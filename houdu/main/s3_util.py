import os
import re

import boto3
from botocore.config import Config

from botocore.exceptions import ClientError
from obs import PutObjectHeader, ObsClient


def init_obs_cli(func):
    def wrapper(self, *args, **kwargs):
        self.init()
        res = func(self, *args, **kwargs)
        return res

    return wrapper


class OBSCli:
    def __init__(self, bucket_name, server=None, ak=None, sk=None,region=None):
        self.bucket_name = bucket_name
        self.server = server
        self.ak = ak
        self.sk = sk
        self.obs_cli = None
        self.region = region

    def init(self):
        if self.obs_cli:
            return
        ak = self.ak
        sk = self.sk
        server = self.server
        region = self.region
        # 创建obsClient实例
        obs_cli = ObsClient(
            access_key_id=ak,
            secret_access_key=sk,
            server=server,
            is_cname=True,
            region=region,
            signature='v4',
            max_retry_count=3,
            timeout=120
        )
        self.obs_cli = obs_cli

    def close(self):
        if self.obs_cli:
            # 关闭obsClient
            self.obs_cli.close()

    @init_obs_cli
    def get_object(self, bucket_key, local_path):
        # 下载对象到本地
        resp = self.obs_cli.getObject(self.bucket_name, bucket_key, local_path)
        # 返回码为2xx时，接口调用成功，否则接口调用失败
        if resp.status >= 300:
            print('get object Failed')
            print('requestId:', resp.requestId)
            print('errorCode:', resp.errorCode)
            print('errorMessage:', resp.errorMessage)
            print('resp:', resp)
            raise Exception()

    @init_obs_cli
    def get_object_meta(self, bucket_key):
        resp = self.obs_cli.getObjectMetadata(self.bucket_name, bucket_key)
        # 返回码为2xx时，接口调用成功，否则接口调用失败
        if resp.status >= 300:
            print('get object Failed')
            print('requestId:', resp.requestId)
            print('errorCode:', resp.errorCode)
            print('errorMessage:', resp.errorMessage)
        return dict(resp.body)

    @init_obs_cli
    def exist_object(self, bucket_key):
        resp = self.obs_cli.getObjectMetadata(self.bucket_name, bucket_key)
        if resp.status >= 300:
            return False
        return True

    def standard_key(self, origin_key: str):
        if origin_key.startswith("obs://"):
            return re.sub(r"obs://.*?/", '', origin_key)
        elif origin_key.startswith(self.bucket_name):
            return origin_key.replace(f"{self.bucket_name}/", "", 1)
        elif origin_key.startswith("/"):
            raise ValueError("对象名不能以 '/' 开头")

        return origin_key

    @init_obs_cli
    def put_object(self, bucket_key, local_path):
        objectkey = self.standard_key(bucket_key)
        try:
            # 待上传文件的完整路径，如aa/bb.txt
            file_path = local_path
            # 分段上传的并发数
            taskNum = 10
            # 分段的大小，单位字节
            partSize = 50 * 1024 * 1024
            # True表示开启断点续传
            enableCheckpoint = False
            headers = PutObjectHeader()
            # 【可选】设置校验crc64
            isAttachCrc64 = True
            if self.bucket_name in ["mb-serverless-spark"]:
                isAttachCrc64 = False
            headers.isAttachCrc64 = isAttachCrc64
            # 上传文件
            resp = self.obs_cli.uploadFile(self.bucket_name, objectkey, file_path, partSize, taskNum, enableCheckpoint,
                                           isAttachCrc64=isAttachCrc64)  # 返回码为2xx时，接口调用成功，否则接口调用失败
            if resp.status < 300:
                # print('Upload File Succeeded')
                # print('requestId:', resp.requestId)
                # print('crc64:', resp.body.crc64)
                return resp.body
            else:
                print(f'Upload File Failed local_file:{local_path} target bucket_key:{bucket_key}')
                print('requestId:', resp.requestId)
                print('errorCode:', resp.errorCode)
                print('errorMessage:', resp.errorMessage)
        except Exception as e:
            print(f'Upload File Failed local_file:{local_path} target bucket_key:{bucket_key}')
            print(e)

def get_s3_client():
    """创建配置了自定义端点的S3客户端"""
    s3_client = None
    s3_type = os.environ.get('S3_TYPE','s3')
    endpoint_url = os.getenv('AWS_ENDPOINT')
    aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region_name = os.getenv('AWS_DEFAULT_REGION')
    bucket_name = os.getenv("S3_BUCKET")
    if s3_type == 's3':
        s3_client =  boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
    elif s3_type == 'obs':
        s3_client = OBSCli(
            bucket_name=bucket_name,
            server=endpoint_url,
            ak=aws_access_key_id,
            sk=aws_secret_access_key,
            region=region_name
        )
    elif s3_type == 'oss':
        config = Config(
            s3={
                "addressing_style": "virtual",
            },
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required"
        )
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
            config=config
        )

    return s3_client

def download_from_s3(bucket_name, key, local_path):
    """从S3下载文件到本地"""
    s3_client = get_s3_client()
    s3_type = os.environ.get('S3_TYPE','s3')
    try:
        if s3_type == 's3' or s3_type == 'oss':
            s3_client.download_file(bucket_name, key, local_path)
        elif s3_type == 'obs':
            s3_client.get_object(key, local_path)
            s3_client.close()
        print(f"Downloaded {key} to {local_path}")
    except ClientError as e:
        print(f"Error downloading {key} from S3: {e}")
        raise

def upload_to_s3(local_path, bucket_name, key):
    """上传文件到S3"""
    s3_client = get_s3_client()
    s3_type = os.environ.get('S3_TYPE', 's3')
    try:
        if s3_type == 's3' or s3_type == 'oss':
            s3_client.upload_file(local_path, bucket_name, key)
        elif s3_type == 'obs':
            s3_client.put_object(key,local_path)
        print(f"Uploaded {local_path} to {key}")
    except ClientError as e:
        print(f"Error uploading {local_path} to S3: {e}")
        raise

def check_result_exists(bucket_name: str, result_key: str) -> bool:
    """检查S3上结果文件是否已存在"""
    s3_client = get_s3_client()
    s3_type = os.environ.get('S3_TYPE', 's3')
    try:
        if s3_type == 's3' or s3_type == 'oss':
            s3_client.head_object(Bucket=bucket_name, Key=result_key)
        elif s3_type == 'obs':
            return s3_client.exist_object(result_key)
        print(f"Result already exists: {result_key}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            print(f"Error checking result existence: {e}")
            raise