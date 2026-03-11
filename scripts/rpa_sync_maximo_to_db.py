import requests
import os
import argparse
import json
import pymysql
from datetime import datetime

# ==========================================
# 1. 数据库配置
# ==========================================
DB_CONFIG = {
    "host": "222.187.11.98",
    "port": 33060,
    "user": "bmp153",
    "password": "45bSnyonIhPk3rsTOSLi",
    "database": "bmp153",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# ==========================================
# 2. Maximo API 获取逻辑
# ==========================================
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

def auto_detect_site(config):
    print("🕵️ [1/4] 正在自动侦测当前账户所属厂区(Site ID)...")
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    params = {"oslc.select": "siteid", "oslc.where": 'status="WAPPR"', "oslc.pageSize": 1, "lean": 1}
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        members = data.get("member", [])
        if members and "siteid" in members[0]:
            site_id = members[0]["siteid"]
            print(f"   🎯 侦测成功！您的厂区代码为: 【 {site_id} 】")
            return site_id
    except Exception as e:
        print(f"   ⚠️ 自动侦测失败，将回退到全网扫描: {e}")
    return ""

def fetch_wonums_by_date(config, category_status, page_no, page_size, start_date, end_date, site_id):
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    where_clause = f'status="{category_status}" and changedate>="{start_date}" and changedate<="{end_date}"'
    if site_id: where_clause += f' and siteid="{site_id}"'
        
    params = {"oslc.select": "wonum", "oslc.where": where_clause, "oslc.pageSize": page_size, "pageno": page_no, "lean": 1}
    print(f"   -> 抓取第 {page_no} 页单号 ...")
    try:
        response = requests.get(base_url, headers=headers, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()
        return [item.get("wonum") for item in data.get("member", [])]
    except requests.exceptions.RequestException as e:
        print(f"   ❌ 获取单号失败: {e}")
        return []

def fetch_detail_by_wonum(config, wonum):
    base_url = "https://main.manage.scania-acc.suite.maximo.com/maximo/oslc/os/mxapiwodetail"
    headers = {"Accept": "application/json", "Cookie": config.get("COOKIE", "")}
    params = {"oslc.select": "wonum,description,glaccount,status,onbehalfof,owner,wplabor,wpmaterial,wpservice,wptool", "oslc.where": f'wonum="{wonum}"', "lean": 1}
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
            extracted_costs.append({"costType": cost_type, "identifier": identifier, "lineCost": cost})
    return extracted_costs

# ==========================================
# 3. 数据库入库逻辑
# ==========================================
def init_database_tables(connection):
    with connection.cursor() as cursor:
        sql_create_main = """
        CREATE TABLE IF NOT EXISTS work_order (
            wonum VARCHAR(50) PRIMARY KEY COMMENT '工单号',
            description TEXT COMMENT '工单描述',
            gl_account VARCHAR(100) COMMENT '完整GL科目',
            cost_center VARCHAR(50) COMMENT '成本中心',
            status VARCHAR(20) COMMENT '状态',
            on_behalf_of VARCHAR(100) COMMENT '代表(审批人)',
            owner VARCHAR(100) COMMENT '负责人',
            total_cost DECIMAL(10, 2) DEFAULT 0.00 COMMENT '总费用'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA_工单主表';
        """
        cursor.execute(sql_create_main)
        
        sql_create_sub = """
        CREATE TABLE IF NOT EXISTS work_order_cost (
            id INT AUTO_INCREMENT PRIMARY KEY,
            wonum VARCHAR(50) COMMENT '关联的工单号',
            cost_type VARCHAR(50) COMMENT '费用类型',
            identifier VARCHAR(255) COMMENT '工种或物料标识',
            line_cost DECIMAL(10, 2) DEFAULT 0.00 COMMENT '具体金额',
            FOREIGN KEY (wonum) REFERENCES work_order(wonum) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RPA_工单费用子表';
        """
        cursor.execute(sql_create_sub)
    connection.commit()

def insert_data_to_db(connection, json_data):
    inserted_main = 0
    inserted_sub = 0
    
    with connection.cursor() as cursor:
        for item in json_data:
            wo = item.get("workOrder", {})
            costs = item.get("costDetails", [])
            total_cost = item.get("totalCost", 0)
            wonum = wo.get("wonum")
            
            if not wonum or wonum == "UNKNOWN": continue
                
            # 主表 UPSERT (存在则更新，不存在则插入)
            sql_insert_main = """
                INSERT INTO work_order (wonum, description, gl_account, cost_center, status, on_behalf_of, owner, total_cost)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                description=VALUES(description), gl_account=VALUES(gl_account), cost_center=VALUES(cost_center), 
                status=VALUES(status), on_behalf_of=VALUES(on_behalf_of), owner=VALUES(owner), total_cost=VALUES(total_cost)
            """
            cursor.execute(sql_insert_main, (
                wonum, wo.get("description", ""), wo.get("glAccount", ""), wo.get("costCenter", ""),
                wo.get("status", ""), wo.get("onBehalfOf", ""), wo.get("owner", ""), total_cost
            ))
            inserted_main += 1
            
            # 子表刷新 (先删后插，保证幂等)
            cursor.execute("DELETE FROM work_order_cost WHERE wonum = %s", (wonum,))
            if costs:
                sql_insert_sub = "INSERT INTO work_order_cost (wonum, cost_type, identifier, line_cost) VALUES (%s, %s, %s, %s)"
                sub_data = [(wonum, c.get("costType"), c.get("identifier"), c.get("lineCost")) for c in costs]
                cursor.executemany(sql_insert_sub, sub_data)
                inserted_sub += len(sub_data)
                
    connection.commit()
    print(f"   ✅ 成功处理主表记录: {inserted_main} 条")
    print(f"   ✅ 成功插入子表费用: {inserted_sub} 条")

# ==========================================
# 4. 主干编排流程
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="斯堪尼亚 RPA: 抓取 -> JSON -> 入库 终极自动化引擎")
    parser.add_argument("-s", "--status", type=str, required=True, help="工单状态 (如 COMP, WAPPR)")
    parser.add_argument("-p", "--pages", type=int, default=3, help="抓取前几页 (默认: 3)")
    parser.add_argument("-n", "--size", type=int, default=10, help="每页条数 (默认: 10)")
    parser.add_argument("--start", type=str, default="2025-07-01", help="开始日期")
    parser.add_argument("--end", type=str, default="2025-07-31", help="结束日期")
    parser.add_argument("--site", type=str, default="", help="手动指定站点 (留空自动侦测)")
    
    args = parser.parse_args()
    target_status = args.status.upper() 
    
    config = read_api_config("wo_config.txt")
    if not config: return

    print(f"\n=======================================================")
    print(f" 🚀 RPA 自动化管线启动 | 目标: {target_status} | {args.start} 至 {args.end}")
    print(f"=======================================================\n")
    
    # 步骤 1：侦测地点
    active_site = args.site if args.site else auto_detect_site(config)
    
    # 步骤 2：获取单号
    print("\n📦 [2/4] 正在拉取符合条件的工单号池...")
    target_wonums = []
    for page in range(1, args.pages + 1):
        wonums = fetch_wonums_by_date(config, target_status, page, args.size, args.start, args.end, active_site)
        if not wonums: break
        target_wonums.extend(wonums)
        if len(wonums) < args.size: break

    if not target_wonums:
        print("⚠️ 未抓取到任何有效工单，任务结束。")
        return
        
    # 步骤 3：获取详情并清洗组装
    print(f"\n🔍 [3/4] 成功锁定 {len(target_wonums)} 个单号，开始提取详情与子表费用...")
    processed_wos = []
    for idx, wonum in enumerate(target_wonums, 1):
        print(f"   ({idx}/{len(target_wonums)}) 提取: {wonum} ... ", end="", flush=True)
        detail = fetch_detail_by_wonum(config, wonum)
        if detail:
            glaccount = detail.get("glaccount", "")
            try: cost_center = glaccount.split("-")[2] if glaccount else ""
            except IndexError: cost_center = "PARSE_ERROR"

            all_costs = (extract_subtable_costs(detail.get("wplabor", []), "LABOR") + 
                         extract_subtable_costs(detail.get("wpmaterial", []), "MATERIAL") + 
                         extract_subtable_costs(detail.get("wpservice", []), "SERVICE") + 
                         extract_subtable_costs(detail.get("wptool", []), "TOOL"))
            
            processed_wos.append({
                "workOrder": {
                    "wonum": detail.get("wonum", "UNKNOWN"), "description": detail.get("description", ""),
                    "glAccount": glaccount, "costCenter": cost_center, "status": detail.get("status", ""),
                    "onBehalfOf": detail.get("onbehalfof", ""), "owner": detail.get("owner", "")
                },
                "costDetails": all_costs,
                "totalCost": sum(item["lineCost"] for item in all_costs)
            })
            print("OK")
        else:
            print("FAILED")

    # 步骤 4：本地备份与写入数据库
    print("\n💾 [4/4] 正在进行本地备份与远程数据库同步...")
    
    # 4.1 存为本地 JSON
    filename = f"WOS_SyncBackup_{target_status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(processed_wos, f, ensure_ascii=False, indent=4)
    print(f"   📄 本地审计日志已保存: {filename}")
    
    # 4.2 直连 MySQL 入库
    print("   🔗 正在连接目标数据库 222.187.11.98 ...")
    connection = None
    try:
        connection = pymysql.connect(**DB_CONFIG)
        init_database_tables(connection)
        insert_data_to_db(connection, processed_wos)
        print("\n🎉 RPA 自动化全流程执行完毕！数据已完美落库！")
    except pymysql.MySQLError as e:
        print(f"\n❌ 数据库写入失败: {e}")
    finally:
        if connection: connection.close()

if __name__ == "__main__":
    main()