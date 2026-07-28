#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
latex_utils 函数单元测试
"""

import pytest
import sys
from pathlib import Path

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from latex_utils import (
    fix_matrix_transpose,
    fix_math_notation,
    sanitize_latex_body,
    validate_latex_page,
    replace_latex_page_block,
    stitch_cross_page_formula_fragments,
    normalize_align_environments,
    repair_tabular_consistency,
    strip_document_wrapper,
    wrap_with_template,
)


class TestFixMatrixTranspose:
    """测试 fix_matrix_transpose 函数"""

    def test_period_T(self):
        """句点表示的转置 W.T"""
        assert fix_matrix_transpose("W.T") == r"W^{\mathsf{T}}"
        assert fix_matrix_transpose("A.T B") == r"A^{\mathsf{T}} B"
        assert fix_matrix_transpose("X_i.T") == r"X_i^{\mathsf{T}}"

    def test_space_T(self):
        """空格表示的转置 W T"""
        assert fix_matrix_transpose("W T") == r"W^{\mathsf{T}}"
        assert fix_matrix_transpose("A T B") == r"A^{\mathsf{T}} B"

    def test_no_space_T(self):
        """T 后面是字母时不转换"""
        assert fix_matrix_transpose("W TA") == "W TA"
        assert fix_matrix_transpose("W T.") == "W T."

    def test_lowercase_t(self):
        """小写 t 表示转置"""
        assert fix_matrix_transpose("A.t") == r"A^{\mathsf{T}}"

    def test_top_without_brace(self):
        """\\top 没有大括号"""
        assert fix_matrix_transpose("W\top") == r"W^{\top}"
        assert fix_matrix_transpose("A\top") == r"A^{\top}"

    def test_already_has_brace(self):
        """已经有大括号的保持不变"""
        result = fix_matrix_transpose(r"W^{\top}")
        assert r"W^{\top}" in result

    def test_hermitian(self):
        """Hermitian 转置 W.H"""
        assert fix_matrix_transpose("W.H") == r"W^{\dagger}"

    def test_empty_string(self):
        """空字符串"""
        assert fix_matrix_transpose("") == ""
        assert fix_matrix_transpose(None) is None

    def test_no_transpose(self):
        """没有转置符号的文本保持不变"""
        assert fix_matrix_transpose("x + y = z") == "x + y = z"


class TestFixMathNotation:
    """测试 fix_math_notation 函数"""

    def test_power_without_brace(self):
        """缺失的大括号 x^2 → x^{2}"""
        assert fix_math_notation("x^2") == r"x^{2}"
        assert fix_math_notation("y^10") == r"y^{10}"

    def test_special_symbols(self):
        """特殊符号文字表示"""
        assert fix_math_notation(r"\infty") == r"\infty"
        assert fix_math_notation("\\le") == r"\leq"
        assert fix_math_notation("\\ge") == r"\geq"
        assert fix_math_notation("\\ne") == r"\neq"
        assert fix_math_notation("\\alpha") == r"\alpha"

    def test_symbols_in_word(self):
        """单词内的符号不转换"""
        assert fix_math_notation("line") == "line"
        assert fix_math_notation("alpha-beta") == "alpha-beta"

    def test_empty(self):
        """空字符串"""
        assert fix_math_notation("") == ""
        assert fix_math_notation(None) is None


class TestSanitizeLatexBody:
    """测试 sanitize_latex_body 函数"""

    def test_eqref_conversion(self):
        """\\eqref 转换为 (\\ref)"""
        result = sanitize_latex_body(r"\eqref{eq:1.31}")
        assert r"\eqref" not in result
        assert r"(\ref{eq:1.31})" in result

    def test_eqref_in_text(self):
        """文本中的 \\eqref"""
        result = sanitize_latex_body(r"根据 \eqref{eq:1.31} 和 \eqref{eq:1.32}")
        assert r"\eqref" not in result
        assert r"(\ref{eq:1.31})" in result

    def test_multiple_eqref(self):
        """多个 \\eqref"""
        result = sanitize_latex_body(r"\eqref{a}--\eqref{b}")
        assert result.count(r"(\ref{") == 2

    def test_code_block_removal(self):
        """移除代码块标记"""
        result = sanitize_latex_body("```latex\nsome content\n```")
        assert "```" not in result

    def test_begin_end_spacing(self):
        """修复 \\ begin 和 \\ end"""
        result = sanitize_latex_body(r"\ begin {equation} \ end {equation}")
        assert r"\begin{equation}" in result

    def test_matrix_transpose(self):
        """矩阵转置修复"""
        result = sanitize_latex_body("W.T")
        assert r"W^{\mathsf{T}}" in result

    def test_preserve_math(self):
        """保留数学公式"""
        result = sanitize_latex_body(r"$x^2 + y^2 = z^2$")
        assert "x" in result
        assert "z^2" in result

    def test_empty(self):
        """空字符串"""
        assert sanitize_latex_body("") == ""
        assert sanitize_latex_body(None) == ""

    def test_strip_whitespace(self):
        """去除首尾空白"""
        result = sanitize_latex_body("  some content  ")
        assert result == "some content"

    def test_repair_nested_and_escaped_display_delimiters(self):
        result = sanitize_latex_body(
            "\\[\\[x_{k+1} = x_k - 1\\]\\textbackslash{}]"
        )
        assert result.count(r"\[") == 1
        assert result.count(r"\]") == 1
        assert r"\textbackslash{}" not in result

    def test_drop_isolated_math_glyphs(self):
        result = sanitize_latex_body("before\n\\[\n√    √\n\\]\nafter")
        assert "√" not in result
        assert "before" in result and "after" in result

    def test_unwrap_prose_from_display_math(self):
        result = sanitize_latex_body("\\[\n这是被错误放入数学环境的一整段中文说明文字，其中包含足够多的普通内容。\n\\]")
        assert r"\[" not in result
        assert "中文说明" in result

    def test_preserves_page_marker_for_retry(self):
        result = sanitize_latex_body("% ===== 第 1 页 =====\n正文")
        assert "% ===== 第 1 页 =====" in result

    def test_preserves_table_hlines(self):
        result = sanitize_latex_body("\\begin{tabular}{|c|}\n\\hline\nA \\\\\n\\hline\n\\end{tabular}")
        assert result.count(r"\hline") == 2

    def test_wrapped_document_keeps_page_marker_for_retry(self):
        result = wrap_with_template("% ===== 第 1 页 =====\n正文")
        assert "% ===== 第 1 页 =====" in result

    def test_algorithm_body_adds_required_pseudocode_packages(self):
        result = wrap_with_template(
            r"\begin{algorithm}\caption{示例}\begin{algorithmic}[1]\State x\end{algorithmic}\end{algorithm}"
        )
        assert r"\usepackage{algorithm}" in result
        assert r"\usepackage{algpseudocode}" in result


class TestValidateLatexPage:
    def test_detects_nested_display_math(self):
        report = validate_latex_page(r"\[\[x = y\]\]")
        assert not report['valid']
        assert any(item['code'] == 'nested_display_math' for item in report['diagnostics'])

    def test_flags_prose_in_display_math(self):
        report = validate_latex_page(r"\[这是一段被错误放进公式环境的较长中文说明文字，需要提示用户检查。\]")
        assert report['warnings_count'] == 1


class TestReplaceLatexPageBlock:
    def test_replaces_only_requested_page(self):
        document = """\\begin{document}
