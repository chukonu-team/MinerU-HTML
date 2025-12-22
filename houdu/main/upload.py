import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing
from threading import Lock as ThreadLock
from common import get_subdirectories, has_files
from s3_util import upload_to_s3
from functools import partial


def process_file(filename, upload_result_list, upload_result_file,
                 result_dir, bucket_index, s3_bucket, result_key, thread_lock):
    """处理单个文件的上传任务"""
    if filename in upload_result_list:
        return None, filename, "skipped"

    if not filename.endswith((".gz")):
        return None, filename, "skipped"

    s3_key = os.path.join(result_key, bucket_index, filename)
    result_path = os.path.join(result_dir, filename)

    try:
        upload_to_s3(result_path, s3_bucket, s3_key)

        # 使用线程锁安全地写入文件
        with thread_lock:
            try:
                with open(upload_result_file, "a", encoding="utf8") as f:
                    f.write(f"{filename}\n")
                return True, filename, "success"
            except Exception as e:
                return False, filename, f"write error: {e}"
    except Exception as e:
        return False, filename, f"upload error: {e}"


def process_bucket_directory(bucket_index, output_dir, s3_bucket, result_key, process_lock):
    """处理单个bucket目录的上传任务，使用多线程处理文件"""
    upload_result_list = set()
    upload_result_file = os.path.join(output_dir, bucket_index, "upload_result.txt")

    # 使用进程锁安全地读取文件（进程间同步）
    with process_lock:
        if os.path.exists(upload_result_file):
            try:
                with open(upload_result_file, "r", encoding="utf8") as f:
                    for line in f:
                        line = line.strip()
                        upload_result_list.add(line)
            except Exception as e:
                print(f"Error reading {upload_result_file}: {e}")

    # 创建线程锁（线程间同步，同一个进程内）
    thread_lock = ThreadLock()

    # 处理result目录
    result_dir = os.path.join(output_dir, bucket_index)
    if not has_files(result_dir):
        return bucket_index, [], []

    try:
        list_result = os.listdir(result_dir)
    except Exception as e:
        print(f"Error listing directory {result_dir}: {e}")
        return bucket_index, [], []

    # 获取线程数配置
    threads_per_process = int(os.environ.get('THREADS_PER_PROCESS', 4))

    success_files = []
    failed_files = []

    # 使用线程池执行器创建多线程
    with ThreadPoolExecutor(max_workers=threads_per_process) as thread_executor:
        # 为每个文件提交一个任务到线程池
        future_to_file = {}
        for filename in list_result:
            # 创建偏函数，固定部分参数
            process_file_func = partial(
                process_file,
                upload_result_list=upload_result_list,
                upload_result_file=upload_result_file,
                result_dir=result_dir,
                bucket_index=bucket_index,
                s3_bucket=s3_bucket,
                result_key=result_key,
                thread_lock=thread_lock
            )
            future = thread_executor.submit(process_file_func, filename)
            future_to_file[future] = filename

        # 等待所有任务完成并处理结果
        for future in as_completed(future_to_file):
            filename = future_to_file[future]
            try:
                result = future.result()
                if result[0] is True:  # 上传成功
                    success_files.append((filename, result[2]))
                elif result[0] is False:  # 上传失败
                    failed_files.append((filename, result[2]))
                # result[0] is None 表示已跳过
            except Exception as e:
                failed_files.append((filename, f"execution error: {e}"))

    return bucket_index, success_files, failed_files


def upload(s3_bucket, result_key):
    output_dir = '/mnt/data/output'
    try:
        list_dir = get_subdirectories(output_dir)
    except Exception as e:
        print(f"Error getting subdirectories from {output_dir}: {e}")
        return

    if not list_dir:
        print("No directories found to process")
        return

    # 创建进程锁
    manager = multiprocessing.Manager()
    process_lock = manager.Lock()

    # 获取进程数配置
    max_workers = int(os.environ.get('MAX_PROCESSES', multiprocessing.cpu_count()))
    threads_per_process = int(os.environ.get('THREADS_PER_PROCESS', 4))

    print(f"Starting upload with {max_workers} processes, {threads_per_process} threads per process")
    print(f"Processing {len(list_dir)} directories")

    # 创建偏函数，固定部分参数
    process_func = partial(
        process_bucket_directory,
        output_dir=output_dir,
        s3_bucket=s3_bucket,
        result_key=result_key,
        process_lock=process_lock
    )

    total_completed = 0
    total_success_files = 0
    total_failed_files = 0
    failed_directories = []
    directory_details = []

    # 使用进程池执行器创建多进程
    with ProcessPoolExecutor(max_workers=max_workers) as process_executor:
        # 为每个bucket目录提交一个任务到进程池
        future_to_dir = {
            process_executor.submit(process_func, bucket_index): bucket_index
            for bucket_index in list_dir
        }

        # 等待所有任务完成并处理结果
        for future in as_completed(future_to_dir):
            bucket_index = future_to_dir[future]
            try:
                result = future.result()
                bucket_index, success_files, failed_files = result

                total_completed += 1
                total_success_files += len(success_files)
                total_failed_files += len(failed_files)

                # 记录目录详细信息
                dir_info = {
                    'dir': bucket_index,
                    'success': len(success_files),
                    'failed': len(failed_files)
                }
                directory_details.append(dir_info)

                print(f"Completed directory: {bucket_index} ({total_completed}/{len(list_dir)})")
                print(f"  - Successfully uploaded: {len(success_files)} files")
                if failed_files:
                    print(f"  - Failed: {len(failed_files)} files")
                    # 可以选择记录失败的详细信息
                    # for filename, error in failed_files[:5]:  # 只显示前5个失败文件
                    #     print(f"    * {filename}: {error}")

            except Exception as e:
                failed_directories.append(bucket_index)
                print(f"Error processing bucket directory {bucket_index}: {e}")

    # 输出处理结果摘要
    print(f"\n{'=' * 60}")
    print("Upload process completed.")
    print(f"{'=' * 60}")
    print(f"Total directories processed: {total_completed}")
    print(f"Total files successfully uploaded: {total_success_files}")
    print(f"Total files failed to upload: {total_failed_files}")

    if failed_directories:
        print(f"\nFailed directories: {len(failed_directories)}")
        for failed_dir in failed_directories:
            print(f"  - {failed_dir}")

    # 输出每个目录的详细统计
    if directory_details:
        print(f"\nDirectory details:")
        for detail in directory_details[:10]:  # 只显示前10个目录的详细信息
            print(f"  - {detail['dir']}: {detail['success']} success, {detail['failed']} failed")
        if len(directory_details) > 10:
            print(f"  ... and {len(directory_details) - 10} more directories")


if __name__ == '__main__':
    # 从环境变量读取配置
    s3_bucket = os.environ.get('S3_BUCKET')
    result_key = os.environ.get('RESULT_KEY')

    # 验证环境变量
    if not all([s3_bucket, result_key]):
        print("Error: Missing required environment variables: S3_BUCKET, RESULT_KEY")
        sys.exit(1)

    upload(s3_bucket, result_key)