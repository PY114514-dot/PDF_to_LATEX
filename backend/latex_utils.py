#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 模板与内容处理工具
"""

import re
from typing import List


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
        r'\1^{\mathsf{T}}',
        text
    )

    # 模式2: 空格表示的转置 (W T, A T, X_i T) - 只在数学上下文中
    # 匹配: 字母/下标 + 空格 + T + 非字母
    # 使用负向先行断言确保 T 后面不是字母
    text = re.sub(
        r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\s+([T])(?![a-zA-Z])',
        r'\1^{\mathsf{T}}',
        text
    )

    # 模式3: 单独的 t 表示转置 (有时 AI 用小写 t)
    # 匹配: 矩阵变量后紧跟 ,t 或 )t
    text = re.sub(
        r'([A-Z])\.t\b',
        r'\1^{\mathsf{T}}',
        text
    )

    # 模式4: 修复 AI 忘记加大括号的 \top (W\top → W^{\top})
    # 但保留已经是 W^{\top} 的形式
    text = re.sub(
        r'(\w)\s*\\top\b',
        r'\1^{\\top}',
        text
    )

    # 模式5: 修复 AI 忘记加大括号的 \mathsf{T}
    text = re.sub(
        r'(\w)\s*\\mathsf\{T\}',
        r'\1^{\\mathsf{T}}',
        text
    )

    # 模式6: 修复单独的 ^T 没有大括号 (W^T → W^{T})
    # 但 W^{T} 已经正确，不需要修改
    text = re.sub(
        r'(\w)\^([A-Za-z])(?![{a-zA-Z])',
        r'\1^{\2}',
        text
    )

    # 模式7: 修复句点表示的 Hermitian 转置 (W.H → W^{\dagger})
    text = re.sub(
        r'(\w)\.H\b',
        r'\1^{\\dagger}',
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

    # 修复常见的特殊符号文字表示
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
        # 使用单词边界确保不替换变量名
        text = re.sub(old, new, text, flags=re.IGNORECASE)

    return text


def strip_document_wrapper(latex_content: str) -> str:
    """去除完整文档包装，仅保留正文。"""
    # 不做任何清理，因为 AI 在 prompt 里已经被要求不要输出文档结构命令
    return latex_content or ""


def sanitize_latex_body(latex_content: str) -> str:
    """做一层无损清洗，提高输出稳定性。"""
    content = (latex_content or "").strip()

    try:
        content = re.sub(r"^```(?:latex)?", "", content, flags=re.IGNORECASE | re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE)
    except re.error:
        pass

    content = content.replace("\\ begin", "\\begin").replace("\\ end", "\\end")

    try:
        # 修复 \\eqref 不兼容 KaTeX 的问题
        # KaTeX 不支持 \\eqref，转为 (\\ref{...}) 格式
        content = re.sub(r'\\eqref\{([^}]+)\}', r'(\ref{\1})', content)
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
        # 移除内部的页码注释行（如 % ===== 第 19 页 =====）
        if re.match(r'^\s*%+\s*={3,}\s*第\s*\d+\s*页\s*={3,}\s*$', stripped):
            continue
        filtered_lines.append(line)
    return '\n'.join(filtered_lines)


def remove_excessive_hrules(content: str) -> str:
    r"""移除文中多余的 \hrule 命令（连续多个 \hrule 或孤立的 \hrule）。"""
    if not content:
        return content
    # 移除孤立的 \hrule（前后是空行的单行 \hrule）
    # 保留 \hrulefill（后者常用于签名栏等场景）
    lines = content.split('\n')
    filtered = []
    for line in lines:
        stripped = line.strip()
        # 跳过单独的 \hrule 或 \hrule 前后只有空行的情况
        if stripped in (r'\hrule', r'\hline', r'\HRule'):
            # 计数周围空行，避免误删正常表格中的 \hline
            continue
        filtered.append(line)
    result = '\n'.join(filtered)
    # 移除连续出现的多个 \hrule（2个及以上）
    result = re.sub(r'(\s*\\hrule\s*\n){2,}', '\n', result)
    return result


def normalize_align_environments(content: str) -> str:
    r"""将 align/align* 转换为支持多行的 aligned 环境，保留 \quad 等间距命令。"""
    text = content or ""

    def _replace(match: re.Match) -> str:
        body = (match.group("body") or "").strip()
        if not body:
            return ""
        # aligned 环境支持 \\ 分行，\quad 等间距命令可正常使用
        return "\\[\n\\begin{aligned}\n" + body + "\n\\end{aligned}\n\\]"

    pattern = re.compile(
        r"\\begin\{align\*?\}(?P<body>[\s\S]*?)\\end\{align\*?\}",
        flags=re.IGNORECASE,
    )
    return pattern.sub(_replace, text)


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
            if "\\\\" not in raw:
                fixed_lines.append(line)
                continue
            if re.match(r"^\\(hline|toprule|midrule|bottomrule|cmidrule)", stripped):
                fixed_lines.append(line)
                continue
            if "\\multicolumn" in stripped or "\\multirow" in stripped:
                fixed_lines.append(line)
                continue

            parts = re.split(r"(?<!\\)&", raw)
            if len(parts) < cols:
                parts.extend([" -- "] * (cols - len(parts)))
            elif len(parts) > cols:
                parts = parts[:cols - 1] + [" \\& ".join(parts[cols - 1:])]

            fixed_lines.append(" & ".join(part.strip() for part in parts))

        new_body = "\n".join(fixed_lines)
        return f"{begin}{new_body}{end}"

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
            spec_match = re.search(r'\{([^}]*)\}', begin)
            spec = spec_match.group(1) if spec_match else '||'
            col_count = _count_tabular_columns(spec)
            placeholder = " & ".join([" " * 8] * max(col_count, 2))
            return f"{begin}\n{placeholder}\n{end}"
        return match.group(0)

    content = empty_tabular_pattern.sub(_fix_empty_tabular, content)

    # 处理表格内被截断的短行——行长度 < 10 且以 & 结尾
    lines = content.split('\n')
    fixed_lines: List[str] = []
    in_tabular = False
    skip_blank_count = 0

    for line in lines:
        is_begin = re.match(r'\\begin\{(?:tabular|tabular\*)\*?', line, re.IGNORECASE)
        is_end = re.match(r'\\end\{(?:tabular|tabular\*)\*?', line, re.IGNORECASE)

        if is_begin:
            in_tabular = True
            skip_blank_count = 0
            fixed_lines.append(line)
            continue
        if is_end:
            in_tabular = False
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

            # 检测被截断的短行：只含少量字符 + 以 & 结尾
            if re.match(r'^[^&]*&\s*$', stripped) or (len(stripped) < 15 and stripped.count('&') == 1 and stripped.endswith('&')):
                # 可能是截断行，检查下一行是否 & 开头（继续了同一行）
                fixed_lines.append(line)
                continue

            skip_blank_count = 0
            fixed_lines.append(line)
        else:
            fixed_lines.append(line)

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
        r"\usepackage{multicol}",
    ]
    if use_chinese:
        base_packages.append(r"\usepackage{xeCJK}")

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
