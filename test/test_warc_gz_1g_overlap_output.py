# pip install warcio
from warcio.archiveiterator import ArchiveIterator
import gzip
import time
import cProfile, pstats, io
from multiprocessing import Process, Queue, Manager
import queue
import sys
import os
import signal
import time

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from dripper.api import Dripper


class HtmlDataProducer:
    def __init__(self, warc_file_path, batch_size=100):
        self.batch_size = batch_size
        self.current_index = 0
        start_time = time.time()
        logger.info(f"HtmlDataProducer : read_html_from_warc_gz warc_file_path:{warc_file_path}")
        self.warc_file_path = warc_file_path
        self.html_list = self.read_html_from_warc_gz(self.warc_file_path)
        self.total_count = len(self.html_list)
        self.total_count = 1000 # test
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"HtmlDataProducer : File reading took {elapsed_time:.2f} seconds")

    
    def consume_batch(self, batch_size=None):
        """
        消费一批数据, 返回数据批次列表和是否有更多数据标识
        Args:
            batch_size: 指定的批次大小，如果不指定则使用默认值
            
        Returns:
            tuple: (data_batch, has_data_flag)
                - data_batch: 数据批次列表
                - has_data_flag: 是否还有更多数据 (True/False)
        """
        if batch_size is None:
            batch_size = self.batch_size
            
        # 计算当前批次的结束索引
        end_index = min(self.current_index + batch_size, self.total_count)
        
        # 获取当前批次的数据
        data_batch = self.html_list[self.current_index:end_index]
        
        # 更新索引
        self.current_index = end_index
        
        # 检查是否还有更多数据
        has_data_flag = self.current_index < self.total_count
        
        return data_batch, has_data_flag
    def read_html_from_warc_gz(self, warc_gz_path: str) -> list[str]:
        """
        从 warc.gz 文件中提取所有 HTML 字符串，返回列表

        参数:
            warc_gz_path: warc.gz 文件的路径（相对/绝对路径）

        返回:
            list[str]: 去重后的 HTML 字符串列表（空列表表示无有效 HTML）
        """
        html_list = []
        seen_html = set()  # 用于去重（避免重复网页）

        # 打开 warc.gz 文件（gzip 自动解压）
        with gzip.open(warc_gz_path, 'rb') as f:
            # 遍历 WARC 中的所有记录
            for record in ArchiveIterator(f):
                # 1. 筛选 HTTP 响应记录（只有 response 类型才包含网页内容）
                # 记录类型：response（响应）、request（请求）、metadata（元数据）等
                if record.rec_type != 'response':
                    continue

                # 2. 验证 Content-Type 是 HTML（避免提取图片、JS、CSS 等非 HTML 内容）
                content_type = record.http_headers.get('Content-Type', '')
                if 'text/html' not in content_type.lower():
                    continue

                # 3. 读取响应体（网页原始数据），解码为字符串
                try:
                    # 读取字节流，按 HTTP 编码解码（优先从 headers 取 charset，默认 utf-8）
                    html_bytes = record.content_stream().read()
                    charset = 'utf-8'  # 默认编码
                    # 从 Content-Type 中提取字符集（如：text/html; charset=utf-8）
                    for part in content_type.split(';'):
                        part = part.strip()
                        if part.startswith('charset='):
                            charset = part.split('=')[-1].strip()
                            break
                    # 解码为字符串（忽略非法字符，避免解码报错）
                    html_str = html_bytes.decode(charset, errors='ignore').strip()
                except Exception as e:
                    logger.info(f"警告：解析记录失败 - {str(e)}")
                    continue

                # 4. 过滤空字符串和重复 HTML
                if html_str and html_str not in seen_html:
                    seen_html.add(html_str)
                    html_list.append(html_str)

                if len(html_list) % 10000 == 0:
                    break

        return html_list

