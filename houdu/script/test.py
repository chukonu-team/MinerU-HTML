import zlib
import re
from typing import List, Set



# 使用更高效的解析方式（针对WARC格式优化）
def read_html_from_warc_gz_fast(warc_gz_path: str, max_records: int = 10000) -> List[str]:
    """
    快速从 warc.gz 文件中提取HTML字符串

    使用更高效的解析方式，直接查找WARC和HTTP边界
    """
    global html_str, decompressed_data
    html_list = []
    seen_html = set()

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

        # 查找所有WARC响应记录
        warc_response_positions = []
        pos = 0
        while True:
            pos = data_str.find('WARC-Type: response', pos)
            if pos == -1:
                break

            # 找到WARC记录的开始
            start = data_str.rfind('WARC/', 0, pos)
            if start == -1:
                start = data_str.rfind('\n\n', 0, pos)
                if start != -1:
                    start += 2
                else:
                    start = 0

            warc_response_positions.append(start)
            pos += 20  # 跳过当前匹配

        print(f"找到 {len(warc_response_positions)} 个WARC响应记录")

        # 解析每个响应记录
        record_count = 0
        for i, start_pos in enumerate(warc_response_positions):
            if record_count >= max_records:
                break

            # 查找WARC记录结束
            if i < len(warc_response_positions) - 1:
                end_pos = warc_response_positions[i + 1]
            else:
                end_pos = len(data_str)

            record_data = data_str[start_pos:end_pos]

            # 检查是否是HTML
            if 'Content-Type: text/html' not in record_data and \
                    'Content-Type: application/xhtml+xml' not in record_data:
                continue

            # 查找HTTP响应头后的内容
            http_header_end = record_data.find('\n\n')
            if http_header_end == -1:
                http_header_end = record_data.find('\r\n\r\n')

            if http_header_end != -1:
                html_content = record_data[http_header_end:].strip()

                # 提取字符集
                charset = 'utf-8'
                charset_match = re.search(r'charset=([^;\s]+)', record_data)
                if charset_match:
                    charset = charset_match.group(1)

                # 解码（如果之前是用错误的编码解码的，需要重新处理）
                try:
                    # 重新从原始字节中提取
                    byte_start = start_pos + http_header_end
                    byte_end = end_pos
                    html_bytes = decompressed_data[byte_start:byte_end]

                    # 尝试多种编码
                    for enc in [charset, 'utf-8', 'latin-1', 'iso-8859-1']:
                        try:
                            html_str = html_bytes.decode(enc, errors='ignore').strip()
                            break
                        except:
                            continue

                    if html_str and html_str not in seen_html:
                        seen_html.add(html_str)
                        html_list.append(html_str)
                        record_count += 1

                        if record_count % 100 == 0:
                            print(f"已提取 {record_count} 个HTML页面")

                except Exception as e:
                    continue

    except Exception as e:
        print(f"快速解析失败: {str(e)}")

    return html_list

if __name__ == '__main__':
    res = read_html_from_warc_gz_fast("/Users/wangshd/Downloads/1000004305-9873-CC-MAIN-20241113004258-20241113034258-00081.warc.gz")
    print(res)