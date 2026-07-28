#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 模板与内容处理工具
"""

import re
from typing import Any, Dict, List


def fix_matrix_transpose(text: str) -> str:
    r"""
    修复 PDF 提取或 AI 生成过程中丢失的矩阵转置符号。

    PDF 文本提取时，矩阵转置 T 经常丢失或错误表示：
    - W^T (上标) → W.T, W T, W·T, W,t (句点/空格/点号)
    - A^T B → A.T B, A T B
    - X_i^T → X_i.T, X_i T

    同时处理 AI 错误输出：
    - W\top → W^{\top} (有时 AI 忘记加大括号)
    - A.t → A^{\mathsf{T}} (小写 t 不是转置)

    Returns:
        修复后的文本
    """
    if not text:
        return text

    # 模式1: 句点/点号表示的转置 (W.T, A.T, X_i.T)
    # 匹配: 字母/下标 + . + T
    text = re.sub(
        r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\.([T])',
        lambda m: m.group(1) + r'^{\mathsf{T}}',
        text
    )

    # 模式2: 空格表示的转置 (W T, A T, X_i T) - 只在数学上下文中
    # 匹配: 字母/下标 + 空格 + T + 非字母
    # 使用负向先行断言确保 T 后面不是字母
    text = re.sub(
        r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\s+([T])(?![a-zA-Z.])',
        lambda m: m.group(1) + r'^{\mathsf{T}}',
        text
    )

    # 模式3: 单独的 t 表示转置 (有时 AI 用小写 t)
    # 匹配: 矩阵变量后紧跟 ,t 或 )t
    text = re.sub(
        r'([A-Z])\.t\b',
        lambda m: m.group(1) + r'^{\mathsf{T}}',
        text
    )

    # 模式4: 修复 AI 忘记加大括号的 \top (W\top → W^{\top})
    # 但保留已经是 W^{\top} 的形式
    text = re.sub(
        r'(\w)\s*\\top\b',
        lambda m: m.group(1) + r'^{\top}',
        text
    )
    text = re.sub(
        r'(\w)\top\b',
        lambda m: m.group(1) + r'^{\top}',
        text
    )

    # 模式5: 修复 AI 忘记加大括号的 \mathsf{T}
    text = re.sub(
        r'(\w)\s*\\mathsf\{T\}',
        lambda m: m.group(1) + r'^{\mathsf{T}}',
        text
    )

    # 模式6: 修复单独的 ^T 没有大括号 (W^T → W^{T})
    # 但 W^{T} 已经正确，不需要修改
    text = re.sub(
        r'(\w)\^([A-Za-z])(?![{a-zA-Z])',
        lambda m: m.group(1) + '^' + '{' + m.group(2) + '}',
        text
    )

    # 模式7: 修复句点表示的 Hermitian 转置 (W.H → W^{\dagger})
    text = re.sub(
        r'(\w)\.H\b',
        lambda m: m.group(1) + r'^{\dagger}',
        text
    )

    # 模式8: 修复句点表示的共轭转置 (W.* → W^{*})
    # 这个比较特殊，因为 .* 可能表示多种意思

    return text


def fix_math_notation(text: str) -> str:
    """
    修复常见的数学符号提取问题。

    处理 PDF 提取时丢失的上标/下标信息：
    - x^2 → x² (但已经是 Unicode 的保持)
    - x_i → xᵢ (下标)
    - 特殊符号如 ∞, ≤, ≥, ≠, ≈ 等可能丢失为文字

    Returns:
        修复后的文本
    """
    if not text:
        return text

    # 修复缺失的大括号 (x^2 → x^{2})
    text = re.sub(
        r'(\w)\^(\d+)(?![}a-zA-Z])',
        r'\1^{\2}',
        text
    )

    # 修复下划线形式的下标 (x_i → x_{i}) 但保持 x_i 格式
    # 这个只修复已经是 LaTeX 格式的情况

    command_replacements = {
        r'\\le\b': r'\leq',
        r'\\ge\b': r'\geq',
        r'\\ne\b': r'\neq',
    }
    for old, new in command_replacements.items():
        text = re.sub(old, lambda _, rep=new: rep, text, flags=re.IGNORECASE)

    # 修复常见的特殊符号文字表示；避免替换已有 LaTeX 命令和连字符词。
    replacements = {
        r'\binfinity\b': r'\infty',
        r'\ble\b': r'\leq',
        r'\bge\b': r'\geq',
        r'\bne\b': r'\neq',
        r'\bleq\b': r'\leq',
        r'\bgeq\b': r'\geq',
        r'\bsum\b': r'\sum',
        r'\bprod\b': r'\prod',
        r'\bint\b': r'\int',
        r'\balpha\b': r'\alpha',
        r'\bbeta\b': r'\beta',
        r'\bgamma\b': r'\gamma',
        r'\bdelta\b': r'\delta',
        r'\blambda\b': r'\lambda',
        r'\bmu\b': r'\mu',
        r'\bsigma\b': r'\sigma',
        r'\bphi\b': r'\phi',
        r'\bvarphi\b': r'\varphi',
        r'\bpsi\b': r'\psi',
        r'\bomega\b': r'\omega',
        r'\bepsilon\b': r'\epsilon',
    }

    for old, new in replacements.items():
        guarded = old.replace(r'\b', r'(?<![\\-])\b', 1)
        if guarded.endswith(r'\b'):
            guarded = guarded[:-2] + r'\b(?!-)'
        text = re.sub(guarded, lambda _, rep=new: rep, text, flags=re.IGNORECASE)

    return text


def strip_document_wrapper(latex_content: str) -> str:
    """去除完整文档包装，仅保留正文。"""
    # 不做任何清理，因为 AI 在 prompt 里已经被要求不要输出文档结构命令
    return latex_content or ""


def _is_math_fragment(fragment: str) -> bool:
    """Return whether a display-math fragment is substantial enough to keep."""
    compact = re.sub(r"\s+", "", fragment or "")
    if not compact:
        return False

    # PDF extraction occasionally leaves a line containing only a glyph from a
    # split formula (most commonly ``√``).  Rendering such a fragment is both
    # misleading and useless, so remove it instead of creating a broken block.
    if re.fullmatch(r"[√∑∫∏±∓≈≠≤≥=+\-*/·.,:;()\[\]{}|]+", compact):
        return False

    # A lone variable or command is normally another piece of a split formula;
    # keeping it as display math produces the isolated symbols seen in previews.
    if re.fullmatch(r"(?:[A-Za-z0-9]|\\[A-Za-z]+)", compact):
        return False
    return True


def _is_prose_in_display_math(fragment: str) -> bool:
    """Detect explanatory prose that was incorrectly wrapped in ``\\[...\\]``."""
    text = (fragment or "").strip()
    if not text:
        return False
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_words = re.findall(r"[A-Za-z]{3,}", text)
    # A normal equation can contain a short \text{} annotation.  Only unwrap a
    # block when it is clearly sentence-like rather than mathematical.
    return (cjk_count >= 8 and len(text) >= 24) or (
        len(ascii_words) >= 6 and len(text) >= 60 and not re.search(r"\\(?:frac|sum|int|begin|left|right)", text)
    )


def repair_display_math_delimiters(content: str) -> str:
    """Repair malformed display-math delimiters emitted by OCR or an LLM.

    The parser deliberately keeps only properly paired ``\\[ ... \\]`` blocks,
    flattens accidental nesting, and turns prose blocks back into ordinary text.
    This prevents a single malformed delimiter from making the rest of a page
    invalid LaTeX/KaTeX.
    """
    if not content:
        return content

    # An escaped backslash followed by a bracket is a common local-conversion
    # residue (``\\textbackslash{}]``), not literal text that should reach TeX.
    content = re.sub(r"\\textbackslash\{\}\s*\\?([\[\]])", "", content)

    output: List[str] = []
    math_parts: List[str] = []
    in_display_math = False
    cursor = 0
    for match in re.finditer(r"\\[\[\]]", content):
        segment = content[cursor:match.start()]
        token = match.group(0)
        cursor = match.end()

        if token == r"\[":
            if in_display_math:
                # Nested display math is invalid; retain its intervening text
                # in the already-open block and ignore the redundant opener.
                math_parts.append(segment)
            else:
                output.append(segment)
                math_parts = []
                in_display_math = True
            continue

        if not in_display_math:
            # Drop unmatched closers.  They are always malformed LaTeX here.
            output.append(segment)
            continue

        math_parts.append(segment)
        body = "".join(math_parts).strip()
        if _is_math_fragment(body):
            if _is_prose_in_display_math(body):
                output.append(body)
            else:
                output.append("\\[\n" + body + "\n\\]")
        in_display_math = False
        math_parts = []

    tail = content[cursor:]
    if in_display_math:
        # An opener without a matching closer must not swallow the remainder of
        # the document into math mode.  Preserve its text as ordinary content.
        output.append("".join(math_parts) + tail)
    else:
        output.append(tail)
    return "".join(output)


def validate_latex_page(latex_content: str) -> Dict[str, Any]:
    """Return lightweight, page-scoped diagnostics for generated LaTeX.

    This deliberately complements (rather than replaces) a full TeX compiler:
    it is fast enough to run for every converted PDF page and reports problems
    in terms that the conversion UI can display before a user downloads a file.
    """
    text = latex_content or ""
    diagnostics: List[Dict[str, Any]] = []

    def add(code: str, severity: str, message: str, line: int) -> None:
        diagnostics.append({
            'code': code,
            'severity': severity,
            'message': message,
            'line': line,
        })

    display_opens = [match.start() for match in re.finditer(r"\\\[", text)]
    display_closes = [match.start() for match in re.finditer(r"\\\]", text)]
    if len(display_opens) != len(display_closes):
        add(
            'unbalanced_display_math', 'error', '显示公式定界符 \\[ 与 \\] 数量不匹配。', 1
        )

    inline_opens = [match.start() for match in re.finditer(r"\\\(", text)]
    inline_closes = [match.start() for match in re.finditer(r"\\\)", text)]
    if len(inline_opens) != len(inline_closes):
        add(
            'unbalanced_inline_math', 'error', '行内公式定界符 \\( 与 \\) 数量不匹配。', 1
        )

    for match in re.finditer(r"\\\[\s*\\\[", text):
        add(
            'nested_display_math', 'error', '检测到嵌套显示公式，KaTeX 无法渲染。',
            text.count('\n', 0, match.start()) + 1,
        )
    for match in re.finditer(r"\\textbackslash\{\}\s*\\?[]]", text):
        add(
            'escaped_math_delimiter', 'error', '检测到被错误转义的公式结束符。',
            text.count('\n', 0, match.start()) + 1,
        )
    for match in re.finditer(r"\\\[\s*([√∑∫∏±∓≈≠≤≥=+\-*/·.,:;()\[\]{}|\s]+)\s*\\\]", text):
        add(
            'isolated_math_fragment', 'warning', '检测到疑似被拆分的孤立公式符号。',
            text.count('\n', 0, match.start()) + 1,
        )
    for match in re.finditer(r"\\\[([\s\S]*?)\\\]", text):
        body = match.group(1)
        if len(body) >= 24 and len(re.findall(r"[\u4e00-\u9fff]", body)) >= 8:
            add(
                'prose_in_display_math', 'warning', '检测到较长的中文正文被放入显示公式。',
                text.count('\n', 0, match.start()) + 1,
            )

    errors = sum(item['severity'] == 'error' for item in diagnostics)
    warnings = sum(item['severity'] == 'warning' for item in diagnostics)
    return {
        'valid': errors == 0,
        'errors_count': errors,
        'warnings_count': warnings,
        'diagnostics': diagnostics,
    }


def replace_latex_page_block(document: str, page_num: int, replacement: str) -> str:
    """Replace one generated ``% ===== 第 N 页 =====`` block in a document.

    Keeping page replacement here makes a later retry endpoint safe: it can
    update one page without rebuilding or losing every other converted page.
    """
    if page_num < 1:
        raise ValueError('page_num must be 1-based')
    marker = rf"% ===== 第 {page_num} 页 ====="
    # Failed pages deliberately use a compact placeholder instead of a normal
    # page block.  A retry must be able to replace that placeholder too.
    failed_marker = rf"% 第 {page_num} 页(?:转换|翻译并转换)失败"
    next_boundary = (
        r"(?=^% ===== 第 \d+ 页 =====|"
        r"^% 第 \d+ 页(?:转换|翻译并转换)失败|"
        r"^\\end\{document\}|\Z)"
    )
    pattern = re.compile(
        rf"^(?:{re.escape(marker)}|{failed_marker})\n.*?{next_boundary}",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(document or '')
    if not match:
        raise ValueError(f'找不到第 {page_num} 页的 LaTeX 内容块')

    clean_replacement = (replacement or '').strip()
    if clean_replacement.startswith(marker):
        clean_replacement = clean_replacement[len(marker):].lstrip('\r\n')
    return (document[:match.start()] + marker + '\n' + clean_replacement.rstrip() + '\n\n' + document[match.end():])


def _boundary_formula_lines(text: str, at_end: bool) -> tuple[List[str], int]:
    lines = (text or '').splitlines()
    indices = [
        index for index, line in enumerate(lines)
        if line.strip() and not (line.strip().startswith('[') and line.strip().endswith(']'))
    ]
    if not indices:
        return lines, -1
    return lines, indices[-1] if at_end else indices[0]


def stitch_cross_page_formula_fragments(
    pages_text: List[str], selected_pages: List[int]
) -> set[int]:
    """Conservatively retain a formula split across two consecutive pages.

    Both sides must exhibit math-specific continuation evidence.  This avoids
    joining normal prose that happens to cross a PDF page break.
    """
    routed_pages: set[int] = set()
    for previous, following in zip(selected_pages, selected_pages[1:]):
        if following != previous + 1:
            continue
        previous_lines, tail_index = _boundary_formula_lines(pages_text[previous], at_end=True)
        following_lines, head_index = _boundary_formula_lines(pages_text[following], at_end=False)
        if tail_index < 0 or head_index < 0:
            continue
        tail, head = previous_lines[tail_index].strip(), following_lines[head_index].strip()
        tail_unfinished = bool(
            re.search(r'(?:[=+*/^_({\[]|\\(?:frac|sum|int|prod|left|begin\{[^}]+\}))\s*$', tail)
            or tail.count('{') > tail.count('}')
            or tail.count('(') > tail.count(')')
            or tail.count('[') > tail.count(']')
        )
        head_math = (
            head.startswith(('+', '*', '/', '=', ',', ')', ']', '}'))
            or head.startswith(('\\frac', '\\sum', '\\int', '\\prod', '\\sqrt', '\\right', '\\end{'))
            or bool(re.match(r'^[A-Za-z]\s*(?:[_^=]|\()', head))
        )
        if not (tail_unfinished and head_math):
            continue
        previous_lines[tail_index] = f"{tail} {head}"
        following_lines.pop(head_index)
        pages_text[previous] = '\n'.join(previous_lines).strip()
        pages_text[following] = '\n'.join(following_lines).strip()
        routed_pages.update({previous, following})
    return routed_pages


def sanitize_latex_body(latex_content: str) -> str:
    """做一层无损清洗，提高输出稳定性。"""
    content = (latex_content or "").strip()

    try:
        content = re.sub(r"^```(?:latex)?", "", content, flags=re.IGNORECASE | re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE)
    except re.error:
        pass

    content = content.replace("\\ begin", "\\begin").replace("\\ end", "\\end")
    content = re.sub(r'\\(begin|end)\s+\{', r'\\\1{', content)

    try:
        content = repair_display_math_delimiters(content)
    except re.error:
        pass

    try:
        # 修复 \\eqref 不兼容 KaTeX 的问题
        # KaTeX 不支持 \\eqref，转为 (\\ref{...}) 格式
        content = re.sub(r'\\eqref\{([^}]+)\}', lambda m: r'(\ref{' + m.group(1) + '})', content)
    except re.error:
        pass

    try:
        content = fix_matrix_transpose(content)  # 修复矩阵转置符号
    except re.error:
        pass

    try:
        content = normalize_align_environments(content)
    except re.error:
        pass

    try:
        content = repair_tabular_consistency(content)
    except re.error:
        pass

    try:
        content = repair_latex_tables(content)
    except re.error:
        pass

    # 移除独立的页码数字（如 "19", "20" 等单独出现在一行的数字）
    try:
        content = remove_standalone_page_numbers(content)
    except re.error:
        pass

    # 清理多余的 \hrule 命令（豆包等模型容易滥用）
    try:
        content = remove_excessive_hrules(content)
    except re.error:
        pass

    # 移除残留的 [TWO_COLUMN_PAGE] 标记（LLM 未处理时清理）
    try:
        content = re.sub(r'\[TWO_COLUMN_PAGE\]', '', content)
        # Output is deliberately single-column.  Source-PDF column detection
        # helps reading order, but must not force a page-layout environment.
        content = re.sub(r'\\begin\{multicols\}\{\d+\}\s*', '', content)
        content = re.sub(r'\\end\{multicols\}\s*', '', content)
        content = re.sub(r'\\vspace(?:\*?)\{[^{}]*\}\s*', '', content)
        content = re.sub(r'\\(?:newpage|pagebreak|clearpage)\s*', '', content)
        content = re.sub(r"\n{3,}", "\n\n", content)
    except re.error:
        pass

    return content.strip()


def remove_standalone_page_numbers(content: str) -> str:
    """移除单独出现在一行中的页码数字（如正文中的 "19", "20"）。"""
    if not content:
        return content
    # 匹配单独一行且只有数字的内容（可能是PDF提取的页码）
    # 但保留图表编号如 "图1", "表1", "Figure 1", "Table 1" 等
    lines = content.split('\n')
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # 如果一行只有数字（2-4位），很可能是页码
        if re.match(r'^\d{2,4}\s*$', stripped):
            continue
        # 页级标记是单页重试定位所需的元数据，不能作为页码噪声删除。
        filtered_lines.append(line)
    return '\n'.join(filtered_lines)


def remove_excessive_hrules(content: str) -> str:
    r"""移除文中多余的 \hrule 命令，同时保留表格的 \hline。"""
    if not content:
        return content
    # 移除孤立的 \hrule（前后是空行的单行 \hrule）
    # 保留 \hrulefill（后者常用于签名栏等场景）
    lines = content.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        # \hline 是 tabular 的合法行分隔符，不能在全局清理阶段删除。
        if stripped in (r'\hrule', r'\HRule'):
            continue
        filtered.append(line)
    result = '\n'.join(filtered)
    # 移除连续出现的多个 \hrule（2个及以上）
    result = re.sub(r'(\s*\\hrule\s*\n){2,}', '\n', result)
    return result


def normalize_align_environments(content: str) -> str:
    r"""Convert fragile align/align* output to display math with aligned."""
    text = content or ""

    text = re.sub(
        r"\\\[\s*(\\begin\{align\*?\})",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(\\end\{align\*?\})\s*\\\]",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\$\$\s*(\\begin\{align\*?\})",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(\\end\{align\*?\})\s*\$\$",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    def _normalize_align_body(body: str) -> str:
        body = (body or "").strip()
        if not body:
            return ""

        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if len(lines) > 1:
            normalized_lines = []
            for idx, line in enumerate(lines):
                if idx < len(lines) - 1 and not line.rstrip().endswith(r"\\"):
                    line = line.rstrip() + r" \\"
                normalized_lines.append(line)
            body = "\n".join(normalized_lines)

        fixed_lines = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and "&" not in stripped and "=" in stripped and not stripped.startswith("\\"):
                line = re.sub(r"\s*=\s*", r" &= ", line, count=1)
            fixed_lines.append(line)
        body = "\n".join(fixed_lines).strip()
        return re.sub(r"\\\\\s*$", "", body)

    def _replace(match: re.Match) -> str:
        body = _normalize_align_body(match.group("body") or "")
        if not body:
            return ""
        return "\\[\n\\begin{aligned}\n" + body + "\n\\end{aligned}\n\\]"

    pattern = re.compile(
        r"\\begin\{align\*?\}(?P<body>[\s\S]*?)\\end\{align\*?\}",
        flags=re.IGNORECASE,
    )
    text = pattern.sub(_replace, text)

    aligned_pattern = re.compile(
        r"\\begin\{aligned\}[\s\S]*?\\end\{aligned\}",
        flags=re.IGNORECASE,
    )

    def _wrap_bare_aligned(match: re.Match) -> str:
        prefix = text[:match.start()]
        suffix = text[match.end():]
        if prefix.rstrip().endswith(r"\[") and suffix.lstrip().startswith(r"\]"):
            return match.group(0)
        if prefix.rstrip().endswith("$$") and suffix.lstrip().startswith("$$"):
            return match.group(0)

        begin_equation = max(
            prefix.rfind(r"\begin{equation}"),
            prefix.rfind(r"\begin{equation*}"),
            prefix.rfind(r"\begin{displaymath}"),
        )
        end_equation = max(
            prefix.rfind(r"\end{equation}"),
            prefix.rfind(r"\end{equation*}"),
            prefix.rfind(r"\end{displaymath}"),
        )
        if begin_equation > end_equation:
            return match.group(0)

        return "\n\\[\n" + match.group(0).strip() + "\n\\]\n"

    text = aligned_pattern.sub(_wrap_bare_aligned, text)
    return text

def split_references_section(text: str) -> tuple[str, str]:
    """拆分正文与参考文献部分，参考文献部分将保持原样不翻译。"""
    content = text or ""
    if not content.strip():
        return "", ""

    patterns = [
        r"(?im)^\s*(references|bibliography|works\s+cited)\s*[:：]?\s*$",
        r"(?im)^\s*(参考文献|参考资料|文献)\s*[:：]?\s*$",
        r"(?im)^\s*\d*\.?\s*(references|bibliography|works\s+cited)\s*[:：]?\s*$",
        r"(?im)^\s*\d*\.?\s*(参考文献|参考资料|文献)\s*[:：]?\s*$",
        r"(?i)\\section\*?\{\s*(references|bibliography|works\s+cited)\s*\}",
        r"(?i)\\section\*?\{\s*(参考文献|参考资料|文献)\s*\}",
        r"(?i)\\begin\{thebibliography\}",
    ]

    split_index = None
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            idx = match.start()
            if split_index is None or idx < split_index:
                split_index = idx

    if split_index is None:
        split_index = _detect_tail_references_start(content)

    # 进一步检测：以 [数字] 开头的连续行（参考文献格式）
    if split_index is None:
        ref_start = _detect_brackets_ref_start(content)
        if ref_start is not None:
            split_index = ref_start

    if split_index is None:
        return content, ""

    main_text = content[:split_index].rstrip()
    refs_text = content[split_index:].lstrip("\n")
    return main_text, refs_text


def _detect_tail_references_start(content: str) -> int | None:
    """通过末尾引用样式启发式检测参考文献起点。"""
    lines = content.splitlines(keepends=True)
    if not lines:
        return None

    line_offsets = []
    cursor = 0
    for line in lines:
        line_offsets.append(cursor)
        cursor += len(line)

    numbered_ref = re.compile(r"^\s*(\[\d+\]|\(\d+\)|\d+\.)\s+.+")
    year_ref = re.compile(r"\b(19|20)\d{2}\b")
    author_sep = re.compile(r",\s*[A-Z][a-zA-Z\-']+|\bet\s+al\.|\bvol\.|\bpp\.", flags=re.IGNORECASE)

    def is_ref_line(text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if numbered_ref.match(stripped):
            return True
        return bool(year_ref.search(stripped) and author_sep.search(stripped))

    tail_nonempty_indices = [i for i, line in enumerate(lines) if line.strip()]
    if len(tail_nonempty_indices) < 4:
        return None

    start = None
    hit_count = 0
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if not line.strip():
            if hit_count >= 4:
                start = i + 1
            continue

        if is_ref_line(line):
            hit_count += 1
            start = i
        elif hit_count >= 4:
            break
        else:
            hit_count = 0
            start = None

    if start is None or hit_count < 4:
        return None

    # 仅当参考文献区位于文档后 40% 时才触发，避免误分割正文列表。
    if start / max(len(lines), 1) < 0.6:
        return None

    return line_offsets[start]


def _detect_brackets_ref_start(content: str) -> int | None:
    """检测以 [数字] 开头的连续参考文献行（如 [10]、[11] 等）。"""
    lines = content.splitlines(keepends=True)
    if not lines:
        return None

    line_offsets = []
    cursor = 0
    for line in lines:
        line_offsets.append(cursor)
        cursor += len(line)

    # 匹配 [数字] 或 [数字, ...] 开头的行
    bracket_ref_pattern = re.compile(r"^\s*\[\d+\]")

    # 扫描寻找连续的参考文献行（至少5行）
    consecutive_refs = 0
    first_ref_offset = None

    for i, line in enumerate(lines):
        if bracket_ref_pattern.match(line.strip()):
            if consecutive_refs == 0:
                first_ref_offset = line_offsets[i]
            consecutive_refs += 1
        else:
            if consecutive_refs >= 5 and first_ref_offset is not None:
                # 参考文献必须在文档后50%才触发
                if first_ref_offset / max(len(content), 1) > 0.5:
                    return first_ref_offset
            consecutive_refs = 0
            first_ref_offset = None

    # 结尾检查
    if consecutive_refs >= 5 and first_ref_offset is not None:
        if first_ref_offset / max(len(content), 1) > 0.5:
            return first_ref_offset

    return None


def _count_tabular_columns(spec: str) -> int:
    """估算 tabular 列数。"""
    if not spec:
        return 0

    text = spec
    text = re.sub(r"[|\s]", "", text)
    text = re.sub(r"@\{[^{}]*\}", "", text)
    text = re.sub(r">\{[^{}]*\}", "", text)
    text = re.sub(r"<\{[^{}]*\}", "", text)
    text = re.sub(r"[pmb]\{[^{}]*\}", "P", text)

    return len(re.findall(r"[clrXSPQ]", text))


def _is_tabular_rule_line(line: str) -> bool:
    stripped = (line or "").strip()
    return bool(re.match(r"^\\(hline|toprule|midrule|bottomrule|cmidrule|cline)", stripped))


def _looks_like_tabular_data_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or stripped.startswith("%"):
        return False
    if _is_tabular_rule_line(stripped):
        return False
    if stripped.startswith("\\multicolumn") or stripped.startswith("\\multirow"):
        return True
    return "&" in stripped


def _repair_tabular_row(line: str, cols: int) -> str:
    raw = (line or "").rstrip()
    stripped = raw.strip()
    if not _looks_like_tabular_data_line(stripped):
        return line

    if stripped.endswith(r"\\"):
        raw = re.sub(r"\\\\\s*$", "", raw).rstrip()

    raw = re.sub(r"(?<!\\)&\s*$", "", raw).rstrip()

    if cols > 1 and "\\multicolumn" not in stripped and "\\multirow" not in stripped:
        parts = re.split(r"(?<!\\)&", raw)
        if len(parts) < cols:
            parts.extend([" -- "] * (cols - len(parts)))
        elif len(parts) > cols:
            extra = " \\& ".join(part.strip() for part in parts[cols - 1:])
            parts = parts[:cols - 1] + [extra]
        raw = " & ".join(part.strip() for part in parts)

    return raw.rstrip() + r" \\"


def repair_tabular_consistency(content: str) -> str:
    """修复 tabular 中行列数缺失导致的编译错误。"""
    text = content or ""

    try:
        pattern = re.compile(
            r"(?P<begin>\\begin\{tabular\*?\}(?:\[[^\]]*\])?\{(?P<spec>[^{}]*)\})"
            r"(?P<body>[\s\S]*?)"
            r"(?P<end>\\end\{tabular\*?\})",
            flags=re.IGNORECASE,
        )
    except re.error:
        return text

    def _fix_block(match: re.Match) -> str:
        begin = match.group("begin")
        body = match.group("body")
        end = match.group("end")
        cols = _count_tabular_columns(match.group("spec") or "")
        if cols <= 1:
            return f"{begin}{body}{end}"

        lines = body.splitlines()
        fixed_lines: List[str] = []

        for line in lines:
            raw = line.rstrip()
            stripped = raw.strip()
            if not stripped:
                fixed_lines.append(line)
                continue
            if stripped.startswith("%"):
                fixed_lines.append(line)
                continue
            if _is_tabular_rule_line(stripped):
                fixed_lines.append(line)
                continue
            fixed_lines.append(_repair_tabular_row(raw, cols))

        new_body = "\n".join(fixed_lines).strip()
        return f"{begin}\n{new_body}\n{end}"

    return pattern.sub(_fix_block, text)


def repair_latex_tables(content: str) -> str:
    r"""
    深度修复 LaTeX 表格的常见问题：
    1. 空表格（只有 & 分隔符但无实际内容）——保留表头行
    2. 表格内出现独立短行（LLM 输出时常见的截断问题）
    3. 多余的空行导致表格被拆分
    4. 含有 \multicolumn 但列数不足的行
    """
    if not content:
        return content

    # 先处理多行空表格（LLM 输出时整段表格全是空行）
    # 匹配空的 tabular 环境（只有 & 分隔符或多行空内容）
    empty_tabular_pattern = re.compile(
        r"(\\begin\{(?:tabular|tabular\*)\*?(?:\[[^\]]*\])?\{[^}]*\})"
        r"((?:\s*(?:&\s*)+[^\n]*\n)*)"
        r"(\\end\{(?:tabular|tabular\*)\*?\})",
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _fix_empty_tabular(match):
        begin = match.group(1)
        body = match.group(2)
        end = match.group(3)
        # 如果 body 里没有任何可读字符，保留一个最小占位行
        stripped = re.sub(r'\s+', '', body)
        if not stripped or stripped.count('&') < 2:
            # 从 begin 中提取列格式 spec
            spec_matches = re.findall(r'\{([^{}]*)\}', begin)
            spec = spec_matches[-1] if spec_matches else '||'
            col_count = _count_tabular_columns(spec)
            placeholder = " & ".join([" " * 8] * max(col_count, 2))
            return f"{begin}\n{placeholder}\n{end}"
        return match.group(0)

    content = empty_tabular_pattern.sub(_fix_empty_tabular, content)

    # 处理表格内被截断的短行——行长度 < 10 且以 & 结尾
    lines = content.split('\n')
    fixed_lines: List[str] = []
    in_tabular = False
    current_cols = 0
    skip_blank_count = 0

    for line in lines:
        is_begin = re.match(r'\\begin\{(?:tabular|tabular\*)\*?', line, re.IGNORECASE)
        is_end = re.match(r'\\end\{(?:tabular|tabular\*)\*?', line, re.IGNORECASE)

        if is_begin:
            in_tabular = True
            spec_match = re.search(r'\{([^{}]*)\}\s*$', line)
            current_cols = _count_tabular_columns(spec_match.group(1)) if spec_match else 0
            skip_blank_count = 0
            fixed_lines.append(line)
            continue
        if is_end:
            in_tabular = False
            current_cols = 0
            skip_blank_count = 0
            fixed_lines.append(line)
            continue

        if in_tabular:
            stripped = line.strip()
            # 跳过连续空行（最多保留 1 个）
            if not stripped:
                if skip_blank_count == 0:
                    fixed_lines.append(line)
                    skip_blank_count += 1
                continue

            # 清理注释行（用户可见）
            if stripped.startswith('%'):
                fixed_lines.append(line)
                continue

            skip_blank_count = 0
            fixed_lines.append(_repair_tabular_row(line, current_cols))
        else:
            fixed_lines.append(line)

    if in_tabular:
        fixed_lines.append(r"\end{tabular}")

    return '\n'.join(fixed_lines)


def _extract_beamer_blocks(body: str) -> List[str]:
    """按页面分隔注释切分为 beamer frame 内容块。"""
    content = (body or "").strip()
    if not content:
        return []

    # 兼容现有输出中的分页标记：% ===== 第 N 页 =====
    parts = re.split(r"(?m)^\s*%\s*=+\s*第\s*\d+\s*页\s*=+\s*$", content)
    blocks = [part.strip() for part in parts if part and part.strip()]
    return blocks if blocks else [content]


def _to_beamer_body(body: str) -> str:
    """确保 beamer 模板下正文包含 frame 环境。"""
    content = (body or "").strip()
    if not content:
        return ""

    if re.search(r"\\begin\{frame\}", content):
        return content

    blocks = _extract_beamer_blocks(content)
    frames = []
    for idx, block in enumerate(blocks, start=1):
        title = f"第 {idx} 页"
        frames.append("\\begin{frame}[fragile]")
        frames.append(f"\\frametitle{{{title}}}")
        frames.append(block)
        frames.append("\\end{frame}")
        frames.append("")

    return "\n".join(frames).strip()


def wrap_with_template(body: str, template_name: str = "article", use_chinese: bool = False) -> str:
    """用模板包裹正文。"""
    clean_body = strip_document_wrapper(sanitize_latex_body(body))
    template_name = (template_name or "article").lower()

    base_packages = [
        r"\usepackage{amsmath,amssymb,amsthm}",
        r"\usepackage{graphicx}",
        r"\usepackage{hyperref}",
    ]
    if use_chinese:
        base_packages.append(r"\usepackage{xeCJK}")
    if re.search(r"\\begin\{algorithm(?:ic)?\}", clean_body):
        # algorithm 提供浮动体/caption，algpseudocode 提供 algorithmic 伪代码命令。
        base_packages.extend([
            r"\usepackage{algorithm}",
            r"\usepackage{algpseudocode}",
        ])

    if template_name == "report":
        docclass = r"\documentclass[12pt]{report}"
    elif template_name == "book":
        docclass = r"\documentclass[12pt]{book}"
    elif template_name == "beamer":
        docclass = r"\documentclass{beamer}"
    elif template_name == "cn-article":
        docclass = r"\documentclass[12pt]{article}"
        if r"\usepackage{xeCJK}" not in base_packages:
            base_packages.append(r"\usepackage{xeCJK}")
    else:
        docclass = r"\documentclass[12pt]{article}"

    if template_name == "beamer":
        clean_body = _to_beamer_body(clean_body)

    lines = [docclass, *base_packages, "", r"\begin{document}", "", clean_body, "", r"\end{document}"]
    return "\n".join(lines)


def merge_tex_contents(contents: List[str], template_name: str = "article", use_chinese: bool = False) -> str:
    """将多个 tex 内容合并为一个文档。"""
    parts = []
    for idx, content in enumerate(contents, start=1):
        body = strip_document_wrapper(content)
        parts.append(f"% ===== 合并文档 {idx} =====")
        parts.append(body)
        parts.append(r"\clearpage")
        parts.append("")

    merged_body = "\n".join(parts).strip()
    return wrap_with_template(merged_body, template_name=template_name, use_chinese=use_chinese)
