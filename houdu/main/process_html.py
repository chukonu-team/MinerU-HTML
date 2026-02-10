#!/usr/bin/env python3
import gzip
import io
import os
import re
import time
import glob
import zlib
from typing import List, Dict, Any, Optional, Tuple
import traceback
import math

# 导入简化的进程池
from process_pool import SimpleProcessPool
from dripper.api import Dripper

# Initialize with model path
dripper = Dripper(
    config={
        'model_path': os.environ.get("MODEL_PATH", "/data/models"),  # Required
        'tp': os.environ.get("TENSOR_PARALLEL", 1),  # Tensor parallel size
        'use_fall_back': True,  # Enable trafilatura fallback
        'raise_errors': False,  # Return None on errors
    }
)


def read_html_from_warc_gz(warc_gz_path: str) -> list[str]:
    """
    读取WARC文件并返回HTML内容列表
    """
    decompressed_data = ""
    html_list = []
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
        # data_str = decompressed_data.decode('utf-8', errors='ignore')
        file_like_object = io.BytesIO(decompressed_data)
                # 遍历 WARC 中的所有记录
        for record in ArchiveIterator(file_like_object):
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
            # if html_str and html_str not in seen_html:
            #     seen_html.add(html_str)
            #     html_list.append(html_str)
            if html_str:
                html_list.append(html_str)
            # if len(html_list) % 10000 == 0:
            #     break

        # html_list.append(data_str)
    except Exception as e:
        print(f"Error reading {warc_gz_path}: {e}")

    return html_list


def process_batch(file_paths: List[str], save_dir: str, batch_id: int = 0) -> Dict[str, Any]:
    """
    批量处理文件
    """
    result = {'success': False, 'processed': 0, 'failed': 0, 'batch_id': batch_id}
    all_htmls = []
    file_info = []  # 记录每个文件的信息

    try:
        # 确保保存目录存在
        os.makedirs(save_dir, exist_ok=True)

        # 批量读取所有文件的HTML内容
        for file_path in file_paths:
            try:
                html_list = read_html_from_warc_gz(file_path)
                if html_list:
                    all_htmls.extend(html_list)
                    # 记录文件信息：文件路径、HTML内容索引
                    for i, html in enumerate(html_list):
                        file_info.append({
                            'file_path': file_path,
                            'html_index': i,
                            'file_base_name': os.path.basename(file_path).replace('.warc.gz', ''),
                            'total_in_file': len(html_list)
                        })
                else:
                    result['failed'] += 1
                    print(f"No HTML content found in {file_path}")
            except Exception as e:
                result['failed'] += 1
                print(f"Error reading {file_path}: {e}")

        if not all_htmls:
            print(f"Batch {batch_id}: No HTML content to process")
            return result

        print(f"Batch {batch_id}: Processing {len(all_htmls)} HTMLs from {len(file_paths)} files")

        # 批量处理HTML
        input_map, generate_inputs, process_datas = dripper.pre_process_data(all_htmls)
        batch_results = dripper.process_data_ex(input_map, generate_inputs, process_datas)

        if batch_results:
            # 保存处理结果
            success_count = 0
            for idx, batch_result in enumerate(batch_results):
                if idx >= len(file_info):
                    print(f"Warning: Result index {idx} out of range for file_info")
                    continue

                file_info_item = file_info[idx]
                result_content = batch_result.main_html

                # 生成文件名
                if file_info_item['total_in_file'] == 1:
                    # 如果文件只有一个HTML，使用原始文件名
                    result_filename = f"{file_info_item['file_base_name']}.html.gz"
                else:
                    # 如果文件有多个HTML，添加索引
                    result_filename = f"{file_info_item['file_base_name']}_{file_info_item['html_index']}.html.gz"

                result_path = os.path.join(save_dir, result_filename)

                try:
                    # 确保内容是字节类型
                    if isinstance(result_content, str):
                        result_content = result_content.encode('utf-8')

                    with gzip.open(result_path, 'wb') as f:
                        f.write(result_content)

                    success_count += 1
                except Exception as e:
                    print(f"Error saving {result_path}: {e}")
                    result['failed'] += 1

            result['success'] = True
            result['processed'] = success_count
            print(f"Batch {batch_id}: Successfully processed {success_count} HTMLs")

    except Exception as e:
        print(f"Batch {batch_id} processing failed: {str(e)}")
        traceback.print_exc()

    return result


