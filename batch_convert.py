#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量转换示例脚本
批量将当前目录下的所有PDF文件转换为LaTeX格式
"""

import os
from pathlib import Path
from pdf2latex import PDF2LaTeX


def main():
    """批量转换PDF文件"""
    # 创建转换器
    converter = PDF2LaTeX()
    
    # 获取当前目录下所有PDF文件
    current_dir = Path(".")
    pdf_files = list(current_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("当前目录下没有找到PDF文件")
        return
    
    print(f"找到 {len(pdf_files)} 个PDF文件\n")
    
    # 创建输出目录
    output_dir = current_dir / "latex_output"
    output_dir.mkdir(exist_ok=True)
    
    # 批量转换
    success_count = 0
    failed_files = []
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(pdf_files)}] 正在转换: {pdf_file.name}")
        print('='*60)
        
        try:
            output_path = output_dir / f"{pdf_file.stem}.tex"
            converter.convert_pdf(
                pdf_path=str(pdf_file),
                output_path=str(output_path)
            )
            success_count += 1
            
        except Exception as e:
            print(f"转换失败: {str(e)}")
            failed_files.append(pdf_file.name)
    
    # 输出总结
    print(f"\n{'='*60}")
    print("批量转换完成！")
    print(f"{'='*60}")
    print(f"成功: {success_count}/{len(pdf_files)}")
    
    if failed_files:
        print(f"\n失败的文件:")
        for filename in failed_files:
            print(f"  - {filename}")
    
    print(f"\n输出目录: {output_dir}")


if __name__ == "__main__":
    main()
