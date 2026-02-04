"""
查看 material 表的结构
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mysql.connector
from config import get_db_config


def check_material_table():
    """查看 material 表结构"""
    print("="*80)
    print("查看 material 表结构")
    print("="*80)
    
    try:
        db_config = get_db_config()
        print(f"\n连接数据库: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # 查看表结构
        print("\n" + "="*80)
        print("表结构")
        print("="*80)
        
        cursor.execute("DESCRIBE `material`")
        columns = cursor.fetchall()
        
        print(f"\n字段数: {len(columns)}")
        print(f"\n{'序号':<5} {'字段名':<35} {'类型':<25} {'允许NULL':<10} {'键':<10} {'默认值':<15}")
        print("-"*100)
        
        field_info = []
        for i, col in enumerate(columns, 1):
            field, type_, null, key, default, extra = col
            field_info.append({
                'name': field,
                'type': type_,
                'null': null,
                'key': key,
                'default': default
            })
            print(f"{i:<5} {field:<35} {type_:<25} {null:<10} {key:<10} {str(default):<15}")
        
        # 查看数据量
        cursor.execute("SELECT COUNT(*) FROM `material`")
        count = cursor.fetchone()[0]
        print(f"\n当前数据量: {count} 条")
        
        # 查看示例数据
        if count > 0:
            print("\n" + "="*80)
            print("示例数据 (前3条)")
            print("="*80)
            
            cursor.execute("SELECT * FROM `material` LIMIT 3")
            samples = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description]
            
            for idx, sample in enumerate(samples, 1):
                print(f"\n第 {idx} 条数据:")
                print("-"*80)
                for col_name, value in zip(col_names, sample):
                    if value is not None and value != '':
                        print(f"  {col_name:<35} = {str(value)[:60]}")
        
        # 保存字段信息到文件
        output_file = PROJECT_ROOT / "docs" / "material_table_structure.txt"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("material 表结构\n")
            f.write("="*80 + "\n\n")
            f.write(f"字段数: {len(columns)}\n")
            f.write(f"数据量: {count} 条\n\n")
            f.write(f"{'序号':<5} {'字段名':<35} {'类型':<25} {'允许NULL':<10}\n")
            f.write("-"*80 + "\n")
            for i, info in enumerate(field_info, 1):
                f.write(f"{i:<5} {info['name']:<35} {info['type']:<25} {info['null']:<10}\n")
        
        print(f"\n表结构已保存到: {output_file}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*80)
        print("✓ 查询完成")
        print("="*80)
        
        return field_info
        
    except mysql.connector.Error as e:
        print(f"\n✗ 数据库错误: {e}")
        return None
    except Exception as e:
        print(f"\n✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    check_material_table()
