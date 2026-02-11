"""
测试 RPA 服务脚本
"""
import subprocess
import json
import sys

# 准备测试数据
test_input = {
    "po_number": "CN5123",
    "po_lines_data": [
        {"po_line": "10", "quantity": "5.00", "remark": "测试1"},
        {"po_line": "22", "quantity": "2.00", "remark": "测试2"}
    ],
    "auto_save": False
}

print("=== 测试 RPA 服务脚本 ===")
print(f"输入数据: {json.dumps(test_input, indent=2, ensure_ascii=False)}")
print()

# 调用 RPA 服务
result = subprocess.run(
    [sys.executable, "api/rpa_service.py"],
    input=json.dumps(test_input),
    capture_output=True,
    text=True,
    timeout=180
)

print(f"返回码: {result.returncode}")
print()

if result.returncode == 0:
    print("✓ 执行成功")
    print(f"输出: {result.stdout}")
    
    try:
        output = json.loads(result.stdout)
        print()
        print("解析结果:")
        print(json.dumps(output, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print(f"✗ JSON 解析失败: {e}")
else:
    print("✗ 执行失败")
    print(f"错误输出: {result.stderr}")
    print(f"标准输出: {result.stdout}")