class DripperRunner:
    def __init__(self, dripper: Dripper, html_data_producer: HtmlDataProducer):
        """
        初始化 DripperRunner
        
        Args:
            dripper: Dripper实例
            html_data_producer: HTML数据生产者实例
            config: 配置字典（可选，如果提供则会覆盖dripper的设置）
        """
        self.dripper = dripper
        self.html_data_producer = html_data_producer
        self.process_running = True
        self.preprocess_result_queue = Queue()
        self.generate_result_queue = Queue()
        self.postprocess_result_queue = Queue()
        self.processes = []
        self.all_results = []
        
        self.queue_max_size = 10
        
        # 启动预处理工作进程
        logger.info("Starting preprocess worker")
        self.pre_process = self.start_preprocess_worker(1)
        
        # 启动后处理工作进程
        logger.info("Starting postprocess worker")
        self.post_process = self.start_postprocess_worker(2)
        
        self.run()
    
    def start_preprocess_worker(self, worker_id: int = 1):
        """
        启动预处理工作进程
        """
        p = Process(target=self._preprocess_worker_all, args=(worker_id,))
        p.start()
        return p
        
    def _preprocess_worker_all(self, worker_id: int):
        """
        子进程预处理工作函数，循环处理html_list中的数据
        """
        try:
            logger.info(f"Worker {worker_id}: Starting preprocessing ")
            
            has_data = True
            index = 1
            while has_data:
                                # 获取下一批数据
                html_list, has_data = self.html_data_producer.consume_batch()
                current_batch = html_list
                logger.info(f"Worker {worker_id}: Processing batch starting at index {index}, size {len(current_batch)}")
                
                # 检查队列大小，如果大于10则等待
                while self.preprocess_result_queue.qsize() > self.queue_max_size:
                    logger.info(f"Worker {worker_id}: Queue size is {self.preprocess_result_queue.qsize()}, sleeping...")
                    time.sleep(5)  # 等待1秒后再次检查
                
                try:
                    logger.info(f"Worker {worker_id}: Preprocessing batch starting at index {index}, size {len(current_batch)}")
                    input_map, generate_inputs, process_datas = self.dripper.pre_process_data(current_batch)
                    
                    # 将结果放入队列
                    self.preprocess_result_queue.put((index, (input_map, generate_inputs, process_datas)), timeout=1)
                    logger.info(f"Worker {worker_id}: Finished preprocessing batch at index {index}, added to queue")
                    
                except Exception as e:
                    logger.info(f"Worker {worker_id}: Error in preprocessing batch at index {index} - {str(e)}")
                

                index += 1
            time.sleep(5)
            logger.info(f"Worker {worker_id}: Finished all preprocessing tasks")
        except Exception as e:
            logger.info(f"Worker {worker_id}: Fatal error - {str(e)}")
    
    def start_postprocess_worker(self, worker_id: int = 1):
        """
        启动后处理工作进程
        """
        p = Process(target=self._postprocess_worker_all, args=(worker_id,))
        p.start()
        return p
    
    def _postprocess_worker_all(self, worker_id: int):
        """
        后处理工作函数，处理预处理结果
        """
        process_result_pack = None
        logger.info(f"Worker {worker_id}: postprocess_worker begin")
        while True:
            try:
                logger.info(f"Worker {worker_id}: postprocess_worker begin get data")
                batch_id, process_result_pack = self.generate_result_queue.get(timeout=5)
                if process_result_pack is None:
                    logger.info(f"Worker {worker_id}: Error in postprocess_worker")
                    if batch_id == -1:
                        logger.info(f"Worker {worker_id}: Finish postprocess_worker")
                        break
                    time.sleep(1)
                    continue
                    
                logger.info(f"Worker {worker_id}: batch_id- {batch_id} postprocess_worker post_process_data")
                input_map, generate_inputs, process_datas, process_results = process_result_pack
                batch_results = self.dripper.post_process_data(input_map, generate_inputs, process_datas, process_results)
                # self.all_results.extend(batch_results)
                self.postprocess_result_queue.put(batch_results)

            except queue.Empty:
                # 队列为空，继续循环
                logger.info(f"Worker {worker_id}: postprocess_worker queue.Empty")
                continue
            except Exception as e:
                process_result_pack = None
                logger.info(f"Worker {worker_id}: Fatal error - {str(e)}")
        self.postprocess_result_queue.put(None)
        logger.info(f"Worker {worker_id}: postprocess_worker end")

    
    def run(self):
        """
        运行整个处理流程
        """

        
        # 主处理循环
        process_numbers = 0
        batch_index = 0
        while True:
            try:
                logger.info(f"run: begin get data")
                worker_id, preprocess_result = self.preprocess_result_queue.get(timeout=5)  # 5分钟超时
                if preprocess_result is None:
                    logger.info(f"Error in preprocessing batch {batch_index + 1}")
                    batch_index += 1
                    continue
                    
                input_map, generate_inputs, process_datas = preprocess_result
                
                # 处理当前批次
                start_time = time.time()
                batch_process_results = self.dripper.generate_data(generate_inputs)
                end_time = time.time()
                elapsed_time = end_time - start_time
                self.generate_result_queue.put((batch_index, (input_map, generate_inputs, process_datas, batch_process_results)), timeout=1)
                
                batch_actual_size = len(input_map)
                logger.info(f"Processing batch {batch_index + 1} (size: {batch_actual_size}) took {elapsed_time:.2f} seconds")
                batch_index += 1
                process_numbers += batch_actual_size
                
            except queue.Empty:
                logger.info("Timeout waiting for preprocessing result")
                if self.pre_process.is_alive():
                    continue
                else:
                    break
        
        # 结束处理
        self.generate_result_queue.put((-1, None), timeout=1)
        self.process_running = False
        time.sleep(1)
        
        # 等待所有子进程结束,确保后处理结束
        
        
        # 获取处理结果
        # while self.postprocess_result_queue.qsize() > 0:
        #     self.all_results.extend(self.postprocess_result_queue.get())
        # 获取处理结果 - 持续获取直到获取到None
        while True:
            try:
                result = self.postprocess_result_queue.get(timeout=1)  # 使用较短超时避免无限等待
                if result is None:  # 如果获取到None，则停止获取
                    logger.info("Received None, stopping result collection")
                    break
                self.all_results.extend(result)  # 将结果添加到列表中
            except queue.Empty:
                logger.info("No more results in postprocess queue, continue collection")
                continue

        self._cleanup_processes()
        # 打印结果
        if self.all_results:
            logger.info(f"results len:{len(self.all_results)}")
            logger.info(self.all_results[0].main_html)
            
        return self.all_results
    
    def _cleanup_processes(self):
        """
        清理和等待所有子进程结束
        """

        # 循环等待直到进程退出
        while self.post_process.is_alive():
            logger.info(f"Waiting for process {self.post_process.pid} to exit...")
            self.post_process.join(timeout=2)  # 每次等待1秒
        logger.info(f"Process {self.post_process.pid} has exited normally")
                
        # 关闭队列，释放资源
        self.preprocess_result_queue.close()
        self.preprocess_result_queue.join_thread()
        self.generate_result_queue.close()
        self.generate_result_queue.join_thread()
        
        
def main():
    # Initialize with model path
    dripper = Dripper(
        config={
            'model_path': '/root/data/models',  # Required
            'tp': 1,                                # Tensor parallel size
            'use_fall_back': True,                  # Enable trafilatura fallback
            'raise_errors': False,                  # Return None on errors
        }
    )

    # Create HtmlDataProducer
    html_data_producer = HtmlDataProducer(warc_file_path='/root/data/CC-MAIN-20250918080014-20250918110014-00995.warc.gz', batch_size=300)

    # Run profiling if needed
    pr = cProfile.Profile()
    pr.enable()

    start_time0 = time.time()

    # Run the processing
    # Create DripperRunner
    runner = DripperRunner(dripper, html_data_producer)

    end_time = time.time()
    elapsed_time = end_time - start_time0
    logger.info(f"Total processing took {elapsed_time:.2f} seconds")

    # Print profiling results
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('time')
    ps.print_stats(10)
    logger.info(s.getvalue())

        
if __name__ == "__main__":
    main()