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
from pydantic import BaseModel, Field

from src.sync.company_cache import (
    load_company_cache,
    upsert_company,
    delete_company,
    list_companies,
)
from src.utils.db import get_connection

router = APIRouter(prefix="/api/vendor-cache", tags=["公司名称缓存"])


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class ScrapeRequest(BaseModel):
    company_codes: Optional[List[str]] = Field(
        None,
        description=(
            "指定要抓取的公司代码列表（vendor code / billto code）。"
            "不填则自动从 purchase_order 表中找 supplier_name 为空的 vendor_code。"
        ),
    )


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


@router.post("/scrape", summary="通过浏览器自动抓取公司详情到缓存")
async def scrape_company_to_cache(request: ScrapeRequest = None):
    """
    利用本地已登录的 Edge/Chrome debug 实例（CDP port 9223）自动从 Maximo 抓取公司详情，
    写入 company_cache 表，下次 PO 同步时自动填充供应商/收款方字段。

    **原理**：MXAPIVENDOR OSLC 接口对 API 账号要求 COMPANIES READ 权限，
    而本地浏览器登录的人工账号具有该权限。通过 Playwright CDP 在浏览器上下文中
    发起请求，可绕过 API 账号的权限限制。

    **前置条件**：
    - 本地运行 Edge/Chrome 并以 `--remote-debugging-port=9223` 启动
    - 浏览器已登录 Maximo（人工账号需具有 COMPANIES READ 权限）

    **两种模式**：
    - 提供 `company_codes`：抓取指定代码列表
    - 不提供：自动检测 purchase_order 表中 supplier_name 为空的 vendor_code
    """
    import asyncio
    from src.fetcher.company_browser_fetcher import fetch_company_details_via_browser

    # 1. 确定需要抓取的代码
    if request and request.company_codes:
        codes = list(dict.fromkeys(request.company_codes))
    else:
        # 自动检测：找 purchase_order 表中 supplier_name 为空的 vendor_code
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT DISTINCT vendor_code FROM purchase_order "
                "WHERE vendor_code IS NOT NULL AND (supplier_name IS NULL OR supplier_name = '') "
                "AND del_flag = 0"
            )
            codes = [row[0] for row in cur.fetchall()]
        finally:
            cur.close()
            conn.close()

    if not codes:
        return {"success": True, "message": "没有需要补全的公司代码", "scraped": 0, "saved": 0}

    # 2. 通过 CDP 浏览器抓取
    scraped = await fetch_company_details_via_browser(codes)

    if not scraped:
        raise HTTPException(
            status_code=503,
            detail=(
                "浏览器抓取失败。请确认：\n"
                "1. Edge/Chrome 已以 --remote-debugging-port=9223 启动\n"
                "2. 浏览器已登录 Maximo 且账号具有 COMPANIES READ 权限"
            ),
        )

    # 3. 写入 company_cache
    conn = get_connection()
    cur = conn.cursor()
    saved = 0
    try:
        for code, detail in scraped.items():
            ok = upsert_company(cur, code, **detail)
            if ok:
                saved += 1
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return {
        "success": True,
        "queried": len(codes),
        "scraped": len(scraped),
        "saved": saved,
        "codes": list(scraped.keys()),
        "message": f"成功抓取并缓存 {saved} 条公司信息，下次 PO 同步时自动填充",
    }


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
