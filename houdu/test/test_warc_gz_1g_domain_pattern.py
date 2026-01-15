# pip install warcio
from warcio.archiveiterator import ArchiveIterator
import gzip
import os, time
import cProfile, pstats, io
from dataclasses import dataclass
from typing import Optional, Dict, Any, Set
import datetime
from urllib.parse import urlparse

# from dripper.api import Dripper

@dataclass
class WARCRecordResult:
    """
    Structure to store WARC request results
    """
    # Basic record information
    read_url: str
    read_meta_str: Optional[str] = None
    read_response_str: Optional[str] = None
    is_filtered: bool = False

# Initialize with model path
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
    read_record_by_url = {}

    # 打开 warc.gz 文件（gzip 自动解压）
    with gzip.open(warc_gz_path, 'rb') as f:
        # 遍历 WARC 中的所有记录
        for record in ArchiveIterator(f):
            # 1. 筛选 HTTP 响应记录（只有 response 类型才包含网页内容）
            # 记录类型：response（响应）、request（请求）、metadata（元数据）等
            if record.rec_type != 'metadata' and record.rec_type != 'response' and record.rec_type != 'request':
                continue
            record_url = record.rec_headers.get_header('WARC-Target-URI')
            if record_url not in read_record_by_url:
                read_record_by_url[record_url] = WARCRecordResult(
                    read_url=record_url,
                    read_meta_str=None,
                    read_response_str=None
                )
            if record.rec_type == 'metadata':
                readstr = record.content_stream().read().decode('utf-8', errors='ignore').strip()
                # print(readstr)
                # if "Chinese" in readstr or "ENGLISH" in readstr:
                # if "Chinese" in readstr:
                #     read_record_by_url[record_url].is_filtered = False
                
                if read_record_by_url[record_url].read_meta_str is None:
                    read_record_by_url[record_url].read_meta_str = readstr
                else:
                    read_record_by_url[record_url].read_meta_str = readstr

            
            if record.rec_type == 'request':
                # readstr = record.content_stream().read().decode('utf-8', errors='ignore').strip()
                # print(readstr)
                continue
            
            if record.rec_type == 'response':
                if record_url not in read_record_by_url:
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
                # if html_str and html_str not in seen_html:
                #     seen_html.add(html_str)
                #     html_list.append(html_str)
                if html_str:
                    # seen_html.add(html_str)
                    if read_record_by_url[record_url].read_response_str is None:
                        read_record_by_url[record_url].read_response_str = html_str
                    else:
                        read_record_by_url[record_url].read_response_str = html_str
                    html_list.append(read_record_by_url[record_url])

                # if len(html_list) % 1000 == 0:
                #     break

    return html_list


start_time = time.time()
# html_list = read_html_from_warc_gz('/home/chukonu/MinerU-HTML/deploy_0/CC-MAIN-20250918080014-20250918110014-00995.warc.gz')
html_list = read_html_from_warc_gz('/home/chukonu/MinerU-HTML/deploy_0/CC-MAIN-20150226074105-00240-ip-10-28-5-156.ec2.internal.warc.gz')

end_time = time.time()
elapsed_time = end_time - start_time
print(f"File reading took {elapsed_time:.2f} seconds length: {len(html_list)}")




domains_count = {}
sidx = 0

for item in html_list:
    if item.is_filtered is False:
        # Extract just the main domain + subdomain
        # domain = item.read_url
        parsed_url = urlparse(item.read_url)
        domain = parsed_url.netloc
        if domain in domains_count:
            domains_count[domain] += 1
        else:
            domains_count[domain] = 1
        # if domain == 'bo.ebay.com':
        #     filename = f'{output_dir}/{sidx}.html'
        #     with open(filename, 'w', encoding='utf-8') as f:
        #         f.write(item.read_response_str)
        #         sidx += 1
            


# 使用 Counter 获取并打印前10个域名
from collections import Counter
domains_counter = Counter(domains_count)
top_10_domains = domains_counter.most_common(100)

print("Top 10 domains by count:")
print("-" * 30)
domains_count_topN = {}
for i, (domain, count) in enumerate(top_10_domains, 1):
    domains_count_topN[domain] = 0
    print(f"{i:2d}. {domain}: {count}")


output_dir = './results'
os.makedirs(output_dir, exist_ok=True)

for item in html_list:
    if item.is_filtered is False:
        parsed_url = urlparse(item.read_url)
        domain = parsed_url.netloc
        if domain in domains_count_topN:
            output_dir = f'./results/{domain}'
            os.makedirs(output_dir, exist_ok=True)
            sidx = domains_count_topN[domain]
            filename = f'{output_dir}/{sidx}.html'
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(item.read_response_str)
                sidx += 1
            domains_count_topN[domain] += 1