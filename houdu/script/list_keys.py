import argparse
import os

import boto3
from botocore.config import Config


def get_s3_client(endpoint_url, access_key_id, secret_access_key, region_name):
    """创建配置了自定义端点的S3客户端"""
    config = None
    s3_type = os.environ.get('S3_TYPE','s3')
    if s3_type != 's3':
        config = Config(
            s3={
                "addressing_style": "virtual",
            },
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required"
        )
    s3_client =  boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
        config=config
    )
    return s3_client


def list_all_keys_to_file(endpoint_url, access_key_id, secret_access_key, region_name,bucket_name, prefix, output_file):
    """
    列出指定S3存储桶中的所有对象键，并写入到文本文件

    :param bucket_name: 存储桶名称
    :param output_file: 输出的文本文件名
    """
    # 创建S3客户端 [citation:1]
    s3_client = get_s3_client(endpoint_url, access_key_id, secret_access_key, region_name)

    keys_list = []  # 存储所有Key的列表
    continuation_token = None  # 用于分页的ContinuationToken

    # 循环分页获取所有对象 [citation:4]
    while True:
        # 准备请求参数
        list_kwargs = {
            'Prefix': prefix,
            'Bucket': bucket_name,
            'MaxKeys': 1000  # 单次请求最多返回1000个对象
        }
        # 如果存在ContinuationToken，则添加到请求参数中
        if continuation_token:
            list_kwargs['ContinuationToken'] = continuation_token

        # 发送列表对象请求
        response = s3_client.list_objects_v2(**list_kwargs)

        # 如果响应中包含Contents，则提取Key
        if 'Contents' in response:
            for obj in response['Contents']:
                keys_list.append(obj['Key'])  # 将Key添加到列表 [citation:1]

        # 检查是否还有更多结果，有则设置ContinuationToken继续获取 [citation:4]
        if response.get('IsTruncated'):
            continuation_token = response.get('NextContinuationToken')
        else:
            break

    # 将所有Key写入文本文件
    with open(output_file, 'w') as f:
        for key in keys_list:
            f.write(f"{key}\n")

    print(f"成功列出 {len(keys_list)} 个对象Key，并保存到 {output_file}")


def add_prefix(input,prefix,output):
    url_list = []
    with open(input, 'r', encoding='utf-8') as f:
        for url in f:
            url = url.strip()
            url = f'{prefix}{url}'
            url_list.append(url)

    with open(output, 'w', encoding='utf-8') as f:
        for url in url_list:
            f.write(url + '\n')

if __name__ == '__main__':
    print("list_keys")
    endpoint_url="https://s3.us-east-1.amazonaws.com"
    access_key_id=""
    secret_access_key=""
    region_name="us-east-1"
    bucket_name="houdu"
    prefix="mb/cc-result/CC-MAIN-2024-46"
    list_output_file="/root/mineru-html/keys/list_key_CC-MAIN-2024-46.txt"
    list_all_keys_to_file(endpoint_url, access_key_id, secret_access_key, region_name,bucket_name, prefix, list_output_file)

    output="/root/wangshd/batch6/keys/CC-MAIN-2024-46.txt"
    bucket_prefix = "s3://houdu/"
    add_prefix(list_output_file,bucket_prefix,output)
