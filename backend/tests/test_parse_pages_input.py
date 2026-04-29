#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_pages_input 函数测试
"""

import pytest
from app_enhanced import parse_pages_input


class TestParsePagesInput:
    """测试页码解析功能"""

    def test_empty_string(self):
        """空字符串返回 None"""
        assert parse_pages_input("") is None
        assert parse_pages_input("   ") is None

    def test_single_page(self):
        """单页码解析"""
        assert parse_pages_input("1") == [0]
        assert parse_pages_input("5") == [4]

    def test_multiple_pages(self):
        """多页码逗号分隔"""
        assert parse_pages_input("1,3,5") == [0, 2, 4]
        assert parse_pages_input("2,4,6,8") == [1, 3, 5, 7]

    def test_page_range(self):
        """页码范围解析"""
        assert parse_pages_input("1-3") == [0, 1, 2]
        assert parse_pages_input("5-7") == [4, 5, 6]

    def test_mixed_range_and_single(self):
        """混合范围和单页"""
        assert parse_pages_input("1-3,5,7-9") == [0, 1, 2, 4, 6, 7, 8]
        assert parse_pages_input("1,3-5,7") == [0, 2, 3, 4, 6]

    def test_deduplication(self):
        """去重排序"""
        assert parse_pages_input("1,1,2,2,3") == [0, 1, 2]
        assert parse_pages_input("1-3,2,3,4") == [0, 1, 2, 3]

    def test_invalid_range_reversed(self):
        """起始大于结束应报错"""
        with pytest.raises(ValueError, match="起始不能大于结束"):
            parse_pages_input("5-3")

    def test_invalid_non_digit(self):
        """非数字应报错"""
        with pytest.raises(ValueError, match="无效的页码"):
            parse_pages_input("1,a,3")
        with pytest.raises(ValueError, match="无效的页码"):
            parse_pages_input("abc")

    def test_invalid_format(self):
        """无效格式应报错"""
        with pytest.raises(ValueError, match="无效的页码范围"):
            parse_pages_input("1-2-3")
        with pytest.raises(ValueError, match="无效的页码范围"):
            parse_pages_input("1-")

    def test_zero_or_negative_page(self):
        """零页或负数页应报错"""
        with pytest.raises(ValueError, match="页码必须大于0"):
            parse_pages_input("0")
        with pytest.raises(ValueError, match="页码必须大于0"):
            parse_pages_input("-1")
        with pytest.raises(ValueError, match="页码必须大于0"):
            parse_pages_input("1-0")
        with pytest.raises(ValueError, match="页码必须大于0"):
            parse_pages_input("5--3")

    def test_max_pages_limit(self):
        """最大页数限制"""
        # 默认硬限制 5000
        with pytest.raises(ValueError, match="页码范围过大"):
            parse_pages_input("1-5001")

        # 自定义限制
        with pytest.raises(ValueError, match="页码超出范围"):
            parse_pages_input("100", max_pages=50)
        with pytest.raises(ValueError, match="页码范围过大"):
            parse_pages_input("1-51", max_pages=50)

    def test_with_valid_max_pages(self):
        """有效 max_pages 参数"""
        result = parse_pages_input("1-10", max_pages=100)
        assert result == list(range(10))

    def test_large_range_within_limit(self):
        """大范围但在限制内"""
        result = parse_pages_input("1-100", max_pages=200)
        assert len(result) == 100
        assert result == list(range(100))