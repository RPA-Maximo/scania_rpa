"""
启动 Maximo RPA API 服务

API 使用示例：
POST http://localhost:8000/api/receipt

请求体示例：
{
    "po_number": "CN5123",
    "items": [
        {
            "item_num": "20326862",
            "quantity": 2.0,
            "remark": "这是一个备注"
        },
        {
            "item_num": "20346794",
            "quantity": 3.5,
            "remark": "rpa自动处理"
        }
    ],
    "auto_save": false
}

说明：
- po_number: 采购单号（必填）
- items: 入库项列表（必填）
  - item_num 或 po_line: 二选一，推荐使用 item_num（项目号）
  - quantity: 入库数量，支持浮点数（必填）
  - remark: 备注信息（可选）
- auto_save: 是否自动保存，false 表示仅填写不保存（可选，默认 false）
"""
import uvicorn

if __name__ == "__main__":
    print("启动 Maximo RPA API 服务...")
    print("访问 http://localhost:8000/docs 查看 API 文档")
    print()
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
