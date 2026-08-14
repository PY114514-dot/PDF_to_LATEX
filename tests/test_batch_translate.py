#!/usr/bin/env python3
"""测试批量翻译核心逻辑"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import asyncio
import re

# 测试 _mark_duplicate_headers 函数
def test_mark_duplicate_headers():
    """测试页眉页脚去重标记"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    # 测试1: 正常文本无重复
    text1 = "This is a normal paragraph.\n\nAnother paragraph here."
    result1 = converter._mark_duplicate_headers(text1)
    assert "[DUPLICATE_HEADER]" not in result1, "Should not mark normal text"
    print("[PASS] Test 1 passed: normal text")

    # 测试2: 重复的短行（页眉）
    text2 = "Chapter 1 Introduction\n" * 2  # 连续两行相同
    result2 = converter._mark_duplicate_headers(text2)
    assert "[DUPLICATE_HEADER]" in result2, "Should mark duplicate header"
    # 第二次出现应该被移除
    lines = result2.split('\n')
    duplicate_count = sum(1 for l in lines if "[DUPLICATE_HEADER]" in l)
    assert duplicate_count == 1, f"Should only mark first occurrence, got {duplicate_count}"
    print("[PASS] Test 2 passed: duplicate header marked")

    # 测试3: 长文本不重复
    text3 = "A" * 100 + "\n" + "A" * 100  # 长行，即使内容相同也不算重复
    result3 = converter._mark_duplicate_headers(text3)
    assert "[DUPLICATE_HEADER]" not in result3, "Long lines should not be marked"
    print("[PASS] Test 3 passed: long lines not marked")

    print("\n=== _mark_duplicate_headers tests passed ===\n")

# 测试 _parse_batch_translation 函数
def test_parse_batch_translation():
    """测试批量翻译结果解析"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    chunk_info = [(0, 0), (1, 1), (2, 2), (3, 3)]  # 4页

    # 测试1: 正常的PAGE标记分割
    content1 = """[PAGE 1]
First page content
[PAGE 2]
Second page content
[PAGE 3]
Third page content
[PAGE 4]
Fourth page content"""

    results1 = converter._parse_batch_translation(content1, chunk_info)
    assert len(results1) == 4, f"Should return 4 results, got {len(results1)}"
    assert results1[0] == (0, "First page content"), f"Page 1 mismatch: {results1[0]}"
    assert results1[1] == (1, "Second page content"), f"Page 2 mismatch: {results1[1]}"
    print("[PASS] Test 1 passed: normal PAGE splitting")

    # 测试2: 清理DUPLICATE_HEADER标记
    content2 = """[PAGE 1]
[DUPLICATE_HEADER]Header text[/DUPLICATE_HEADER]
Main content
[PAGE 2]
Main content continues"""

    results2 = converter._parse_batch_translation(content2, chunk_info)
    assert "[DUPLICATE_HEADER]" not in results2[0][1], "Should remove DUPLICATE_HEADER tags"
    assert "Header text" not in results2[0][1], "Should remove duplicate header text"
    print("[PASS] Test 2 passed: DUPLICATE_HEADER tags removed")

    # 测试3: 无PAGE标记时回退
    content3 = "All content together without PAGE markers"

    results3 = converter._parse_batch_translation(content3, chunk_info)
    # 回退时应该返回第一个chunk_info的页码作为整个内容
    assert len(results3) == 4, f"Fallback should return 4 results, got {len(results3)}"
    print("[PASS] Test 3 passed: fallback handling")

    print("\n=== _parse_batch_translation tests passed ===\n")

# 测试 translate_batch_async 的基本流程
async def test_translate_batch_async():
    """测试批量翻译async方法（使用mock）"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    from clients import LLMClient

    # 创建一个简单的mock客户端
    class MockClient:
        async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
            # 提取user消息中的PAGE标记来生成响应
            user_content = messages[1]['content']
            response_pages = []

            # 解析PAGE标记
            page_pattern = r'\[PAGE (\d+)\]'
            pages = re.split(page_pattern, user_content)

            for i in range(1, len(pages), 2):
                page_num = pages[i]
                page_text = pages[i+1] if i+1 < len(pages) else ""
                # 简单翻译：添加"[已翻译]"标记
                response_pages.append(f"[PAGE {page_num}]\n[已翻译] {page_text[:50]}...")

            content = "\n---\n".join(response_pages)
            return {'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}

    converter = PDF2LaTeXEnhanced()
    converter.client = MockClient()

    # 测试批量翻译
    pages_text = [
        "This is page 1 content about mathematics.",
        "This is page 2 content about algorithms.",
        "This is page 3 content about neural networks.",
        "This is page 4 content about optimization."
    ]
    pages_info = [(0, 0), (1, 1), (2, 2), (3, 3)]

    results = await converter.translate_batch_async(pages_text, pages_info, 4, translate=True)

    assert len(results) == 4, f"Should return 4 results, got {len(results)}"
    for page_num, content in results:
        assert "[已翻译]" in content, f"Page {page_num} should be translated: {content[:100]}"
    print(f"[PASS] translate_batch_async returned {len(results)} results")
    for page_num, content in results:
        print(f"  Page {page_num}: {content[:60]}...")

    print("\n=== translate_batch_async test passed ===\n")

def main():
    print("=" * 60)
    print("Testing Batch Translation Logic")
    print("=" * 60 + "\n")

    # 测试去重函数
    test_mark_duplicate_headers()

    # 测试解析函数
    test_parse_batch_translation()

    # 测试批量翻译async方法
    asyncio.run(test_translate_batch_async())

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)

if __name__ == '__main__':
    main()