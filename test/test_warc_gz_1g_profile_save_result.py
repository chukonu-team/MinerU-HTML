# pip install warcio
from warcio.archiveiterator import ArchiveIterator
import gzip
import time
import cProfile, pstats, io

from dripper.api import Dripper

# Initialize with model path
dripper = Dripper(
    config={
        'model_path': '/home/ubuntu/cenjing/models',  # Required
        'tp': 1,                                # Tensor parallel size
        'use_fall_back': False,                  # Enable trafilatura fallback
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


start_time = time.time()
html_list = read_html_from_warc_gz('/home/ubuntu/cenjing/models/CC-MAIN-20250918080014-20250918110014-00995.warc.gz')
end_time = time.time()
elapsed_time = end_time - start_time
print(f"File reading took {elapsed_time:.2f} seconds")

pr = cProfile.Profile()
pr.enable()

start_time = time.time()
start_time0 = start_time
# results = dripper.process(html_list)
batch_size = 300
all_results = []

for i in range(0, len(html_list), batch_size):
    batch = html_list[i:i + batch_size]

    start_time = time.time()
    input_map, generate_inputs, process_datas = dripper.pre_process_data(batch)
    start_time_process = time.time()
    batch_results = dripper.process_data_ex(input_map, generate_inputs, process_datas)
    # batch_results = dripper.process(batch)
    end_time = time.time()

    elapsed_time_process = end_time - start_time_process
    print(f"Processing batch {i//batch_size + 1} (size: {len(batch)}) process took {elapsed_time_process:.2f} seconds")
    elapsed_time = end_time - start_time
    print(f"Processing batch {i//batch_size + 1} (size: {len(batch)}) took {elapsed_time:.2f} seconds")

    all_results.extend(batch_results)
    batch_idx = i//batch_size + 1
    if batch_idx == 1:
        break

results = all_results

# Create directory for results if it doesn't exist
import os

# Create directory for results if it doesn't exist
output_dir = './results'
os.makedirs(output_dir, exist_ok=True)

raw_output_dir = './raw'
os.makedirs(raw_output_dir, exist_ok=True)

# Save raw HTML content to ./raw folder
for idx in range(len(results)):
    if idx < len(html_list):  # Ensure we don't exceed html_list bounds
        filename = f'{raw_output_dir}/{idx}.html'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_list[idx])

# Save each main_html content to a separate file with appropriate suffix
none_count = 0
total_count = len(results)

for idx, result in enumerate(results):
    # Determine if content is None and set appropriate suffix
    html_content = result.main_html if result.main_html is not None else ""
    # suffix = "_0" if result.main_html is None else "_1"
    none_count += 1 if result.main_html is None else 0

    filename = f'{output_dir}/{idx}.html'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html_content)

# Calculate and print the ratio of None values
none_ratio = none_count / total_count if total_count > 0 else 0
print(f"None ratio: {none_ratio:.2%} ({none_count}/{total_count})")

end_time = time.time()
elapsed_time = end_time - start_time0
print(f"dripper.process took {elapsed_time:.2f} seconds")
pr.disable()
s = io.StringIO(); ps = pstats.Stats(pr, stream=s).sort_stats('time')
ps.print_stats(10)
print(s.getvalue())

# for result in results:
#     print(result.main_html)
print(f"results len:{len(results)}")
print(results[0].main_html)
