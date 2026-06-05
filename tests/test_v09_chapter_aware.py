#!/usr/bin/env python3
"""v0.9 章节感知 + 困难页双次翻译 单元测试 (mock，无API调用)"""
import sys
import os
import asyncio
import re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

# ==================== Phase 1: 章节检测算法单元测试 ====================

def test_group_chars_into_lines():
    """测试字符按y坐标聚类成行"""
    from document_parser import PDFDocumentParser
    parser = PDFDocumentParser()

    # 模拟 chars: 两行文字，每行3字符
    chars = [
        {'text': 'C', 'x0': 10, 'top': 100, 'size': 12},
        {'text': 'h', 'x0': 15, 'top': 100, 'size': 12},
        {'text': '1', 'x0': 20, 'top': 100, 'size': 12},
        {'text': 'C', 'x0': 10, 'top': 115, 'size': 12},
        {'text': 'h', 'x0': 15, 'top': 115, 'size': 12},
        {'text': '2', 'x0': 20, 'top': 115, 'size': 12},
    ]
    lines = parser._group_chars_into_lines(chars)
    assert len(lines) == 2, f"应该聚成2行，得到{len(lines)}行"
    assert lines[0]['text'] == 'Ch1', f"第1行文本错误: {lines[0]['text']}"
    assert lines[1]['text'] == 'Ch2', f"第2行文本错误: {lines[1]['text']}"
    print("[PASS] test_group_chars_into_lines")


def test_looks_like_heading():
    """测试标题正则匹配"""
    from document_parser import PDFDocumentParser
    parser = PDFDocumentParser()

    # 英文标题
    assert parser._looks_like_heading("Chapter 1 Introduction")
    assert parser._looks_like_heading("Section 2.3 Methods")
    assert parser._looks_like_heading("Abstract")
    assert parser._looks_like_heading("1. Introduction")
    assert parser._looks_like_heading("2.3 Related Work")
    assert parser._looks_like_heading("References")

    # 中文标题
    assert parser._looks_like_heading("第一章 绪论")
    assert parser._looks_like_heading("第3节 实验")
    assert parser._looks_like_heading("摘要")
    assert parser._looks_like_heading("参考文献")

    # 非标题（不应该匹配）
    assert not parser._looks_like_heading("The quick brown fox jumps over the lazy dog")
    assert not parser._looks_like_heading("x = 1 + 2")
    assert not parser._looks_like_heading("")  # 空字符串

    print("[PASS] test_looks_like_heading")


def test_classify_heading_level():
    """测试标题级别分类"""
    from document_parser import PDFDocumentParser
    parser = PDFDocumentParser()

    # Chapter → level 1
    assert parser._classify_heading_level("Chapter 1", 20, 10) == 1
    assert parser._classify_heading_level("第一章 绪论", 20, 10) == 1

    # Section → level 2
    assert parser._classify_heading_level("Section 2.1", 14, 10) == 2
    assert parser._classify_heading_level("第2节", 14, 10) == 2

    # Subsection → level 3
    assert parser._classify_heading_level("2.1.3 Methods", 12, 10) == 3

    # "1. Title" → level 2
    assert parser._classify_heading_level("1. Introduction", 13, 10) == 2

    print("[PASS] test_classify_heading_level")


def test_count_formula_lines():
    """测试公式行统计"""
    from document_parser import PDFDocumentParser
    parser = PDFDocumentParser()

    text = """This is normal text.
$x = 1 + 2$
Another normal line.
\\begin{equation}
y = mx + b
\\end{equation}
Pure text without math.
\\frac{a}{b} = c
"""

    count = parser._count_formula_lines(text)
    assert count >= 2, f"应该检测到至少2个公式行，得到{count}"
    # 4个公式行: $x = 1 + 2$, \begin{equation}, \frac, (其中 2 和 3 被break)
    # 总共: "$x=1+2$" (idx 1), "\begin{equation}" (idx 3), "\frac{a}{b}" (idx 6)
    # text=6行有3个含公式
    print(f"[PASS] test_count_formula_lines (found {count} formula lines)")


# ==================== Phase 2: 章节感知 chunking ====================

