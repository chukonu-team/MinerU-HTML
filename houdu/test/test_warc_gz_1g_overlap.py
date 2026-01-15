# pip install warcio
from warcio.archiveiterator import ArchiveIterator
import gzip
import time
import cProfile, pstats, io
from multiprocessing import Process, Queue, Manager
import queue
import sys

from dripper.api import Dripper

# Initialize with model path
dripper = Dripper(
    config={
        'model_path': '/home/ubuntu/cenjing/models',  # Required
        'tp': 1,                                # Tensor parallel size
        'use_fall_back': True,                  # Enable trafilatura fallback
        'raise_errors': False,                  # Return None on errors
    }
)

def read_html_from_warc_gz(warc_gz_path: str) -> list[str]:
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
                print(f"警告：解析记录失败 - {str(e)}")
                continue

            # 4. 过滤空字符串和重复 HTML
            if html_str and html_str not in seen_html:
                seen_html.add(html_str)
                html_list.append(html_str)

            if len(html_list) % 10000 == 0:
                break

    return html_list

def preprocess_worker(batch, result_queue, worker_id):
    """
    子进程预处理工作函数
    """
    try:
        print(f"Worker {worker_id}: Starting preprocessing batch of size {len(batch)}")
        input_map, generate_inputs, process_datas = dripper.pre_process_data(batch)
        result_queue.put((worker_id, (input_map, generate_inputs, process_datas)))
        print(f"Worker {worker_id}: Finished preprocessing")
    except Exception as e:
        print(f"Worker {worker_id}: Error in preprocessing - {str(e)}")
        result_queue.put((worker_id, None))

start_time = time.time()
html_list = read_html_from_warc_gz('/home/ubuntu/cenjing/models/CC-MAIN-20250918080014-20250918110014-00995.warc.gz')
end_time = time.time()
elapsed_time = end_time - start_time
print(f"File reading took {elapsed_time:.2f} seconds")

pr = cProfile.Profile()
pr.enable()

batch_size = 300
all_results = []

# 创建队列用于进程间通信
result_queue = Queue()
processes = []

# 预处理第一批数据
current_batch = html_list[0:batch_size]

start_time = time.time()
start_time0 = start_time
print(f"Preprocessing first batch (size: {len(current_batch)})")
input_map, generate_inputs, process_datas = dripper.pre_process_data(current_batch)

# 预处理第二批数据（如果存在）在子进程中
if len(html_list) > batch_size:
    next_batch = html_list[batch_size:2*batch_size]
    print(f"Starting subprocess for second batch (size: {len(next_batch)})")
    p = Process(target=preprocess_worker, args=(next_batch, result_queue, 1))
    p.start()
    processes.append(p)

# 处理第一批数据


batch_results = dripper.process_data_ex(input_map, generate_inputs, process_datas)
end_time = time.time()
elapsed_time = end_time - start_time
print(f"Processing first batch (size: {len(current_batch)}) took {elapsed_time:.2f} seconds")
all_results.extend(batch_results)

# 主处理循环
batch_index = 1
while batch_index * batch_size < len(html_list):
    # 等待子进程完成并获取结果
    try:
        worker_id, preprocess_result = result_queue.get(timeout=3000)  # 5分钟超时
        if preprocess_result is None:
            print(f"Error in preprocessing batch {batch_index + 1}")
            batch_index += 1
            continue
            
        input_map, generate_inputs, process_datas = preprocess_result
        
        # 启动下一个批次的预处理（如果还有）
        next_batch_start = (batch_index + 2) * batch_size
        if next_batch_start < len(html_list):
            next_batch = html_list[next_batch_start:min(next_batch_start + batch_size, len(html_list))]
            print(f"Starting subprocess for batch {batch_index + 2} (size: {len(next_batch)})")
            p = Process(target=preprocess_worker, args=(next_batch, result_queue, batch_index + 2))
            p.start()
            processes.append(p)
        
        # 处理当前批次
        start_time = time.time()
        batch_results = dripper.process_data_ex(input_map, generate_inputs, process_datas)
        end_time = time.time()
        elapsed_time = end_time - start_time
        batch_actual_size = len(next_batch) if 'next_batch' in locals() else batch_size
        print(f"Processing batch {batch_index + 1} (size: {batch_actual_size}) took {elapsed_time:.2f} seconds")
        
        all_results.extend(batch_results)
        batch_index += 1
        
        # 限制处理批次数目
        if batch_index == 2:
            print("Reached maximum number of batches 3")
            break
            
    except queue.Empty:
        print("Timeout waiting for preprocessing result")
        break

# 等待所有子进程结束
# for p in processes:
#     p.join()

results = all_results

end_time = time.time()
elapsed_time = end_time - start_time0
print(f"Total processing took {elapsed_time:.2f} seconds")
pr.disable()
s = io.StringIO(); ps = pstats.Stats(pr, stream=s).sort_stats('time')
ps.print_stats(10)
print(s.getvalue())

# for result in results:
#     print(result.main_html)

if results:
    print(f"results len:{len(results)}")
    print(results[0].main_html)
