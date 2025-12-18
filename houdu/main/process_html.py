#!/usr/bin/env python3
import gzip
import io
import os
import re
import time
import glob
import zlib
from typing import List, Dict, Any, Optional
import traceback

# 导入简化的进程池
from process_pool import SimpleProcessPool
from dripper.api import Dripper

# Initialize with model path
dripper = Dripper(
    config={
        'model_path': os.environ.get("MODEL_PATH","/data/models"),  # Required
        'tp': os.environ.get("TENSOR_PARALLEL",1),                                # Tensor parallel size
        'use_fall_back': True,                  # Enable trafilatura fallback
        'raise_errors': False,                  # Return None on errors
    }
)

def read_html_from_warc_gz(warc_gz_path: str) -> list[Any] | None:
    """
    最简单的方法：获取整个文件的原始文本内容
    """
    decompressed_data=""
    html_list=[]
    try:
        # 解压文件
        with open(warc_gz_path, 'rb') as f:
            compressed_data = f.read()

        # 尝试解压
        try:
            decompressed_data = zlib.decompress(compressed_data, zlib.MAX_WBITS | 16)
        except zlib.error:
            # 尝试其他窗口大小
            for wbits in [zlib.MAX_WBITS | 16, zlib.MAX_WBITS, -zlib.MAX_WBITS]:
                try:
                    decompressed_data = zlib.decompress(compressed_data, wbits)
                    break
                except zlib.error:
                    continue
            else:
                return []

        # 转换为字符串以便查找
        data_str = decompressed_data.decode('utf-8', errors='ignore')
        html_list.append(data_str)
    except Exception as e:
        print(e)

    return html_list


def process_one(file_path, save_dir):
    result = {'success': False}
    try:
        file_base_name = os.path.basename(file_path).replace('.warc.gz', '')
        # 确保保存目录存在
        os.makedirs(save_dir, exist_ok=True)

        html_list = read_html_from_warc_gz(file_path)
        print(f"html_list=============== {len(html_list)} ")
        input_map, generate_inputs, process_datas = dripper.pre_process_data(html_list)
        batch_results = dripper.process_data_ex(input_map, generate_inputs, process_datas)

        if batch_results:
            if len(batch_results) == 1:
                result_content = batch_results[0].main_html
                print(f"result_content=============== {result_content} ")
                result_path = os.path.join(save_dir, f"{file_base_name}.html.gz")
                # 确保内容是字节类型
                if isinstance(result_content, str):
                    result_content = result_content.encode('utf-8')

                with gzip.open(result_path, 'wb') as f:
                    f.write(result_content)

                result = {'success': True}
                return result

            # 如果多个文件，批量保存（当前注释掉的代码）
            # else:
            #     for batch_result in batch_results:
            #         case_id = batch_result.case_id
            #         html = batch_result.main_html
            #         result_path = os.path.join(save_dir, str(file_base_name), f"{case_id}.txt")
            #         os.makedirs(os.path.dirname(result_path), exist_ok=True)
            #         with open(result_path, 'w', encoding='utf-8') as f:
            #             f.write(html)

    except Exception as e:
        print(f"process one failed - {str(e)}")
        return result

def gpu_worker_task(file_path, save_dir, gpu_id=None):
    """
    GPU工作进程的任务函数 - 简化版本
    每个工作进程处理单个PDF文件
    """
    if gpu_id is None:
        gpu_id = os.environ.get("CUDA_VISIBLE_DEVICES", "unknown")

    try:
        # 执行PDF处理
        result = process_one(file_path, save_dir)
        result['gpu_id'] = gpu_id
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'input_path': file_path,
            'gpu_id': gpu_id,
            'traceback': traceback.format_exc()
        }