def test_plan_chunks_fallback():
    """章节感知关闭时应回退到4-页块"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    converter = PDF2LaTeXEnhanced()

    # 边界为空 → 4-页块
    pages_text = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7']
    pages_info = [(i, i) for i in range(7)]
    chunks = converter._plan_chunks(pages_text, pages_info)
    assert len(chunks) == 2, f"应该2个4-页块，得到{len(chunks)}"
    assert len(chunks[0][0]) == 4
    assert len(chunks[1][0]) == 3  # 最后一组
    print(f"[PASS] test_plan_chunks_fallback ({len(chunks)} chunks of 4)")


def test_plan_chunks_chapter_aware():
    """章节感知开启时应按章节边界切分"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    from document_parser import ChapterBoundary

    converter = PDF2LaTeXEnhanced()
    # 注入模拟的边界：第3页和第7页是章节起点
    converter._chapter_boundaries = [
        ChapterBoundary(page_num=0, title='Chapter 1', level=1, font_size=20, char_count=9),
        ChapterBoundary(page_num=3, title='Chapter 2', level=1, font_size=20, char_count=9),
        ChapterBoundary(page_num=7, title='Chapter 3', level=1, font_size=20, char_count=9),
    ]
    # _chapter_aware_active 需要 settings.ENABLE_CHAPTER_AWARE=True (默认)

    pages_text = [f'p{i}' for i in range(10)]
    pages_info = [(i, i) for i in range(10)]
    chunks = converter._plan_chunks(pages_text, pages_info)

    # 期望：章节1=[0:3]=3页, 章节2=[3:7]=4页, 章节3=[7:10]=3页
    assert len(chunks) == 3, f"应该3个章节块，得到{len(chunks)}"
    assert len(chunks[0][0]) == 3, f"章节1应该是3页，得到{len(chunks[0][0])}"
    assert len(chunks[1][0]) == 4, f"章节2应该是4页，得到{len(chunks[1][0])}"
    assert len(chunks[2][0]) == 3, f"章节3应该是3页，得到{len(chunks[2][0])}"
    print(f"[PASS] test_plan_chunks_chapter_aware (3 chunks: 3+4+3)")


def test_plan_chunks_max_per_chapter():
    """单章节超过 MAX_PAGES_PER_CHAPTER 时应强制切片"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    from document_parser import ChapterBoundary
    from config import settings

    converter = PDF2LaTeXEnhanced()
    # 模拟：只有1个章节边界，覆盖12页
    converter._chapter_boundaries = [
        ChapterBoundary(page_num=0, title='Big Chapter', level=1, font_size=20, char_count=11),
    ]

    # 临时改小 MAX_PAGES_PER_CHAPTER
    original = settings.MAX_PAGES_PER_CHAPTER
    settings.MAX_PAGES_PER_CHAPTER = 5
    try:
        pages_text = [f'p{i}' for i in range(12)]
        pages_info = [(i, i) for i in range(12)]
        chunks = converter._plan_chunks(pages_text, pages_info)
        # 12页应被切成3块：5+5+2
        assert len(chunks) == 3, f"应该3块，得到{len(chunks)}"
        assert len(chunks[0][0]) == 5
        assert len(chunks[1][0]) == 5
        assert len(chunks[2][0]) == 2
        print(f"[PASS] test_plan_chunks_max_per_chapter (3 chunks: 5+5+2)")
    finally:
        settings.MAX_PAGES_PER_CHAPTER = original


# ==================== Phase 3: 双次翻译+LLM评分 ====================

async def test_pick_better_translation_winner1():
    """LLM评分返回 winner=1 应选 v1"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    class MockClient:
        async def chat(self, messages, **kwargs):
            # 模拟LLM评分返回 JSON
            return {'choices': [{'message': {'content': '{"winner": 1, "score1": 8.5, "score2": 7.0, "reason": "v1更准确"}'}}], 'usage': {}}

    converter.client = MockClient()
    v1 = "翻译版本1，更准确"
    v2 = "翻译版本2，稍差"
    chosen = await converter._pick_better_translation("Original", v1, v2)
    assert chosen == v1, f"应该选v1，得到{chosen}"
    print("[PASS] test_pick_better_translation_winner1")


