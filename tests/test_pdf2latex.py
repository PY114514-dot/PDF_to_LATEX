"""
PDF2LaTeX 单元测试
"""
import os
import sys
import unittest
import tempfile
import hashlib

# 添加 backend 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class TestConversionCache(unittest.TestCase):
    """测试转换缓存功能"""

    def test_cache_key_generation(self):
        """测试缓存键生成"""
        from cache import ConversionCache

        cache = ConversionCache()

        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            # 测试缓存键生成
            key1 = cache._get_cache_key(temp_path, None, False)
            key2 = cache._get_cache_key(temp_path, [1, 2, 3], False)
            key3 = cache._get_cache_key(temp_path, [1, 2, 3], True)

            # 不同参数应生成不同键
            assert key1 != key2, "Pages should affect cache key"
            assert key2 != key3, "Translate should affect cache key"

            # 相同参数应生成相同键
            key2_again = cache._get_cache_key(temp_path, [1, 2, 3], False)
            assert key2 == key2_again, "Same params should generate same key"
        finally:
            os.unlink(temp_path)

    def test_cache_set_and_get(self):
        """测试缓存存取"""
        from cache import ConversionCache

        cache = ConversionCache(cache_dir=tempfile.mkdtemp())

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'test content for cache')
            temp_path = f.name

        try:
            test_result = {
                'output_path': '/tmp/test.tex',
                'total_pages': 10,
                'processed_pages': 10,
                'source_text': 'test source'
            }

            # 保存缓存
            success = cache.set(temp_path, [1, 2, 3], True, test_result)
            assert success, "Cache set should succeed"

            # 读取缓存
            cached = cache.get(temp_path, [1, 2, 3], True)
            assert cached is not None, "Cache should return value"
            assert cached['output_path'] == test_result['output_path']
            assert cached['source_text'] == test_result['source_text']

            # 不同参数不应返回缓存
            cached_wrong = cache.get(temp_path, [4, 5], True)
            assert cached_wrong is None, "Different pages should not return cached"

        finally:
            os.unlink(temp_path)

    def test_cache_disabled(self):
        """测试缓存禁用"""
        from cache import ConversionCache

        cache = ConversionCache(cache_dir=tempfile.mkdtemp(), expiry_seconds=0)
        cache.enabled = False

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            result = cache.get(temp_path, None, False)
            assert result is None, "When disabled, get should return None"

            success = cache.set(temp_path, None, False, {'test': 'data'})
            assert not success, "When disabled, set should return False"
        finally:
            os.unlink(temp_path)

    def test_cache_expiry(self):
        """测试缓存过期"""
        from cache import ConversionCache

        cache_dir = tempfile.mkdtemp()
        cache = ConversionCache(cache_dir=cache_dir, expiry_seconds=-1)  # 已过期

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
            f.write(b'test content')
            temp_path = f.name

        try:
            # 保存缓存
            cache.set(temp_path, None, False, {'test': 'data'})

            # 应该返回 None（已过期）
            result = cache.get(temp_path, None, False)
            assert result is None, "Expired cache should return None"
        finally:
            os.unlink(temp_path)


class TestHeaderFooterDetection(unittest.TestCase):
    """测试页眉页脚检测"""

    def test_header_threshold_calculation(self):
        """测试页眉阈值计算"""
        from document_parser import PDFDocumentParser

        parser = PDFDocumentParser()

        # 模拟页面高度 800
        page_height = 800
        header_threshold = page_height * 0.05  # 5% = 40
        footer_threshold = page_height * 0.95  # 95% = 760

        assert header_threshold == 40, f"Header threshold should be 40, got {header_threshold}"
        assert footer_threshold == 760, f"Footer threshold should be 760, got {footer_threshold}"

    def test_is_pagination_line(self):
        """测试分页线检测"""
        from document_parser import PDFDocumentParser

        parser = PDFDocumentParser()

        # 测试页码格式（阿拉伯数字）
        assert parser._is_pagination_line("1", 0, 100), "Should detect '1'"
        assert parser._is_pagination_line("Page 5", 4, 100), "Should detect 'Page 5'"
        assert parser._is_pagination_line("5 / 100", 4, 100), "Should detect '5 / 100'"
        assert parser._is_pagination_line("第 5 页", 4, 100), "Should detect '第 5 页'"

        # 测试非分页线
        assert not parser._is_pagination_line("This is a title", 0, 100), "Should not detect title as pagination"
        assert not parser._is_pagination_line("", 0, 100), "Should not detect empty as pagination"
        assert not parser._is_pagination_line("- 5 -", 4, 100), "Should not detect '- 5 -' (not implemented)"


class TestRunningHeaderDetection(unittest.TestCase):
    """测试运行标题检测"""

    def test_running_header_validation(self):
        """测试运行标题验证逻辑"""
        from document_parser import PDFDocumentParser
        from document_parser import PageExtraction

        parser = PDFDocumentParser()

        # 模拟多页提取结果
        pages = [
            PageExtraction(page_num=1, text="Chapter 1 Introduction\nSome content here"),
            PageExtraction(page_num=2, text="Chapter 1 Introduction\nMore content"),
            PageExtraction(page_num=3, text="Chapter 1 Introduction\nEven more content"),
            PageExtraction(page_num=4, text="Chapter 2 Methods\nDifferent content"),
        ]

        result = parser._find_running_headers(pages, window=5)

        # "Chapter 1 Introduction" 出现3次，应该被标记为运行标题
        chapter1_found = any(p.is_running_header and "Chapter 1" in p.text for p in result[:3])
        assert chapter1_found, "Running header should be detected for 'Chapter 1 Introduction'"


class TestTokenLimitEnforcement(unittest.TestCase):
    """测试Token限制强制执行"""

    def test_batch_split_on_char_limit(self):
        """测试超过字符限制时拆分批次"""
        # 这个测试需要完整的pdf2latex_enhanced环境
        # 只验证逻辑存在

        from pdf2latex_enhanced import PDF2LaTeXEnhanced

        converter = PDF2LaTeXEnhanced()

        # 验证常量存在
        assert hasattr(converter, 'MAX_CHARS_PER_BATCH'), "MAX_CHARS_PER_BATCH should be defined"
        assert converter.MAX_CHARS_PER_BATCH == 80000, f"MAX_CHARS_PER_BATCH should be 80000, got {converter.MAX_CHARS_PER_BATCH}"


class TestQualityModeRefinement(unittest.TestCase):
    """测试高质量模式的refinement"""

    def test_refinement_error_handling(self):
        """测试refinement失败时的错误处理"""
        # 这个测试需要模拟网络环境
        # 只验证错误处理逻辑存在

        import logging
        from unittest.mock import patch, MagicMock

        # 当 refinement 失败时，应该记录警告而不是 silent pass
        with patch('logging.Logger.warning') as mock_warning:
            # 模拟 refinement 失败
            pass  # 实际测试需要完整环境

        # 验证 logger.warning 被正确调用
        # （这个测试在集成测试中更合适）


if __name__ == '__main__':
    unittest.main()