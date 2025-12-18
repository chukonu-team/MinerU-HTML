import json
import os
import shutil
import sys
import time
from typing import List

# 现在导入原始脚本
from s3_util import download_from_s3

def get_keys_from_txt(bucket_name , key_path) -> List[str]:
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
                key = key.replace('s3a://','').replace('obs://', '').replace('s3://', '')
                # 移除bucket名称部分（如果有）
                if key.startswith(f"{bucket_name}/"):
                    key = key.split(f"{bucket_name}/", 1)[1]

            if key and key.lower().endswith('.warc.gz'):
                keys.append(key)
            else:
                print(f"Skipping non-PDF key: {key}")

    print(f"Found {len(keys)} valid PDF keys in TXT file")
    return keys


import os
from concurrent.futures import ThreadPoolExecutor, as_completed


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

    # 准备下载任务
    def download_file(key,pdf_path):
        """单个文件下载任务"""
        # 构建预期的结果文件路径
        filename = os.path.basename(key)
        # 检查结果是否已存在
        local_path = os.path.join(pdf_path, filename)
        if os.path.exists(local_path):
            print(f"Skipping already processed file: {filename}")
            return None
        try:
            download_from_s3(s3_bucket, key, local_path)
            return local_path
        except Exception as e:
            print(f"Download file error: {e}, key: {key}")
            return None

    # 使用多线程下载文件
    downloaded_files = []
    with ThreadPoolExecutor(max_workers=100) as executor:
        # 提交所有下载任务
        future_to_key = {executor.submit(download_file, key,pdf_dir): key for key in object_keys}
        # 收集下载结果
        for future in as_completed(future_to_key):
            result = future.result()
            if result is not None:
                downloaded_files.append(result)

    if not downloaded_files:
        print(f"Batch {bucket_index} skipped - all files already processed")


if __name__ == "__main__":
    # 从环境变量获取作业索引
    s3_bucket = os.getenv("S3_BUCKET")
    node_name = os.getenv("NODE_NAME")
    print("node_name", node_name)

    json_map_path = os.getenv("JSON_MAP_PATH")
    with open(json_map_path, 'r') as f:
        json_map = json.load(f)

    bucket_list = []
    for key in json_map:
        if json_map[key] == node_name:
            bucket_list.append(key)

    print(f"Found {len(bucket_list)} buckets")
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
            import traceback

            traceback.print_exc()
            sys.exit(1)
