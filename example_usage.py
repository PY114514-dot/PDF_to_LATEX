#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX 使用示例
演示如何在Python代码中使用 PDF2LaTeX 类
"""

from pdf2latex import PDF2LaTeX


def example_1_basic_conversion():
    """示例1: 基本转换"""
    print("=" * 60)
    print("示例1: 基本转换整个PDF")
    print("=" * 60)
    
    converter = PDF2LaTeX()
    
    # 转换整个PDF文件（假设当前目录有 example.pdf）
    try:
        output_path = converter.convert_pdf("main.pdf")
        print(f"\n✓ 转换成功: {output_path}")
    except Exception as e:
        print(f"\n✗ 转换失败: {str(e)}")


def example_2_specific_pages():
    """示例2: 转换特定页面"""
    print("\n" + "=" * 60)
    print("示例2: 只转换前3页")
    print("=" * 60)
    
    converter = PDF2LaTeX()
    
    try:
        output_path = converter.convert_pdf(
            pdf_path="main.pdf",
            output_path="main_first_3_pages.tex",
            pages=[0, 1, 2],  # 页码从0开始
            add_document_wrapper=True
        )
        print(f"\n✓ 转换成功: {output_path}")
    except Exception as e:
        print(f"\n✗ 转换失败: {str(e)}")


def example_3_no_wrapper():
    """示例3: 不添加文档结构"""
    print("\n" + "=" * 60)
    print("示例3: 只转换内容，不添加文档结构")
    print("=" * 60)
    
    converter = PDF2LaTeX()
    
    try:
        output_path = converter.convert_pdf(
            pdf_path="main.pdf",
            output_path="main_content_only.tex",
            pages=[0],  # 只转换第一页
            add_document_wrapper=False  # 不添加 \documentclass 等
        )
        print(f"\n✓ 转换成功: {output_path}")
    except Exception as e:
        print(f"\n✗ 转换失败: {str(e)}")


def example_4_extract_text_only():
    """示例4: 只提取文本不转换"""
    print("\n" + "=" * 60)
    print("示例4: 只提取PDF文本")
    print("=" * 60)
    
    converter = PDF2LaTeX()
    
    try:
        pages_text = converter.extract_text_from_pdf("main.pdf")
        
        print(f"\n提取了 {len(pages_text)} 页文本")
        print("\n第一页内容预览（前500字符）:")
        print("-" * 60)
        print(pages_text[0][:500])
        print("-" * 60)
        
    except Exception as e:
        print(f"\n✗ 提取失败: {str(e)}")


def example_5_custom_api_key():
    """示例5: 使用自定义API密钥"""
    print("\n" + "=" * 60)
    print("示例5: 使用自定义API密钥和模型")
    print("=" * 60)
    
    # 可以在代码中直接指定API密钥
    converter = PDF2LaTeX(
        api_key="your-custom-api-key",  # 替换为实际的API密钥
        model="deepseek-chat"
    )
    
    print("转换器已创建（使用自定义配置）")


def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("PDF2LaTeX 使用示例")
    print("=" * 60)
    
    # 运行示例（根据需要注释/取消注释）
    
    # example_1_basic_conversion()
    # example_2_specific_pages()
    # example_3_no_wrapper()
    # example_4_extract_text_only()
    example_5_custom_api_key()
    
    print("\n" + "=" * 60)
    print("示例运行完成")
    print("=" * 60)
    print("\n提示: 取消注释其他示例函数来运行它们")
    print("注意: 需要将 'main.pdf' 替换为实际存在的PDF文件")


if __name__ == "__main__":
    main()
