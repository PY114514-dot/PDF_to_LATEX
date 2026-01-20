#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF翻译转LaTeX工具 - 快捷脚本
先将PDF内容翻译成中文，再转换为LaTeX格式
"""

import sys
import argparse
from pathlib import Path
from pdf2latex import PDF2LaTeX


def main():
    """翻译转换命令行入口"""
    parser = argparse.ArgumentParser(
        description="PDF 翻译并转 LaTeX 工具 (使用 DeepSeek API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 翻译整个PDF文件并转换
  python pdf2latex_translate.py input.pdf
  
  # 指定输出文件
  python pdf2latex_translate.py input.pdf -o output_cn.tex
  
  # 只翻译转换前3页
  python pdf2latex_translate.py input.pdf -p 1 2 3
  
  # 批量翻译当前目录所有PDF
  python pdf2latex_translate.py --batch
        """
    )
    
    parser.add_argument(
        "pdf_file",
        nargs="?",
        help="输入的PDF文件路径"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="输出的LaTeX文件路径（默认：与PDF同名加_cn后缀的.tex文件）"
    )
    
    parser.add_argument(
        "-p", "--pages",
        type=int,
        nargs="+",
        help="要翻译转换的页码（从1开始，可指定多个）"
    )
    
    parser.add_argument(
        "--no-wrapper",
        action="store_true",
        help="不添加LaTeX文档结构"
    )
    
    parser.add_argument(
        "--api-key",
        help="DeepSeek API密钥"
    )
    
    parser.add_argument(
        "--model",
        default="deepseek-chat",
        help="使用的模型（默认：deepseek-chat）"
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        help="批量翻译当前目录所有PDF文件"
    )
    
    args = parser.parse_args()
    
    # 批量处理模式
    if args.batch:
        batch_translate()
        return
    
    # 单文件处理模式
    if not args.pdf_file:
        parser.print_help()
        sys.exit(1)
    
    try:
        # 创建转换器
        converter = PDF2LaTeX(api_key=args.api_key, model=args.model)
        
        # 转换页码
        pages = None
        if args.pages:
            pages = [p - 1 for p in args.pages]
        
        # 执行翻译转换
        output_path = converter.convert_pdf(
            pdf_path=args.pdf_file,
            output_path=args.output,
            pages=pages,
            add_document_wrapper=not args.no_wrapper,
            translate=True  # 启用翻译
        )
        
        print(f"\n✓ 成功！中文LaTeX文件已保存到: {output_path}")
        
    except Exception as e:
        print(f"\n✗ 错误: {str(e)}", file=sys.stderr)
        sys.exit(1)


def batch_translate():
    """批量翻译当前目录下所有PDF文件"""
    current_dir = Path(".")
    pdf_files = list(current_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("当前目录下没有找到PDF文件")
        return
    
    print(f"找到 {len(pdf_files)} 个PDF文件\n")
    
    # 创建输出目录
    output_dir = current_dir / "latex_cn_output"
    output_dir.mkdir(exist_ok=True)
    
    # 创建转换器
    try:
        converter = PDF2LaTeX()
    except Exception as e:
        print(f"✗ 初始化失败: {str(e)}")
        return
    
    # 批量翻译转换
    success_count = 0
    failed_files = []
    
    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(pdf_files)}] 正在翻译转换: {pdf_file.name}")
        print('='*60)
        
        try:
            output_path = output_dir / f"{pdf_file.stem}_cn.tex"
            converter.convert_pdf(
                pdf_path=str(pdf_file),
                output_path=str(output_path),
                translate=True
            )
            success_count += 1
            
        except Exception as e:
            print(f"翻译转换失败: {str(e)}")
            failed_files.append(pdf_file.name)
    
    # 输出总结
    print(f"\n{'='*60}")
    print("批量翻译转换完成！")
    print(f"{'='*60}")
    print(f"成功: {success_count}/{len(pdf_files)}")
    
    if failed_files:
        print(f"\n失败的文件:")
        for filename in failed_files:
            print(f"  - {filename}")
    
    print(f"\n输出目录: {output_dir}")


if __name__ == "__main__":
    main()