def gpu_worker_task(file_paths: List[str], save_dir: str, batch_id: int = 0, gpu_id=None):
    """
    GPU工作进程的任务函数 - 批量处理版本
    """
    if gpu_id is None:
        gpu_id = os.environ.get("CUDA_VISIBLE_DEVICES", "unknown")

    try:
        # 执行批量处理
        result = process_batch(file_paths, save_dir, batch_id)
        result['gpu_id'] = gpu_id
        result['batch_id'] = batch_id
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'input_paths': file_paths,
            'gpu_id': gpu_id,
            'batch_id': batch_id,
            'traceback': traceback.format_exc()
        }


class SimpleMinerUPool:

    def __init__(self,
                 gpu_ids: List[int],
                 workers_per_gpu: int = 2,
                 vram_size_gb: int = 24,
                 batch_size: int = 8,  # 每个批次的文件数
                 model_path: str = None, ):
        self.gpu_ids = gpu_ids
        self.workers_per_gpu = workers_per_gpu
        self.vram_size_gb = vram_size_gb
        self.batch_size = batch_size
        self.model_path = model_path

        # 设置环境变量 - 增加内存使用配置
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

        # 创建基于GPU ID的进程池
        self.process_pool = SimpleProcessPool(gpu_ids=gpu_ids, workers_per_gpu=workers_per_gpu)
        print(
            f"Created MinerU pool: {len(gpu_ids)} GPUs × {workers_per_gpu} workers = {len(gpu_ids) * workers_per_gpu} total workers")
        print(f"Batch settings: {batch_size} files per batch")

    def _create_batches(self, files: List[str]) -> List[List[str]]:
        """
        将文件列表分成批次
        """
        batches = []

        for i in range(0, len(files), self.batch_size):
            batch_files = files[i:i + self.batch_size]

            # 过滤已处理的文件
            filtered_batch = []
            for file_path in batch_files:
                result_name = os.path.basename(file_path).replace(".warc.gz", "")
                # 检查是否已处理单个HTML文件
                target_file = f"{self.output_dir}/{result_name}.html.gz"
                # 检查是否已处理多个HTML文件（如果文件包含多个HTML）
                target_pattern = f"{self.output_dir}/{result_name}_*.html.gz"

                # 如果还没有处理过任何该文件的输出，则添加到处理队列
                if not os.path.exists(target_file) and not glob.glob(target_pattern):
                    filtered_batch.append(file_path)
                else:
                    print(f"Already processed: {file_path}")

            if filtered_batch:
                batches.append(filtered_batch)

        return batches

    def process_files(self, files: List[str], output_dir: str) -> List[Dict]:
        print(f"Processing {len(files)} files using {len(self.gpu_ids)} GPUs...")
        self.output_dir = output_dir
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 创建批次
        batches = self._create_batches(files)

        if not batches:
            print("No files need processing")
            return []

        print(f"Created {len(batches)} batches for processing")

        results = []
        task_info = {}  # 存储任务ID和批次信息的映射

        try:
            # 提交所有批次任务
            for batch_id, batch_files in enumerate(batches):
                task_data = (batch_files, output_dir, batch_id)
                task_id = self.process_pool.submit_task(gpu_worker_task, *task_data)
                task_info[task_id] = {
                    'batch_id': batch_id,
                    'file_count': len(batch_files),
                    'files': batch_files
                }
                print(f"Submitted batch {batch_id} with {len(batch_files)} files")

            print(f"Submitted {len(batches)} batches to process pool")

            # 设置完成信号
            self.process_pool.set_complete_signal()

            # 收集结果
            start_time = time.time()
            batch_times = []

            # 等待所有任务完成
            for _ in range(len(batches)):
                result = self.process_pool.get_result()
                if result:
                    task_id, status, data = result
                    batch_info = task_info.get(task_id, {})
                    batch_id = batch_info.get('batch_id', 'unknown')

                    if status == 'success':
                        results.append(data)
                        batch_time = time.time() - start_time
                        batch_times.append(batch_time)
                        print(f"Batch {batch_id} completed: processed {data.get('processed', 0)} HTMLs, "
                              f"failed {data.get('failed', 0)} in {batch_time:.1f}s")
                    elif status == 'error':
                        error_result = {
                            'success': False,
                            'error': data,
                            'batch_id': batch_id,
                            'file_count': batch_info.get('file_count', 0)
                        }
                        results.append(error_result)
                        print(f"Batch {batch_id} failed with error: {data}")

            total_time = time.time() - start_time

            # 统计结果
            success_count = sum(1 for r in results if r.get('success', False))
            total_processed = sum(r.get('processed', 0) for r in results if r.get('success', False))
            total_failed = sum(r.get('failed', 0) for r in results if r.get('success', False))
            error_count = sum(1 for r in results if not r.get('success', False))

            print(f"\nProcessing complete!")
            print(f"Total time: {total_time:.1f} seconds")
            print(f"Batches: {len(batches)} total, {success_count} successful, {error_count} failed")
            print(f"HTMLs: {total_processed} processed, {total_failed} failed")

            if success_count > 0 and batch_times:
                avg_batch_time = sum(batch_times) / len(batch_times)
                print(f"Average batch time: {avg_batch_time:.2f} seconds")
                if total_processed > 0:
                    print(f"Average: {total_time / total_processed:.2f} seconds per HTML")

            return results

        except Exception as e:
            print(f"Unexpected error in process_files: {e}")
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
        vram_size_gb=24,
        batch_size=8,
):
    """处理HTML文件的函数，可通过参数直接调用"""
    # 解析GPU ID
    gpu_ids = [int(x.strip()) for x in gpu_ids.split(',')]

    files = glob.glob(f"{input_dir}/*.gz")
    print(f"Found {len(files)} files")
    print(f"Using GPUs: {gpu_ids}")
    print(f"Workers per GPU: {workers_per_gpu}")
    print(f"Batch size: {batch_size} files per batch")

    if not files:
        print("No files found!")
        return

    # 创建处理池并运行
    with SimpleMinerUPool(
            gpu_ids=gpu_ids,
            workers_per_gpu=workers_per_gpu,
            vram_size_gb=vram_size_gb,
            batch_size=batch_size
    ) as pool:
        results = pool.process_files(files, output_dir)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MinerU WARC HTML Processing with Batch Support")
    parser.add_argument('--input-dir', type=str, required=True, help="Input directory containing .warc.gz files")
    parser.add_argument('--output-dir', type=str, required=True, help="Output directory for processed HTMLs")
    parser.add_argument('--gpu-ids', type=str, default='0,1,2,3,4,5,6,7', help="Comma-separated GPU IDs")
    parser.add_argument('--workers-per-gpu', type=int, default=2, help="Number of workers per GPU")
    parser.add_argument('--vram-size-gb', type=int, default=8, help="VRAM size per GPU in GB")
    parser.add_argument('--batch-size', type=int, default=8, help="Number of files per batch")
    args = parser.parse_args()

    process_html(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        gpu_ids=args.gpu_ids,
        workers_per_gpu=args.workers_per_gpu,
        vram_size_gb=args.vram_size_gb,
        batch_size=args.batch_size,
    )