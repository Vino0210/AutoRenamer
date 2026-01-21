 #!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动重命名脚本：根据文件的最后修改时间，在文件名前添加日期前缀
格式：YYYYMMDD_原文件名
"""

import os
import sys
from pathlib import Path
from datetime import datetime


def rename_files_by_modification_date(folder_path):
    """
    根据文件的最后修改时间，在文件名前添加日期前缀
    
    Args:
        folder_path: 目标文件夹路径
    """
    # 转换为 Path 对象
    folder = Path(folder_path)
    
    # 检查文件夹是否存在
    if not folder.exists():
        print(f"错误：文件夹 '{folder_path}' 不存在！")
        return
    
    if not folder.is_dir():
        print(f"错误：'{folder_path}' 不是一个文件夹！")
        return
    
    # 获取文件夹中的所有文件（不包括子文件夹）
    files = [f for f in folder.iterdir() if f.is_file()]
    
    if not files:
        print(f"文件夹 '{folder_path}' 中没有文件。")
        return
    
    print(f"找到 {len(files)} 个文件，开始重命名...\n")
    
    renamed_count = 0
    skipped_count = 0
    
    for file_path in files:
        try:
            # 获取文件的最后修改时间
            mod_time = datetime.fromtimestamp(file_path.stat().st_mtime)
            
            # 格式化为 YYYYMMDD
            date_prefix = mod_time.strftime("%Y%m%d")
            
            # 获取原文件名
            original_name = file_path.name
            
            # 检查文件名是否已经包含日期前缀（避免重复添加）
            if original_name.startswith(date_prefix + "_"):
                print(f"跳过：{original_name} （已有日期前缀）")
                skipped_count += 1
                continue
            
            # 构建新文件名
            new_name = f"{date_prefix}_{original_name}"
            new_path = file_path.parent / new_name
            
            # 检查新文件名是否已存在
            if new_path.exists():
                print(f"警告：{new_name} 已存在，跳过重命名：{original_name}")
                skipped_count += 1
                continue
            
            # 重命名文件
            file_path.rename(new_path)
            print(f"✓ {original_name} -> {new_name}")
            renamed_count += 1
            
        except Exception as e:
            print(f"错误：处理文件 '{file_path.name}' 时出错: {e}")
            skipped_count += 1
    
    print(f"\n完成！")
    print(f"成功重命名：{renamed_count} 个文件")
    print(f"跳过：{skipped_count} 个文件")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        # 如果没有提供参数，使用当前目录
        folder_path = os.getcwd()
        print(f"未指定文件夹路径，使用当前目录：{folder_path}\n")
    else:
        folder_path = sys.argv[1]
    
    # 确认操作
    print(f"即将处理文件夹：{folder_path}")
    response = input("是否继续？(y/n): ").strip().lower()
    
    if response not in ['y', 'yes', '是']:
        print("操作已取消。")
        return
    
    print()
    rename_files_by_modification_date(folder_path)


if __name__ == "__main__":
    main()

