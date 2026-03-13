"""
数据库工具模块
提供数据库连接、ID生成、日期格式化等功能
"""
import sys
from pathlib import Path
from datetime import datetime
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import threading

import mysql.connector
from config.auth import get_db_config

# 线程安全序列号（替换随机数，避免批量生成 ID 时碰撞）
_id_lock = threading.Lock()
_id_seq = 0


def get_connection():
    """
    获取数据库连接

    Returns:
        Connection: MySQL 连接对象
    """
    config = get_db_config()
    return mysql.connector.connect(**config)


def generate_id() -> int:
    """
    生成唯一 ID（时间戳毫秒 × 10000 + 进程内单调递增序列号）

    序列号范围 0-9999，即同一毫秒内可生成 10000 个不重复 ID。
    线程安全，适合批量预生成场景（如 batch_map_details 一次生成 70+ 行 ID）。
    """
    global _id_seq
    timestamp = int(datetime.now().timestamp() * 1000)
    with _id_lock:
        _id_seq = (_id_seq + 1) % 10000
        seq = _id_seq
    return timestamp * 10000 + seq


def format_datetime(dt_str: str) -> str:
    """
    格式化日期时间字符串
    
    Args:
        dt_str: ISO 格式的日期时间字符串
        
    Returns:
        str: MySQL 格式的日期时间字符串
    """
    if not dt_str:
        return None
    # 处理 ISO 格式: 2025-12-25T07:33:49+00:00
    try:
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('+00:00', '+0000').replace('Z', '+0000'))
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return dt_str
    except:
        return dt_str


def execute_batch_insert(cursor, table: str, data_list: list, batch_size: int = 100) -> int:
    """
    批量插入数据
    
    Args:
        cursor: 数据库游标
        table: 表名
        data_list: 数据列表，每个元素是一个字典
        batch_size: 批量大小
        
    Returns:
        int: 成功插入的数量
    """
    if not data_list:
        return 0
    
    success_count = 0
    
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i+batch_size]
        
        # 使用第一条数据的键作为列名
        columns = ', '.join(batch[0].keys())
        placeholders = ', '.join(['%s'] * len(batch[0]))
        insert_sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        # 准备批量数据
        batch_values = [list(item.values()) for item in batch]
        
        try:
            cursor.executemany(insert_sql, batch_values)
            success_count += len(batch)
        except mysql.connector.Error as e:
            print(f"[WARN] 批量插入失败: {e}")
            # 尝试逐条插入
            for item in batch:
                try:
                    cursor.execute(insert_sql, list(item.values()))
                    success_count += 1
                except mysql.connector.Error:
                    pass
    
    return success_count
