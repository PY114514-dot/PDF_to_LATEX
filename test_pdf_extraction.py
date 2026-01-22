#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF提取质量测试工具
快速检测PDF文件的文本提取质量
"""

import sys
from pathlib import Path

try:
    import pdfplumber
    import PyPDF2
except ImportError as e:
    print(f"❌ 缺少依赖: {e}")
    print("\n请先安装依赖:")
    print("  pip install pdfplumber PyPDF2")
    sys.exit(1)


def check_text_quality(text: str) -> float:
    """检查文本质量，返回0-1的分数"""
    if not text or len(text.strip()) < 10:
        return 0.0
    
    readable_chars = sum(1 for c in text if c.isalnum() or c.isspace() or c in '.,;:!?-()[]{}')
    total_chars = len(text)
    
    if total_chars == 0:
        return 0.0
    
    readable_ratio = readable_chars / total_chars
    weird_chars = sum(1 for c in text if ord(c) > 1000 and not ('\u4e00' <= c <= '\u9fff'))
    weird_ratio = weird_chars / total_chars
    
    quality_score = readable_ratio - (weird_ratio * 2)
    
    return max(0.0, min(1.0, quality_score))


def get_quality_emoji(quality: float) -> str:
    """根据质量分数返回emoji"""
    if quality >= 0.7:
        return "✅"
    elif quality >= 0.5:
        return "🟡"
    elif quality >= 0.3:
        return "⚠️"
    else:
        return "❌"


def test_pdf(pdf_path: str):
    """测试PDF文件的文本提取质量"""
    pdf_file = Path(pdf_path)
    
    if not pdf_file.exists():
        print(f"❌ 文件不存在: {pdf_path}")
        return
    
    print("=" * 70)
    print(f"📄 测试文件: {pdf_file.name}")
    print("=" * 70)
    print()
    
    # 测试 pdfplumber
    print("🔍 方法1: pdfplumber (推荐)")
    print("-" * 70)
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            print(f"总页数: {total_pages}")
            print()
            
            plumber_qualities = []
            plumber_lengths = []
            
            for page_num in range(min(5, total_pages)):  # 只测试前5页
                page = pdf.pages[page_num]
                text = page.extract_text() or ""
                quality = check_text_quality(text)
                
                plumber_qualities.append(quality)
                plumber_lengths.append(len(text))
                
                emoji = get_quality_emoji(quality)
                print(f"  {emoji} 第 {page_num + 1} 页:")
                print(f"     长度: {len(text)} 字符")
                print(f"     质量: {quality:.2f}")
                if text:
                    preview = text[:100].replace('\n', ' ')
                    print(f"     预览: {preview}...")
                else:
                    print(f"     预览: (空)")
                print()
            
            if total_pages > 5:
                print(f"  ... (仅显示前5页，共{total_pages}页)")
                print()
            
            avg_quality = sum(plumber_qualities) / len(plumber_qualities) if plumber_qualities else 0
            avg_length = sum(plumber_lengths) / len(plumber_lengths) if plumber_lengths else 0
            
            print(f"平均质量: {avg_quality:.2f} {get_quality_emoji(avg_quality)}")
            print(f"平均长度: {avg_length:.0f} 字符")
            
    except Exception as e:
        print(f"❌ pdfplumber 失败: {str(e)}")
    
    print()
    print("=" * 70)
    
    # 测试 PyPDF2
    print("🔍 方法2: PyPDF2 (备用)")
    print("-" * 70)
    
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            print(f"总页数: {total_pages}")
            print()
            
            pypdf2_qualities = []
            pypdf2_lengths = []
            
            for page_num in range(min(5, total_pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text() or ""
                quality = check_text_quality(text)
                
                pypdf2_qualities.append(quality)
                pypdf2_lengths.append(len(text))
                
                emoji = get_quality_emoji(quality)
                print(f"  {emoji} 第 {page_num + 1} 页:")
                print(f"     长度: {len(text)} 字符")
                print(f"     质量: {quality:.2f}")
                if text:
                    preview = text[:100].replace('\n', ' ')
                    print(f"     预览: {preview}...")
                else:
                    print(f"     预览: (空)")
                print()
            
            if total_pages > 5:
                print(f"  ... (仅显示前5页，共{total_pages}页)")
                print()
            
            avg_quality = sum(pypdf2_qualities) / len(pypdf2_qualities) if pypdf2_qualities else 0
            avg_length = sum(pypdf2_lengths) / len(pypdf2_lengths) if pypdf2_lengths else 0
            
            print(f"平均质量: {avg_quality:.2f} {get_quality_emoji(avg_quality)}")
            print(f"平均长度: {avg_length:.0f} 字符")
            
    except Exception as e:
        print(f"❌ PyPDF2 失败: {str(e)}")
    
    print()
    print("=" * 70)
    
    # 对比和建议
    print("📊 质量评估和建议")
    print("-" * 70)
    
    if plumber_qualities and pypdf2_qualities:
        plumber_avg = sum(plumber_qualities) / len(plumber_qualities)
        pypdf2_avg = sum(pypdf2_qualities) / len(pypdf2_qualities)
        
        print(f"\npdfplumber 平均质量: {plumber_avg:.2f} {get_quality_emoji(plumber_avg)}")
        print(f"PyPDF2     平均质量: {pypdf2_avg:.2f} {get_quality_emoji(pypdf2_avg)}")
        print()
        
        if plumber_avg >= 0.7:
            print("✅ 质量优秀！可以直接使用本工具转换。")
        elif plumber_avg >= 0.5:
            print("🟡 质量良好，可以尝试转换，但结果可能需要人工检查。")
        elif plumber_avg >= 0.3:
            print("⚠️ 质量一般，建议检查PDF是否为文本版。")
        else:
            print("❌ 质量较差！")
            print("   可能原因:")
            print("   1. 这是扫描版PDF（只包含图片）")
            print("   2. PDF使用了特殊字体编码")
            print("   3. PDF文件损坏")
            print()
            print("   建议:")
            print("   - 使用OCR工具将扫描版PDF转换为可搜索PDF")
            print("   - 尝试用Adobe Acrobat重新保存PDF")
            print("   - 检查PDF是否可以正常打开和复制文字")
    
    print()
    print("=" * 70)
    print()


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("PDF提取质量测试工具")
        print()
        print("用法:")
        print(f"  python {sys.argv[0]} <PDF文件路径>")
        print()
        print("示例:")
        print(f"  python {sys.argv[0]} example.pdf")
        print(f"  python {sys.argv[0]} \"C:/Documents/paper.pdf\"")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    test_pdf(pdf_path)


if __name__ == '__main__':
    main()
