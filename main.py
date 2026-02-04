"""
Scannia RPA 主入口
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.main import main as sync_main


def main():
    """主函数"""
    print("Scannia 采购订单同步系统")
    print("="*60)
    print()
    print("启动同步流程...")
    
    # 调用同步主流程
    success = sync_main()
    
    if success:
        print("\n✓ 同步完成")
    else:
        print("\n✗ 同步失败")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
