import json
import os
import sys
import time
from typing import List
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count, Manager
import traceback

# 现在导入原始脚本
from s3_util import download_from_s3


def get_keys_from_txt(bucket_name, key_path) -> List[str]:
    """从S3的TXT文件中获取所有PDF对象的key"""
    # 读取TXT文件内容
    keys = []
    with open(key_path, 'r') as f:
        for line in f:
            key = line.strip()

            if key.startswith("s3://houdu/mb"):
                key = key.replace("s3://houdu/mb", "s3://houdu-dataservice/cc/mb_cc")
            if not key:
                continue
            if key.startswith('s3a://') or key.startswith('obs://') or key.startswith('s3://'):
                # 提取路径部分
                key = key.replace('s3a://', '').replace('obs://', '').replace('s3://', '')
                # 移除bucket名称部分（如果有）
                if key.startswith(f"{bucket_name}/"):
                    key = key.split(f"{bucket_name}/", 1)[1]

            if key and key.lower().endswith('.warc.gz'):
                keys.append(key)
            else:
                print(f"Skipping non-PDF key: {key}")

    print(f"Found {len(keys)} valid PDF keys in TXT file")
    return keys


def download_file(args):
    """单个文件下载任务 - 修改为接收元组参数以兼容多进程"""
    key, pdf_dir, s3_bucket = args
    filename = os.path.basename(key)
    local_path = os.path.join(pdf_dir, filename)

    # 检查结果是否已存在
    if os.path.exists(local_path):
        return None

    try:
        download_from_s3(s3_bucket, key, local_path)
        return local_path
    except Exception as e:
        print(f"Download file error: {e}, key: {key}")
        return None


def process_bucket(
        bucket_index,
        s3_bucket,
        key_path,
):
    """处理一个数据桶"""
    # 获取桶中的所有PDF文件key
    object_keys = get_keys_from_txt(s3_bucket, key_path)
    print(f"Bucket {bucket_index} has {len(object_keys)} files to process")

    # 创建本地临时目录
    pdf_dir = f"/mnt/data/input/{bucket_index}"
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)

    # 准备下载任务参数
    download_args = [(key, pdf_dir, s3_bucket) for key in object_keys]

    # 使用多进程下载文件，根据CPU核心数设置进程数
    # 对于大量小文件，可以设置较多进程数
    max_workers = min(cpu_count() * 4, len(object_keys))  # 使用CPU核心数的4倍，但不超过文件数
    if max_workers < 1:
        max_workers = 1

    print(f"Using {max_workers} processes for bucket {bucket_index}")

    downloaded_files = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有下载任务
        future_to_args = {executor.submit(download_file, arg): arg for arg in download_args}

        # 收集下载结果
        completed_count = 0
        total_count = len(download_args)
        for future in as_completed(future_to_args):
            completed_count += 1
            if completed_count % 100 == 0:  # 每100个文件报告一次进度
                print(f"Bucket {bucket_index}: Downloaded {completed_count}/{total_count} files")

            try:
                result = future.result()
                if result is not None:
                    downloaded_files.append(result)
            except Exception as e:
                print(f"Error processing file: {e}")
                continue

    print(f"Bucket {bucket_index}: Downloaded {len(downloaded_files)} files successfully")

    if not downloaded_files:
        print(f"Batch {bucket_index} skipped - all files already processed")

    return downloaded_files


def process_bucket_wrapper(args):
    """包装函数，用于捕获异常并返回结果"""
    bucket_index, s3_bucket, bucket_txt_key = args
    try:
        result = process_bucket(
            bucket_index=bucket_index,
            s3_bucket=s3_bucket,
            key_path=bucket_txt_key
        )
        return (bucket_index, "success", len(result) if result else 0, None)
    except Exception as e:
        error_msg = f"Error processing bucket {bucket_index}: {e}\n{traceback.format_exc()}"
        return (bucket_index, "failed", 0, error_msg)


if __name__ == "__main__":
    # 从环境变量获取作业索引
    s3_bucket = os.getenv("S3_BUCKET")
    node_name = os.getenv("NODE_NAME")
    print(f"node_name: {node_name}")

    json_map_path = os.getenv("JSON_MAP_PATH")
    with open(json_map_path, 'r') as f:
        json_map = json.load(f)

    bucket_list = []
    for key in json_map:
        if json_map[key] == node_name:
            bucket_list.append(key)

    print(f"Found {len(bucket_list)} buckets to process")

    # 准备所有桶的处理参数
    bucket_args = []
    for bucket_index in bucket_list:
        bucket_txt_key = f"{os.getenv('BUCKET_TXT_KEY_PATH')}/{bucket_index}.txt"
        bucket_args.append((bucket_index, s3_bucket, bucket_txt_key))

    # 使用多进程处理多个桶（如果桶数量多的话）
    # 这里我们可以在两个层级上使用多进程：
    # 1. 外层：多个桶并行处理（如果桶数量多）
    # 2. 内层：每个桶内多个文件并行下载

    # 根据桶的数量决定是否在外层也使用多进程
    if len(bucket_args) > 1:
        # 多个桶，在外层也使用多进程
        outer_max_workers = min(cpu_count(), len(bucket_args))
        print(f"Processing {len(bucket_args)} buckets with {outer_max_workers} outer processes")

        success_count = 0
        failed_buckets = []

        with ProcessPoolExecutor(max_workers=outer_max_workers) as executor:
            # 提交所有桶的处理任务
            future_to_bucket = {executor.submit(process_bucket_wrapper, args): args[0] for args in bucket_args}

            # 收集结果
            for future in as_completed(future_to_bucket):
                bucket_index, status, file_count, error_msg = future.result()

                if status == "success":
                    success_count += 1
                    print(f"Bucket {bucket_index} processed successfully: downloaded {file_count} files")
                else:
                    failed_buckets.append(bucket_index)
                    print(f"Bucket {bucket_index} failed: {error_msg}")

        print(f"\nProcessing completed:")
        print(f"  Successfully processed: {success_count} buckets")
        print(f"  Failed buckets: {len(failed_buckets)}")

        if failed_buckets:
            print(f"  Failed bucket indices: {failed_buckets}")
            sys.exit(1)

    else:
        # 只有一个桶，直接处理
        for bucket_index in bucket_list:
            bucket_txt_key = f"{os.getenv('BUCKET_TXT_KEY_PATH')}/{bucket_index}.txt"
            try:
                process_bucket(
                    bucket_index=bucket_index,
                    s3_bucket=s3_bucket,
                    key_path=bucket_txt_key
                )
            except Exception as e:
                print(f"Error processing bucket {bucket_index}: {e}")
                traceback.print_exc()
                sys.exit(1)