class SimpleMinerUPool:

    def __init__(self,
                 gpu_ids: List[int],
                 workers_per_gpu: int = 2,
                 vram_size_gb: int = 24,
                 model_path: str = None,):
        self.gpu_ids = gpu_ids
        self.workers_per_gpu = workers_per_gpu
        self.vram_size_gb = vram_size_gb
        self.model_path = model_path

        # 设置环境变量 - 增加内存使用配置
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

        # 创建基于GPU ID的进程池
        self.process_pool = SimpleProcessPool(gpu_ids=gpu_ids, workers_per_gpu=workers_per_gpu)
        print(
            f"Created MinerU pool: {len(gpu_ids)} GPUs × {workers_per_gpu} workers = {len(gpu_ids) * workers_per_gpu} total workers")

    def process_files(self, files: List[str], output_dir: str) -> List[Dict]:
        print(f"Processing {len(files)} PDF files using {len(self.gpu_ids)} GPUs...")
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        # 过滤已处理的文件
        files_to_process = []
        for file_path in files:
            result_name = os.path.basename(file_path).replace(".warc.gz", "")
            target_file = f"{output_dir}/{result_name}.html.gz"
            if os.path.exists(target_file):
                print(f"Already processed: {file_path} -> {target_file}")
                continue
            files_to_process.append(file_path)

        if not files_to_process:
            print("No files need processing")
            return []
        print(f"After filtering: {len(files_to_process)} files to process")
        results = []
        task_info = {}  # 存储任务ID和输入路径的映射

        try:
            # 提交所有任务
            for file_path in files_to_process:
                task_data = (file_path, output_dir)
                task_id = self.process_pool.submit_task(gpu_worker_task, *task_data)
                task_info[task_id] = file_path

            print(f"Submitted {len(files_to_process)} tasks to process pool")

            # 设置完成信号
            self.process_pool.set_complete_signal()

            # 收集结果
            start_time = time.time()

            # 等待所有任务完成
            for _ in range(len(files_to_process)):
                result = self.process_pool.get_result()
                if result:
                    task_id, status, data = result
                    pdf_path = task_info.get(task_id, "unknown")

                    if status == 'success':
                        results.append(data)
                        print(f"Task completed: {pdf_path}")
                    elif status == 'error':
                        error_result = {
                            'success': False,
                            'error': data,
                            'input_path': pdf_path
                        }
                        results.append(error_result)
                        print(f"Task failed: {pdf_path} with error: {data}")

            total_time = time.time() - start_time
            success_count = sum(1 for r in results if r.get('success', False))
            skipped_count = sum(1 for r in results if r.get('skipped', False))

            print(f"\nProcessing complete!")
            print(f"Total time: {total_time:.1f} seconds")
            print(
                f"Success: {success_count}, Skipped: {skipped_count}, Errors: {len(results) - success_count - skipped_count}")

            if success_count > 0:
                print(f"Average: {total_time / success_count:.2f} seconds per successful file")

            return results

        except Exception as e:
            print(f"Unexpected error in process_pdf_files: {e}")
            traceback.print_exc()
            return results
        finally:
            print("Shutting down process pool...")
            self.process_pool.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 确保进程池被正确关闭
        if hasattr(self, 'process_pool'):
            self.process_pool.shutdown()


def process_html(
        input_dir,
        output_dir,
        gpu_ids='0,1,2,3,4,5,6,7',
        workers_per_gpu=2,
        vram_size_gb=24
):
    """处理PDF文件的函数，可通过参数直接调用"""
    # 解析GPU ID
    gpu_ids = [int(x.strip()) for x in gpu_ids.split(',')]

    files = glob.glob(f"{input_dir}/*.gz")
    print(f"Found {len(files)} files")
    print(f"Using GPUs: {gpu_ids}")
    print(f"Workers per GPU: {workers_per_gpu}")

    if not files:
        print("No PDF files found!")
        return

    # 创建处理池并运行
    with SimpleMinerUPool(
            gpu_ids=gpu_ids,
            workers_per_gpu=workers_per_gpu,
            vram_size_gb=vram_size_gb
    ) as pool:
        results = pool.process_files(files, output_dir)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fixed MinerU PDF Processing")
    parser.add_argument('--input-dir', type=str, required=True)
    parser.add_argument('--output-dir', type=str, required=True)
    parser.add_argument('--gpu-ids', type=str, default='0,1,2,3,4,5,6,7')
    parser.add_argument('--workers-per-gpu', type=int, default=2)
    parser.add_argument('--vram-size-gb', type=int, default=8)
    args = parser.parse_args()

    process_html(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        gpu_ids=args.gpu_ids,
        workers_per_gpu=args.workers_per_gpu,
        vram_size_gb=args.vram_size_gb,
    )