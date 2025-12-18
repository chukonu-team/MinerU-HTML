import os
import shutil

def empty_directory(directory):
    """完全清空目录（最快方法）"""
    if os.path.exists(directory):
        shutil.rmtree(directory)
        os.makedirs(directory)
    else:
        os.makedirs(directory, exist_ok=True)

def get_subdirectories(path):
    """获取指定路径下的所有子目录名称"""
    subdirs = []
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            subdirs.append(item)
    return subdirs

def has_files(directory):
    """检查目录是否包含文件（不包括子目录）"""
    if not os.path.exists(directory) or not os.path.isdir(directory):
        return False

    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isfile(item_path):
            return True
    return False