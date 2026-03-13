"""
公司/供应商本地缓存管理 API

当 MXAPIVENDOR 因权限不足（BMXAA0024E）无法拉取公司名称/地址时，
通过此接口手动维护 company_cache 表，同步流程自动使用缓存填充 PO 头字段。

端点：
  GET    /api/vendor-cache              查询缓存列表
  POST   /api/vendor-cache              新增或更新一条记录
  DELETE /api/vendor-cache/{code}       删除一条记录
  POST   /api/vendor-cache/batch        批量导入（JSON 数组）
"""
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.sync.company_cache import (
    load_company_cache,
    upsert_company,
    delete_company,
    list_companies,
)
from src.utils.db import get_connection

router = APIRouter(prefix="/api/vendor-cache", tags=["公司名称缓存"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class CompanyEntry(BaseModel):
    company_code:  str
    name:          Optional[str] = None
    address1:      Optional[str] = None
    address2:      Optional[str] = None
    city:          Optional[str] = None
    stateprovince: Optional[str] = None
    zip:           Optional[str] = None
    country:       Optional[str] = None
    phone1:        Optional[str] = None
    email1:        Optional[str] = None
    contact:       Optional[str] = None


# ── 接口实现 ──────────────────────────────────────────────────────────────────

@router.get("", summary="查询公司名称缓存列表")
def list_cache(
    search: Optional[str] = Query(None, description="按公司代码或名称过滤"),
):
    """
    列出 company_cache 表中所有已缓存的公司记录。

    PO 同步时会自动查此表填充 supplier_name / company_name 等字段。
    若某个公司代码不在列表中，对应 PO 的供应商字段将为空。
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        rows = list_companies(cursor, search=search)
    finally:
        cursor.close()
        conn.close()
    return {"total": len(rows), "items": rows}


@router.post("", summary="新增或更新公司名称缓存")
def upsert_cache(entry: CompanyEntry):
    """
    新增或更新一条公司缓存记录（按 company_code 主键，已存在则覆盖）。

    **用法示例（供应商）：**
    ```json
    {
      "company_code": "8970301",
      "name": "ATLAS COPCO (SHANGHAI) TRADING CO., LTD.",
      "city": "Shanghai",
      "country": "CN"
    }
    ```

    **用法示例（收款方）：**
    ```json
    {
      "company_code": "BILLTOCHINA",
      "name": "Scania China Operations",
      "address1": "某某路 100 号",
      "city": "苏州",
      "zip": "215000",
      "country": "CN"
    }
    ```

    写入后，下次 PO 同步（或 resync）时自动填充对应 PO 的 supplier_name /
    company_name / street_address 等字段。
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        ok = upsert_company(
            cursor,
            entry.company_code,
            name=entry.name,
            address1=entry.address1,
            address2=entry.address2,
            city=entry.city,
            stateprovince=entry.stateprovince,
            zip=entry.zip,
            country=entry.country,
            phone1=entry.phone1,
            email1=entry.email1,
            contact=entry.contact,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="写入缓存失败，请查看服务器日志")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"success": True, "company_code": entry.company_code, "message": "缓存已更新"}


@router.post("/batch", summary="批量导入公司名称缓存")
def batch_upsert_cache(entries: List[CompanyEntry]):
    """
    批量新增或更新公司缓存记录。

    请求体为 JSON 数组，示例：
    ```json
    [
      {"company_code": "8970301", "name": "ATLAS COPCO ...", "city": "Shanghai"},
      {"company_code": "BILLTOCHINA", "name": "Scania China", "city": "苏州"}
    ]
    ```
    """
    if not entries:
        return {"success": True, "upserted": 0}

    conn = get_connection()
    cursor = conn.cursor()
    failed = []
    try:
        for entry in entries:
            ok = upsert_company(
                cursor,
                entry.company_code,
                name=entry.name,
                address1=entry.address1,
                address2=entry.address2,
                city=entry.city,
                stateprovince=entry.stateprovince,
                zip=entry.zip,
                country=entry.country,
                phone1=entry.phone1,
                email1=entry.email1,
                contact=entry.contact,
            )
            if not ok:
                failed.append(entry.company_code)
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    upserted = len(entries) - len(failed)
    result = {"success": True, "upserted": upserted}
    if failed:
        result["failed"] = failed
    return result


@router.delete("/{company_code}", summary="删除公司名称缓存")
def delete_cache(company_code: str):
    """删除 company_cache 中指定公司代码的记录"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        ok = delete_company(cursor, company_code)
        if not ok:
            raise HTTPException(status_code=500, detail="删除失败，请查看服务器日志")
        conn.commit()
    finally:
        cursor.close()
        conn.close()
    return {"success": True, "company_code": company_code, "message": "已删除"}
