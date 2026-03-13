"""
公司/供应商本地缓存操作
读写 company_cache 表，供 fetch_vendor_details 用作 MXAPIVENDOR 的备用数据源

用法：
    from src.sync.company_cache import load_company_cache, upsert_company, list_companies

    # 批量加载（传入 company_code 列表，返回 dict）
    cache = load_company_cache(cursor, ['8970301', 'BILLTOCHINA'])

    # 新增或更新一条记录
    upsert_company(cursor, '8970301', name='ATLAS COPCO', city='Shanghai')
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 与 company_cache 表对应的所有可写字段
_FIELDS = ('name', 'address1', 'address2', 'city', 'stateprovince',
           'zip', 'country', 'phone1', 'email1', 'contact')


def load_company_cache(cursor, company_codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    批量从 company_cache 表加载公司详情。

    Args:
        cursor:        数据库游标
        company_codes: 公司代码列表

    Returns:
        {company_code: {name, address1, address2, city, stateprovince,
                        zip, country, phone1, email1, contact}}
        未找到的代码不会出现在结果中。
    """
    if not company_codes:
        return {}

    placeholders = ','.join(['%s'] * len(company_codes))
    try:
        cursor.execute(
            f"SELECT company_code,name,address1,address2,city,stateprovince,"
            f"zip,country,phone1,email1,contact "
            f"FROM company_cache WHERE company_code IN ({placeholders})",
            tuple(company_codes),
        )
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[WARN] load_company_cache: 查询失败: {e}")
        return {}

    result = {}
    for row in rows:
        code = row[0]
        result[code] = {
            'name':          row[1],
            'address1':      row[2],
            'address2':      row[3],
            'city':          row[4],
            'stateprovince': row[5],
            'zip':           row[6],
            'country':       row[7],
            'phone1':        row[8],
            'email1':        row[9],
            'contact':       row[10],
        }
    return result


def upsert_company(cursor, company_code: str, **kwargs) -> bool:
    """
    新增或更新 company_cache 中一条记录（INSERT … ON DUPLICATE KEY UPDATE）。

    Args:
        cursor:       数据库游标
        company_code: 公司代码（主键）
        **kwargs:     字段值，键名为 name/address1/address2/city/
                      stateprovince/zip/country/phone1/email1/contact

    Returns:
        True = 成功；False = 失败（已打印警告）
    """
    data = {k: v for k, v in kwargs.items() if k in _FIELDS}
    data['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    set_clause = ', '.join(f"`{k}` = %s" for k in data)
    values = list(data.values())

    try:
        cursor.execute(
            f"INSERT INTO company_cache (company_code, {', '.join(f'`{k}`' for k in data)}) "
            f"VALUES (%s, {', '.join(['%s'] * len(data))}) "
            f"ON DUPLICATE KEY UPDATE {set_clause}",
            [company_code] + values + values,
        )
        return True
    except Exception as e:
        print(f"[WARN] upsert_company: 写入 {company_code} 失败: {e}")
        return False


def delete_company(cursor, company_code: str) -> bool:
    """从 company_cache 删除一条记录"""
    try:
        cursor.execute(
            "DELETE FROM company_cache WHERE company_code = %s",
            (company_code,),
        )
        return True
    except Exception as e:
        print(f"[WARN] delete_company: 删除 {company_code} 失败: {e}")
        return False


def list_companies(cursor, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    列出 company_cache 中的所有记录。

    Args:
        cursor: 数据库游标
        search: 可选关键词（对 company_code 和 name 做 LIKE 过滤）

    Returns:
        记录列表，按 company_code 排序
    """
    try:
        if search:
            like = f"%{search}%"
            cursor.execute(
                "SELECT company_code,name,address1,address2,city,stateprovince,"
                "zip,country,phone1,email1,contact,updated_at "
                "FROM company_cache "
                "WHERE company_code LIKE %s OR name LIKE %s "
                "ORDER BY company_code",
                (like, like),
            )
        else:
            cursor.execute(
                "SELECT company_code,name,address1,address2,city,stateprovince,"
                "zip,country,phone1,email1,contact,updated_at "
                "FROM company_cache ORDER BY company_code"
            )
        rows = cursor.fetchall()
    except Exception as e:
        print(f"[WARN] list_companies: 查询失败: {e}")
        return []

    result = []
    for row in rows:
        result.append({
            'company_code':  row[0],
            'name':          row[1],
            'address1':      row[2],
            'address2':      row[3],
            'city':          row[4],
            'stateprovince': row[5],
            'zip':           row[6],
            'country':       row[7],
            'phone1':        row[8],
            'email1':        row[9],
            'contact':       row[10],
            'updated_at':    str(row[11]) if row[11] else None,
        })
    return result