async def test_pick_better_translation_winner2():
    """LLM评分返回 winner=2 应选 v2"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    class MockClient:
        async def chat(self, messages, **kwargs):
            return {'choices': [{'message': {'content': '{"winner": 2, "score1": 6, "score2": 9, "reason": "v2更好"}'}}], 'usage': {}}

    converter.client = MockClient()
    v1 = "v1"
    v2 = "v2 better"
    chosen = await converter._pick_better_translation("Orig", v1, v2)
    assert chosen == v2
    print("[PASS] test_pick_better_translation_winner2")


async def test_pick_better_translation_fallback_to_v1():
    """LLM评分失败时应默认选 v1"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    class FailingClient:
        async def chat(self, messages, **kwargs):
            raise Exception("API error")

    converter.client = FailingClient()
    v1 = "v1 fallback"
    v2 = "v2 fallback"
    chosen = await converter._pick_better_translation("Orig", v1, v2)
    assert chosen == v1, f"评分失败时应选v1，得到{chosen}"
    print("[PASS] test_pick_better_translation_fallback_to_v1")


async def test_pick_better_translation_json_parse_fail():
    """LLM返回非JSON时容错"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    class BadJsonClient:
        async def chat(self, messages, **kwargs):
            return {'choices': [{'message': {'content': 'winner is 2, no json'}}], 'usage': {}}

    converter.client = BadJsonClient()
    v1, v2 = "v1", "v2"
    # 应通过正则提取 "winner is 2" → 找不到则默认v1
    chosen = await converter._pick_better_translation("Orig", v1, v2)
    assert chosen == v1, f"JSON失败时默认v1，得到{chosen}"

    # 测试 markdown 包裹
    class MarkdownClient:
        async def chat(self, messages, **kwargs):
            return {'choices': [{'message': {'content': '```json\n{"winner": 2}\n```'}}], 'usage': {}}
    converter.client = MarkdownClient()
    chosen = await converter._pick_better_translation("Orig", v1, v2)
    assert chosen == v2, f"Markdown包裹应正确解析，得到{chosen}"
    print("[PASS] test_pick_better_translation_json_parse_fail")


async def test_translate_difficult_pages_both_valid():
    """双次翻译都成功时调用评分"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    call_count = [0]

    class MockClient:
        async def chat(self, messages, **kwargs):
            call_count[0] += 1
            temp = kwargs.get('temperature', 0.3)
            if temp == 0.1:  # 评分调用
                return {'choices': [{'message': {'content': '{"winner": 2}'}}], 'usage': {}}
            # 单次翻译
            return {'choices': [{'message': {'content': f'翻译@temp{temp}'}}], 'usage': {}}

    converter.client = MockClient()
    converter._difficult_pages = {0}
    pages_text = ['page 0 with formula $x^2$']
    pages_info = [(0, 0)]

    results = await converter._translate_difficult_pages(pages_text, pages_info, 1)
    assert len(results) == 1
    assert results[0][0] == 0
    assert '翻译@temp0.7' in results[0][1], f"应选v2 (temp=0.7), 得到{results[0][1]}"
    # 期望调用 2次翻译 + 1次评分 = 3次
    assert call_count[0] == 3, f"期望3次调用, 实际{call_count[0]}"
    print(f"[PASS] test_translate_difficult_pages_both_valid (3 calls, picked v2)")


