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
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def wrap_with_template(body: str, template_name: str = "article", use_chinese: bool = False) -> str:
    """用模板包裹正文。"""
    clean_body = strip_document_wrapper(sanitize_latex_body(body))
    template_name = (template_name or "article").lower()

    base_packages = [
        r"\\usepackage{amsmath,amssymb,amsthm}",
        r"\\usepackage{graphicx}",
        r"\\usepackage{hyperref}",
    ]
    if use_chinese:
        base_packages.append(r"\\usepackage{xeCJK}")

    if template_name == "report":
        docclass = r"\\documentclass[12pt]{report}"
    elif template_name == "book":
        docclass = r"\\documentclass[12pt]{book}"
    elif template_name == "beamer":
        docclass = r"\\documentclass{beamer}"
    elif template_name == "cn-article":
        docclass = r"\\documentclass[12pt]{article}"
        if r"\\usepackage{xeCJK}" not in base_packages:
            base_packages.append(r"\\usepackage{xeCJK}")
    else:
        docclass = r"\\documentclass[12pt]{article}"

    lines = [docclass, *base_packages, "", r"\\begin{document}", "", clean_body, "", r"\\end{document}"]
    return "\n".join(lines)


def merge_tex_contents(contents: List[str], template_name: str = "article", use_chinese: bool = False) -> str:
    """将多个 tex 内容合并为一个文档。"""
    parts = []
    for idx, content in enumerate(contents, start=1):
        body = strip_document_wrapper(content)
        parts.append(f"% ===== 合并文档 {idx} =====")
        parts.append(body)
        parts.append(r"\\clearpage")
        parts.append("")

    merged_body = "\n".join(parts).strip()
    return wrap_with_template(merged_body, template_name=template_name, use_chinese=use_chinese)
