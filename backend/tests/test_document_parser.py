#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
document_parser 函数单元测试
"""

import pytest
import sys
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from document_parser import PDFDocumentParser


class TestIsPaginationLine:
    """测试 _is_pagination_line 函数"""

    @pytest.fixture
    def parser(self):
        """创建解析器实例"""
        return PDFDocumentParser()

    def test_page_number(self, parser):
        """页码匹配"""
        # 当前页是第5页
        assert parser._is_pagination_line("5", 4, 10) is True
        assert parser._is_pagination_line("10", 4, 10) is True  # 最后一页
        assert parser._is_pagination_line("3", 4, 10) is False

    def test_fraction_page(self, parser):
        """分数格式页码 5/10"""
        assert parser._is_pagination_line("5/10", 4, 10) is True
        assert parser._is_pagination_line("3/10", 4, 10) is False

    def test_chinese_page(self, parser):
        """中文页码"""
        assert parser._is_pagination_line("第5页", 4, 10) is True
        assert parser._is_pagination_line("第 5 页", 4, 10) is True

    def test_english_page(self, parser):
        """英文页码"""
        assert parser._is_pagination_line("page 5", 4, 10) is True
        assert parser._is_pagination_line("p. 5", 4, 10) is True
        assert parser._is_pagination_line("Page 5 of 10", 4, 10) is True

    def test_running_header_chinese(self, parser):
        """中文运行标题"""
        assert parser._is_pagination_line("1. 不可压缩欧拉方程", 0, 20) is True
        assert parser._is_pagination_line("2. 欧拉方程", 0, 20) is True

    def test_running_header_chapter(self, parser):
        """章节标题"""
        assert parser._is_pagination_line("第1章 引言", 0, 20) is True
        assert parser._is_pagination_line("第2章 相关工作", 0, 20) is True

    def test_running_header_with_number(self, parser):
        """短词 + 数字.数字格式"""
        assert parser._is_pagination_line("欧拉方程 1.3", 0, 20) is True

    def test_running_header_with_page_number(self, parser):
        """页码 + 章节号 + 标题（我们新加的模式）"""
        assert parser._is_pagination_line("6    1. 不可压缩欧拉方程", 0, 20) is True
        assert parser._is_pagination_line("10   2. 相关工作", 0, 20) is True
        assert parser._is_pagination_line("1  1.5 简介", 0, 20) is True

    def test_running_header_not_matched(self, parser):
        """正常文本不应匹配"""
        assert parser._is_pagination_line("根据体积对所有V保持不变", 0, 20) is False
        assert parser._is_pagination_line("这是一个正常的句子", 0, 20) is False
        assert parser._is_pagination_line("欧拉方程 1.3 是一个很长的描述不应该被匹配", 0, 20) is False

    def test_empty_string(self, parser):
        """空字符串"""
        assert parser._is_pagination_line("", 0, 20) is False
        assert parser._is_pagination_line(None, 0, 20) is False

    def test_only_whitespace(self, parser):
        """只有空白字符"""
        assert parser._is_pagination_line("   ", 0, 20) is False


class TestCleanupPagination:
    """测试 _cleanup_pagination 函数"""

    @pytest.fixture
    def parser(self):
        """创建解析器实例"""
        return PDFDocumentParser()

    def test_remove_running_header(self, parser):
        """移除运行标题"""
        text = "6    1. 不可压缩欧拉方程\n因此我们看到体积对所有V保持不变当且仅当J=1"
        result = parser._cleanup_pagination(text, 5, 20)
        assert "6    1. 不可压缩欧拉方程" not in result
        assert "因此我们看到体积对所有V保持不变" in result

    def test_preserve_content(self, parser):
        """保留正常内容"""
        text = "第一段内容\n第二段内容\n第三段内容"
        result = parser._cleanup_pagination(text, 0, 20)
        assert "第一段内容" in result
        assert "第二段内容" in result

    def test_remove_page_numbers(self, parser):
        """移除页码"""
        text = "5\n这是正文内容\n10"
        result = parser._cleanup_pagination(text, 4, 10)
        assert "这是正文内容" in result

    def test_empty_text(self, parser):
        """空文本"""
        result = parser._cleanup_pagination("", 0, 20)
        assert result == ""

    def test_only_headers(self, parser):
        """只有页眉页脚"""
        text = "1. 章节标题\n6    1. 不可压缩欧拉方程"
        result = parser._cleanup_pagination(text, 5, 20)
        assert result == ""


class TestDefaultQuality:
    """测试默认质量函数"""

    @pytest.fixture
    def parser(self):
        """创建解析器实例"""
        return PDFDocumentParser()

    def test_high_quality_text(self, parser):
        """高质量文本"""
        text = "This is a normal paragraph with multiple sentences. It has enough characters to be considered quality content."
        quality = parser._default_quality(text)
        assert quality > 0.5

    def test_low_quality_text(self, parser):
        """低质量文本（乱码）"""
        text = "▓▓▓▓▓ ░░░░░ 12345 !!!@@@"
        quality = parser._default_quality(text)
        assert quality < 0.5

    def test_empty_text(self, parser):
        """空文本"""
        quality = parser._default_quality("")
        assert quality == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])