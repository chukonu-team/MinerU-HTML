import json
import logging
import os
import shutil
import sys
import time
from typing import List
from common import get_subdirectories, has_files
from process_html import process_html

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def process():
    # 从环境变量获取作业索引
    gpu_ids = os.getenv("GPU_IDS")
    vram_size_gb = os.getenv("VRAM_SIZE_GB")
    workers_per_gpu = os.getenv("WORKERS_PER_GPU")
    proportion = os.getenv("PROPORTION", 0)
    min_files = os.getenv("MIN_FILES",300)

    file_dir = "/mnt/data/input"
    list_dir = get_subdirectories(file_dir)
    output_dir = f"/mnt/data/output"
    index = None

    for bucket_index in list_dir:
        logger.info(f"for bucket ====================={bucket_index}")
        file_path = os.path.join(file_dir, bucket_index)
        if not has_files(file_path):
            continue

        result_dir = os.path.join(output_dir, bucket_index)
        if os.path.exists(result_dir):
            result_list = os.listdir(result_dir)
            file_list = os.listdir(file_path)
            cur_proportion = (len(file_list) - len(result_list)) / len(file_list)
            logger.info(f"cur_proportion================={cur_proportion}")
            if cur_proportion < float(proportion):
                print(f"Skipping {bucket_index} because proportion is less than {proportion}")
                continue

        index = bucket_index
        break


    logger.info(f"Processing index==========================={index}")
    input_path = f"{file_dir}/{index}"
    output_path = f"/mnt/data/output/{index}"
    try:
        # 运行处理任务
        process_html(
            input_dir=input_path,
            output_dir=output_path,
            vram_size_gb=int(vram_size_gb),
            gpu_ids=gpu_ids,
            workers_per_gpu=int(workers_per_gpu),
        )
        sys.exit(0)

    except Exception as e:
        print(f"Error processing bucket {index}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    process()
