import multiprocessing as mp
import time
import os
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
from queue import Empty


@dataclass
class WorkerInfo:
    """工作进程信息"""
    worker_id: int
    process: mp.Process
    gpu_id: int
    pid: Optional[int] = None
    status: str = "running"


def _worker_process(worker_id: int, gpu_id: int, task_queue: mp.Queue,
                    result_queue: mp.Queue, shutdown_event: mp.Event):
    """工作进程主循环函数"""
    task_count = 0
    os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.set_device(0)
            torch.cuda.empty_cache()
            gpu_name = torch.cuda.get_device_name(0)
            total_memory = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            print(f"Worker {worker_id} (GPU {gpu_id}) initialized: {gpu_name} ({total_memory:.1f}GB)")
    except ImportError:
        pass

    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=1.0)
            if task is None:
                break

            task_id, func, args, kwargs = task
            try:
                kwargs_with_gpu = kwargs.copy()
                kwargs_with_gpu['gpu_id'] = gpu_id
                result = func(*args, **kwargs_with_gpu)
                result_queue.put((task_id, 'success', result))
                task_count += 1
            except Exception as e:
                print(f"Worker {worker_id} task error: {e}")
                result_queue.put((task_id, 'error', str(e)))
        except Empty:
            continue
        except Exception as e:
            print(f"Worker {worker_id} unexpected error: {e}")
            break

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except:
        pass

    print(f"Worker {worker_id} (GPU {gpu_id}) exiting, processed {task_count} tasks")


class SimpleProcessPool:
    """简化进程池类"""

    def __init__(self, gpu_ids: list = None, workers_per_gpu: int = 2):
        if gpu_ids is None:
            gpu_ids = [0]

        self.gpu_ids = gpu_ids
        self.workers_per_gpu = workers_per_gpu
        self.max_workers = len(gpu_ids) * workers_per_gpu
        self.workers: Dict[int, WorkerInfo] = {}
        self.next_worker_id = 0
        self.task_queue = mp.Queue()
        self.result_queue = mp.Queue()
        self.shutdown_event = mp.Event()

        for gpu_id in self.gpu_ids:
            for _ in range(self.workers_per_gpu):
                self._create_worker(gpu_id)

    def _create_worker(self, gpu_id: int) -> int:
        if len(self.workers) >= self.max_workers:
            raise RuntimeError(f"Maximum workers reached")

        worker_id = self.next_worker_id
        self.next_worker_id += 1

        process = mp.Process(
            target=_worker_process,
            args=(worker_id, gpu_id, self.task_queue, self.result_queue, self.shutdown_event)
        )

        worker_info = WorkerInfo(
            worker_id=worker_id,
            process=process,
            gpu_id=gpu_id
        )

        process.start()
        worker_info.pid = process.pid
        self.workers[worker_id] = worker_info

        print(f"Created worker {worker_id} on GPU {gpu_id} with PID {process.pid}")
        return worker_id

    def submit_task(self, func: Callable, *args, **kwargs) -> int:
        task_id = int(time.time() * 1000000)
        task = (task_id, func, args, kwargs)
        self.task_queue.put(task)
        return task_id

    def get_result(self, timeout: float = None) -> Optional[tuple]:
        try:
            return self.result_queue.get(timeout=timeout)
        except Empty:
            return None

    def is_task_queue_empty(self) -> bool:
        return self.task_queue.empty()

    def get_queue_size(self) -> int:
        return self.task_queue.qsize()

    def set_complete_signal(self):
        for _ in range(len(self.workers)):
            self.task_queue.put(None)

    def all_tasks_completed(self) -> bool:
        return self.is_task_queue_empty() and len(self.workers) == 0

    def shutdown(self, timeout: float = 10.0):
        print("Shutting down process pool...")
        self.shutdown_event.set()

        for _ in range(len(self.workers)):
            self.task_queue.put(None)

        dead_workers = []
        start_time = time.time()

        while time.time() - start_time < timeout and self.workers:
            for worker_id, worker_info in list(self.workers.items()):
                if not worker_info.process.is_alive():
                    dead_workers.append(worker_id)
                else:
                    worker_info.process.join(timeout=1.0)

            for worker_id in dead_workers:
                if worker_id in self.workers:
                    del self.workers[worker_id]
            dead_workers.clear()

        for worker_info in self.workers.values():
            if worker_info.process.is_alive():
                worker_info.process.terminate()
                worker_info.process.join(timeout=2.0)
                if worker_info.process.is_alive():
                    worker_info.process.kill()
                    worker_info.process.join()

        self.workers.clear()
        print("Process pool shutdown complete")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()