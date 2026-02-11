"""
测试 API 客户端
"""
import requests
import json


def test_health():
    """测试健康检查"""
    print("=== 测试健康检查 ===")
    response = requests.get("http://localhost:8000/health")
    print(f"状态码: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    print()


def test_receipt():
    """测试入库接口"""
    print("=== 测试入库接口 ===")
    
    url = "http://localhost:8000/api/receipt"
    data = {
        "po_number": "CN5123",
        "items": [
            {
                "po_line": "10",
                "quantity": "5.00",
                "remark": "API测试-行10"
            },
            {
                "po_line": "22",
                "quantity": "2.00",
                "remark": "API测试-行22"
            }
        ],
        "auto_save": False
    }
    
    print(f"请求数据:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print()
    
    print("发送请求...")
    response = requests.post(url, json=data, timeout=120)
    
    print(f"状态码: {response.status_code}")
    print(f"响应:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    print()


if __name__ == "__main__":
    try:
        # 测试健康检查
        test_health()
        
        # 测试入库接口
        test_receipt()
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 API 服务")
        print("请先运行: python start_api.py")
    except Exception as e:
        print(f"❌ 错误: {e}")
