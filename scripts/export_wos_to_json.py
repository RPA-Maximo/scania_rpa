import requests
import os
import argparse
import json
from datetime import datetime

def read_api_config(file_path="wo_config.txt"):
    config = {}
    if not os.path.exists(file_path):
        print(f"⚠️ 找不到配置文件: {file_path}")
        return config
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                config[key.strip()] = val.strip()
    return config

# 💡 新增：自动侦测当前账户所属地点的魔法函数
def auto_detect_site(config):
    print("🕵️ 正在自动侦测当前账户所属厂区(Site ID)...")
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    
    # 找一条 WAPPR 的工单，只要它的 siteid
    params = {
        "oslc.select": "siteid",
        "oslc.where": 'status="WAPPR"',
        "oslc.pageSize": 1, # 只要 1 条就够了
        "lean": 1
    }
    
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        members = data.get("member", [])
        if members and "siteid" in members[0]:
            site_id = members[0]["siteid"]
            print(f"🎯 侦测成功！您的厂区代码为: 【 {site_id} 】")
            return site_id
    except Exception as e:
        print(f"⚠️ 自动侦测失败，将回退到全网扫描: {e}")
    return ""

def fetch_wonums_by_date(config, category_status, page_no, page_size, start_date, end_date, site_id):
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    
    where_clause = f'status="{category_status}" and changedate>="{start_date}" and changedate<="{end_date}"'
    
    # 如果侦测到了 site_id，强行加到查询条件里，速度飙升百倍！
    if site_id:
        where_clause += f' and siteid="{site_id}"'
        
    params = {
        "oslc.select": "wonum", 
        "oslc.where": where_clause,
        "oslc.pageSize": page_size,
        "pageno": page_no,
        "lean": 1 
    }
    
    print(f"🔍 [步骤 1] 抓取第 {page_no} 页 | 区间: {start_date} 至 {end_date} ...")
    
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()
        wonum_list = [item.get("wonum") for item in data.get("member", [])]
        return wonum_list
    except requests.exceptions.RequestException as e:
        print(f"❌ 获取单号失败: {e}")
        return []

def fetch_detail_by_wonum(config, wonum):
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    
    params = {
        "oslc.select": "wonum,description,glaccount,status,onbehalfof,owner,wplabor,wpmaterial,wpservice,wptool",
        "oslc.where": f'wonum="{wonum}"', 
        "lean": 1 
    }
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        members = data.get("member", [])
        return members[0] if members else None
    except requests.exceptions.RequestException:
        return None

def extract_subtable_costs(subtable_list, cost_type):
    extracted_costs = []
    if not subtable_list: return extracted_costs
    for item in subtable_list:
        cost = item.get("linecost", 0)
        if cost > 0:
            identifier = item.get("craft") or item.get("itemnum") or item.get("description") or "UNKNOWN"
            extracted_costs.append({
                "costType": cost_type,
                "identifier": identifier,
                "lineCost": cost
            })
    return extracted_costs

def main():
    parser = argparse.ArgumentParser(description="斯堪尼亚 RPA: 自动侦测地点的 JSON 导出工具")
    parser.add_argument("-s", "--status", type=str, required=True, help="[必填] 指定拉取的分类状态")
    parser.add_argument("-p", "--pages", type=int, default=3, help="抓取前几页 (默认: 3)")
    parser.add_argument("-n", "--size", type=int, default=10, help="每页条数 (默认: 10)")
    parser.add_argument("--start", type=str, default="2025-07-01", help="开始日期")
    parser.add_argument("--end", type=str, default="2025-07-31", help="结束日期")
    parser.add_argument("--site", type=str, default="", help="手动指定站点代码 (留空则自动侦测)")
    
    args = parser.parse_args()
    target_status = args.status.upper() 
    
    config = read_api_config("wo_config.txt")
    if not config: return

    print(f"🚀 启动引擎 | 状态: [{target_status}] | 时间: {args.start} 至 {args.end}")
    print("=" * 70)
    
    # 💡 核心：如果没传 site 参数，自动去偷一个！
    active_site = args.site
    if not active_site:
        active_site = auto_detect_site(config)
    
    target_wonums = []
    
    for page in range(1, args.pages + 1):
        wonums = fetch_wonums_by_date(config, target_status, page, args.size, args.start, args.end, active_site)
        if not wonums: 
            print("ℹ️ 该页无数据或请求超时，终止当前拉取。")
            break
        target_wonums.extend(wonums)
        print(f"✅ 第 {page} 页成功！拿到单号: {wonums}")
        if len(wonums) < args.size: break

    if not target_wonums:
        print("⚠️ 未找到任何满足条件的工单，程序退出。")
        return

    print("=" * 70)
    print(f"🎯 成功锁定 {len(target_wonums)} 个工单！开始逐个精准提取明细...")
    
    raw_wos = []
    for idx, wonum in enumerate(target_wonums, 1):
        print(f"   ({idx}/{len(target_wonums)}) 抓取详情: {wonum} ... ", end="", flush=True)
        detail = fetch_detail_by_wonum(config, wonum)
        if detail:
            raw_wos.append(detail)
            print("OK")
        else:
            print("FAILED")

    print("=" * 70)
    print("📊 详情抓取完毕，开始生成 JSON...")
    
    processed_wos = []
    for wo in raw_wos:
        wonum = wo.get("wonum", "UNKNOWN")
        glaccount = wo.get("glaccount", "")
        try:
            cost_center = glaccount.split("-")[2] if glaccount else ""
        except IndexError:
            cost_center = "PARSE_ERROR"

        all_costs = (extract_subtable_costs(wo.get("wplabor", []), "LABOR") + 
                     extract_subtable_costs(wo.get("wpmaterial", []), "MATERIAL") + 
                     extract_subtable_costs(wo.get("wpservice", []), "SERVICE") + 
                     extract_subtable_costs(wo.get("wptool", []), "TOOL"))
        
        wo_dict = {
            "workOrder": {
                "wonum": wonum,
                "description": wo.get("description", ""),
                "glAccount": glaccount,
                "costCenter": cost_center,
                "status": wo.get("status", ""),
                "onBehalfOf": wo.get("onbehalfof", ""),
                "owner": wo.get("owner", "")
            },
            "costDetails": all_costs,
            "totalCost": sum(item["lineCost"] for item in all_costs)
        }
        processed_wos.append(wo_dict)

    if processed_wos:
        filename = f"WOS_Export_{target_status}_{args.start}_{datetime.now().strftime('%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(processed_wos, f, ensure_ascii=False, indent=4)
        print(f"🎉 大功告成！文件已保存: 【 {filename} 】")

if __name__ == "__main__":
    main()