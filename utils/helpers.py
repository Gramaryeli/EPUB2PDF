# utils/helpers.py
import re

def sanitize_filename(name):
    """清洗文件名，移除非法字符"""
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return name[:50]