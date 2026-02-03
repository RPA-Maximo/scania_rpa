"""
测试认证信息解析功能
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.auth import parse_curl_file, get_maximo_auth


def test_parse_curl_file():
    """测试从 curl 文件解析认证信息"""
    print("=" * 60)
    print("测试从 响应标头.txt 解析认证信息")
    print("=" * 60)
    
    auth_info = parse_curl_file()
    
    if auth_info:
        print("\n✓ 解析成功！\n")
        print(f"Cookie 长度: {len(auth_info['cookie'])} 字符")
        print(f"Cookie 前100字符: {auth_info['cookie'][:100]}...")
        print(f"\nCSRF Token: {auth_info['csrf_token']}")
        print(f"Refresh Token: {auth_info['refresh_token'][:50]}..." if auth_info['refresh_token'] else "Refresh Token: (未找到)")
    else:
        print("\n✗ 解析失败！")
        print("请检查 config/响应标头.txt 文件是否存在且格式正确")


def test_get_maximo_auth():
    """测试获取认证信息（优先从 curl 文件）"""
    print("\n" + "=" * 60)
    print("测试 get_maximo_auth() 函数")
    print("=" * 60)
    
    try:
        auth_info = get_maximo_auth()
        print("\n✓ 获取认证信息成功！\n")
        print(f"Cookie 长度: {len(auth_info['cookie'])} 字符")
        print(f"CSRF Token: {auth_info['csrf_token']}")
        print(f"Refresh Token 长度: {len(auth_info['refresh_token'])} 字符" if auth_info['refresh_token'] else "Refresh Token: (未设置)")
    except ValueError as e:
        print(f"\n✗ 获取认证信息失败: {e}")


if __name__ == "__main__":
    test_parse_curl_file()
    test_get_maximo_auth()
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