async def test_translate_difficult_pages_all_fail():
    """双次翻译都失败时回退到原文"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced

    converter = PDF2LaTeXEnhanced()

    class FailingClient:
        async def chat(self, messages, **kwargs):
            # 第一次的双次翻译都失败，但最终回退的单次翻译也失败 → 应回退到原文
            if kwargs.get('temperature') == 0.3 and 'page 0' in str(messages):
                raise Exception("API down")
            raise Exception("Final fallback also fails")

    converter.client = FailingClient()
    pages_text = ['original page content']
    pages_info = [(0, 0)]
    results = await converter._translate_difficult_pages(pages_text, pages_info, 1)
    # 最终返回原文
    assert len(results) == 1
    assert results[0][0] == 0
    assert results[0][1] == 'original page content'
    print(f"[PASS] test_translate_difficult_pages_all_fail (fallback to original)")


# ==================== 端到端: 章节切分 + 批量翻译 ====================

async def test_translate_batch_async_chapter_aware():
    """完整测试：章节切分 + 正常批量翻译"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    from document_parser import ChapterBoundary

    converter = PDF2LaTeXEnhanced()
    converter._chapter_boundaries = [
        ChapterBoundary(page_num=0, title='Ch1', level=1, font_size=20, char_count=3),
        ChapterBoundary(page_num=4, title='Ch2', level=1, font_size=20, char_count=3),
    ]

    # Mock LLM: 返回带 [PAGE X] 标记的翻译
    class MockClient:
        async def chat(self, messages, **kwargs):
            content = messages[1]['content']
            pages = re.findall(r'\[PAGE (\d+)\]', content)
            output = '\n'.join(f"[PAGE {p}]\n[翻译] page {p}" for p in pages)
            return {'choices': [{'message': {'content': output}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}

    converter.client = MockClient()

    pages_text = [f'Original page {i}' for i in range(8)]
    pages_info = [(i, i) for i in range(8)]
    results = await converter.translate_batch_async(pages_text, pages_info, 8, translate=True)

    assert len(results) == 8, f"应该返回8个结果，得到{len(results)}"
    page_nums = [p for p, _ in results]
    assert sorted(page_nums) == list(range(8)), f"页码不完整: {page_nums}"
    print(f"[PASS] test_translate_batch_async_chapter_aware ({len(results)} results from 2 chapter chunks)")


async def test_translate_batch_async_disable_chapter():
    """ENABLE_CHAPTER_AWARE=False 时回退到4-页块"""
    from pdf2latex_enhanced import PDF2LaTeXEnhanced
    from config import settings

    converter = PDF2LaTeXEnhanced()
    # 即使注入了边界，settings关闭时不应使用
    converter._chapter_boundaries = [type('B', (), {'page_num': 0})()]  # 假装有边界

    original = settings.ENABLE_CHAPTER_AWARE
    settings.ENABLE_CHAPTER_AWARE = False
    try:
        class MockClient:
            async def chat(self, messages, **kwargs):
                pages = re.findall(r'\[PAGE (\d+)\]', messages[1]['content'])
                output = '\n'.join(f"[PAGE {p}]\n[p{p}]" for p in pages)
                return {'choices': [{'message': {'content': output}}], 'usage': {}}
        converter.client = MockClient()
        pages_text = [f'p{i}' for i in range(10)]
        pages_info = [(i, i) for i in range(10)]
        results = await converter.translate_batch_async(pages_text, pages_info, 10, translate=True)
        assert len(results) == 10
    finally:
        settings.ENABLE_CHAPTER_AWARE = original
    print(f"[PASS] test_translate_batch_async_disable_chapter ({len(results)} results, 4-page chunks)")


# ==================== Main ====================

def main():
    print("=" * 60)
    print("v0.9 智能章节 + 困难页双次翻译 单元测试")
    print("=" * 60 + "\n")

    print("--- Phase 1: 章节检测算法 ---")
    test_group_chars_into_lines()
    test_looks_like_heading()
    test_classify_heading_level()
    test_count_formula_lines()

    print("\n--- Phase 2: 章节感知 chunking ---")
    test_plan_chunks_fallback()
    test_plan_chunks_chapter_aware()
    test_plan_chunks_max_per_chapter()

    print("\n--- Phase 3: 双次翻译+LLM评分 ---")
    asyncio.run(test_pick_better_translation_winner1())
    asyncio.run(test_pick_better_translation_winner2())
    asyncio.run(test_pick_better_translation_fallback_to_v1())
    asyncio.run(test_pick_better_translation_json_parse_fail())
    asyncio.run(test_translate_difficult_pages_both_valid())
    asyncio.run(test_translate_difficult_pages_all_fail())

    print("\n--- Phase 4: 端到端集成 ---")
    asyncio.run(test_translate_batch_async_chapter_aware())
    asyncio.run(test_translate_batch_async_disable_chapter())

    print("\n" + "=" * 60)
    print("ALL v0.9 TESTS PASSED!")
    print("=" * 60)


if __name__ == '__main__':
    main()