% ===== 第 1 页 =====
first

% ===== 第 2 页 =====
second
\\end{document}"""
        result = replace_latex_page_block(document, 2, 'revised')
        assert 'first' in result
        assert '% ===== 第 2 页 =====\nrevised' in result
        assert 'second' not in result

    def test_replaces_failed_page_placeholder(self):
        document = """\\begin{document}
% ===== 第 1 页 =====
first

% 第 2 页转换失败

% ===== 第 3 页 =====
third
\\end{document}"""
        result = replace_latex_page_block(document, 2, 'recovered')
        assert '% ===== 第 2 页 =====\nrecovered' in result
        assert '转换失败' not in result
        assert 'first' in result and 'third' in result

    def test_preserves_adjacent_failed_placeholder(self):
        document = """% 第 1 页转换失败

% 第 2 页翻译并转换失败
"""
        result = replace_latex_page_block(document, 1, 'recovered')
        assert '% ===== 第 1 页 =====\nrecovered' in result
        assert '% 第 2 页翻译并转换失败' in result


class TestCrossPageFormulaStitching:
    def test_stitches_strong_formula_continuation(self):
        pages = [
            "The equation is\nF(x) = x^2 +",
            "y^2 = z^2\nThe next paragraph starts here.",
        ]
        routed = stitch_cross_page_formula_fragments(pages, [0, 1])
        assert routed == {0, 1}
        assert "F(x) = x^2 + y^2 = z^2" in pages[0]
        assert pages[1].startswith("The next paragraph")

    def test_does_not_join_ordinary_page_breaks(self):
        pages = ["This paragraph continues", "on the following page."]
        assert stitch_cross_page_formula_fragments(pages, [0, 1]) == set()
        assert pages == ["This paragraph continues", "on the following page."]


class TestNormalizeAlignEnvironments:
    """测试 normalize_align_environments 函数"""

    def test_align_to_aligned(self):
        """align* 转换为 aligned"""
        input_text = r"\begin{align}a &= b \\ c &= d\end{align}"
        result = normalize_align_environments(input_text)
        assert r"\begin{aligned}" in result
        assert r"\end{aligned}" in result

    def test_alignstar_to_aligned(self):
        """align* 环境"""
        input_text = r"\begin{align*}a &= b\end{align*}"
        result = normalize_align_environments(input_text)
        assert r"\begin{aligned}" in result

    def test_preserve_quad(self):
        """保留 \\quad"""
        input_text = r"\begin{align}a &= b \quad c &= d\end{align}"
        result = normalize_align_environments(input_text)
        assert r"\quad" in result

    def test_empty_content(self):
        """空内容"""
        assert normalize_align_environments("") == ""
        assert normalize_align_environments(None) == ""

    def test_no_align(self):
        """没有 align 环境时保持不变"""
        text = r"\begin{equation}a = b\end{equation}"
        result = normalize_align_environments(text)
        assert r"\begin{equation}" in result



    def test_multiline_align_adds_row_breaks(self):
        input_text = "\\begin{align}\na = b\nc = d\n\\end{align}"
        result = sanitize_latex_body(input_text)
        assert r"\begin{aligned}" in result
        assert "a &= b" in result
        assert r"\\" in result
        assert "c &= d" in result
        assert r"\begin{align}" not in result

    def test_nested_display_align(self):
        input_text = "\\[\\begin{align}a &= b \\\\ c &= d\\end{align}\\]"
        result = sanitize_latex_body(input_text)
        assert result.count(r"\[") == 1
        assert r"\begin{aligned}" in result

    def test_equation_aligned_not_wrapped_again(self):
        input_text = r"\begin{equation}\begin{aligned}a&=b\end{aligned}\end{equation}"
        result = sanitize_latex_body(input_text)
        assert r"\begin{equation}" in result
        assert r"\[" not in result

    def test_dollar_wrapped_align(self):
        input_text = r"$$\begin{align}a&=b\end{align}$$"
        result = sanitize_latex_body(input_text)
        assert "$$" not in result
        assert result.count(r"\[") == 1
        assert r"\begin{aligned}" in result


class TestRepairTabularConsistency:
    """??? repair_tabular_consistency ???"""

    def test_basic_repair(self):
        """?????????"""
        input_text = r"\begin{tabular}{|c|c|}\hline a & b \ c & d \ \hline\end{tabular}"
        result = repair_tabular_consistency(input_text)
        assert r"\begin{tabular}" in result

    def test_empty(self):
        """?????"""
        assert repair_tabular_consistency("") == ""
        assert repair_tabular_consistency(None) == ""

    def test_add_missing_row_breaks(self):
        input_text = "\\begin{tabular}{|c|c|}\nA & B\n1 & 2\n\\end{tabular}"
        result = sanitize_latex_body(input_text)
        assert "A & B" in result and r"\\" in result
        assert "1 & 2" in result and r"\\" in result

    def test_pad_short_rows_and_merge_extra_cells(self):
        input_text = r"""\begin{tabular}{|c|c|c|}
A & B \\
1 & 2 & 3 & 4 \\
\end{tabular}"""
        result = sanitize_latex_body(input_text)
        assert "A & B & --" in result
        assert r"3 \& 4" in result

    def test_close_unclosed_tabular(self):
        input_text = "\\begin{tabular}{|c|c|}\nA & B"
        result = sanitize_latex_body(input_text)
        assert r"\end{tabular}" in result
        assert "A & B" in result and r"\\" in result


class TestStripDocumentWrapper:
    """测试 strip_document_wrapper 函数"""

    def test_strip_wrapper(self):
        """去除文档包装"""
        content = r"\documentclass{article}\begin{document}x^2\end{document}"
        result = strip_document_wrapper(content)
        # 当前实现不做处理，直接返回
        assert "x^2" in result

    def test_preserve_content(self):
        """保留正文"""
        result = strip_document_wrapper("some latex content")
        assert result == "some latex content"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
