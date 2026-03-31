#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 模板与内容处理工具
"""

import re
from typing import List


def strip_document_wrapper(latex_content: str) -> str:
    """去除完整文档包装，仅保留正文。"""
    content = latex_content or ""
    patterns = [
        r"\\documentclass(\[.*?\])?\{.*?\}",
        r"\\usepackage(\[.*?\])?\{.*?\}",
        r"\\title\{.*?\}",
        r"\\author\{.*?\}",
        r"\\date\{.*?\}",
        r"\\maketitle",
    ]
    for p in patterns:
        content = re.sub(p, "", content, flags=re.DOTALL)

    content = re.sub(r"\\begin\{document\}", "", content)
    content = re.sub(r"\\end\{document\}", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def sanitize_latex_body(latex_content: str) -> str:
    """做一层无损清洗，提高输出稳定性。"""
    content = (latex_content or "").strip()
    content = re.sub(r"^```(?:latex)?", "", content, flags=re.IGNORECASE | re.MULTILINE)
    content = re.sub(r"```$", "", content, flags=re.MULTILINE)
    content = content.replace("\\ begin", "\\begin").replace("\\ end", "\\end")
    content = normalize_align_environments(content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def normalize_align_environments(content: str) -> str:
    """将 align/align* 统一改写为 display math + aligned，提升预览与编译兼容性。"""
    text = content or ""

    def _replace(match: re.Match) -> str:
        body = (match.group("body") or "").strip()
        if not body:
            return ""
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
        r"(?im)^\s*\d*\.?\s*(references|bibliography|works\s+cited)\s*[:：]?\s*$",
        r"(?i)\\section\*?\{\s*(references|bibliography|works\s+cited)\s*\}",
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
        return content, ""

    main_text = content[:split_index].rstrip()
    refs_text = content[split_index:].lstrip("\n")
    return main_text, refs_text


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
