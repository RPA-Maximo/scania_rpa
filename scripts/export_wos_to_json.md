📄 文档一：工单数据导出 JSON 工具说明
工具名称
export_wos_to_json.py

🛠️ 工具作用
本脚本用于通过 Maximo OSLC API 接口，批量抓取指定状态和时间段的历史工单。它采用“双步防卡死架构”，自动规避大表联合查询导致的超时问题。抓取完成后，会自动清洗工单主表信息以及四个费用子表（人员、材料、服务、工具）的明细，并生成标准的全英文字段 JSON 文件，供后续系统对接或归档使用。

📦 前置准备
确保安装了 Python 依赖：uv pip install requests

确保脚本同级目录下存在 wo_config.txt 配置文件，且包含最新的 API 路径和有效 Cookie。
参数,简写,是否必填,说明,默认值
--status,-s,必填,"要拉取的工单状态 (如：COMP, WAPPR, APPR)",无
--pages,-p,选填,计划抓取的总页数,3
--size,-n,选填,每页抓取的记录条数,10
--start,无,选填,历史区间查询的开始日期 (格式: YYYY-MM-DD),2025-07-01
--end,无,选填,历史区间查询的结束日期 (格式: YYYY-MM-DD),2025-07-31
--site,无,选填,指定厂区代码 (如 CN01)。若留空，脚本将自动侦测,空 (自动侦测)
💻 运行示例
示例 1：抓取 2025年7月份的 COMP 工单（前 3 页，每页 10 条）

PowerShell
uv run .\export_wos_to_json.py -s COMP -p 3 -n 10 --start 2025-07-01 --end 2025-07-31
示例 2：抓取 WAPPR 状态工单，并手动指定厂区代码为 CN01

PowerShell
uv run .\export_wos_to_json.py -s WAPPR -p 1 -n 5 --site CN01
📊 输出结果
脚本运行成功后，会在当前目录生成一个命名格式为 WOS_Export_[状态]_[日期]_[时间戳].json 的文件。