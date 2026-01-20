#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试脚本 - 转换 main.pdf 的第一页
"""

from pdf2latex import PDF2LaTeX

def main():
    print("=" * 60)
    print("PDF2LaTeX 快速测试")
    print("=" * 60)
    
    try:
        # 创建转换器
        print("\n正在初始化转换器...")
        converter = PDF2LaTeX()
        
        # 转换 main.pdf 的第一页
        print("\n开始转换 main.pdf 的第一页...")
        output_path = converter.convert_pdf(
            pdf_path="main.pdf",
            output_path="main_page1.tex",
            pages=[0],  # 只转换第一页
            add_document_wrapper=True
        )
        
        print(f"\n✓ 转换成功！")
        print(f"输出文件: {output_path}")
        
    except FileNotFoundError as e:
        print(f"\n✗ 文件未找到: {str(e)}")
        print("\n提示: 请确保当前目录下有 main.pdf 文件")
        print("或者修改脚本中的文件名为你想转换的PDF")
        
    except Exception as e:
        print(f"\n✗ 转换失败: {str(e)}")

if __name__ == "__main__":
    main()
