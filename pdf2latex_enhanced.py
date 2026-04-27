#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX 增强版 - 支持进度回调、Token统计和多模型
"""

import os
import time
import asyncio
import re
from pathlib import Path
from typing import Optional, List, Callable
import PyPDF2
import pdfplumber
from dotenv import load_dotenv
from document_parser import PDFDocumentParser
from clients import (
    deepseek_chat, deepseek_reasoner, gpt4o, gpt4o_mini, gpt52_with_reasoning,
    glm46_thinking, glm47_thinking, gemini3_pro, doubao, deepseek_math,
    LLMClient
)
from config import settings
from latex_utils import sanitize_latex_body, wrap_with_template, split_references_section

load_dotenv()


class PDF2LaTeXEnhanced:
    """PDF到LaTeX转换器 - 增强版，支持多种LLM模型"""
    
    # 模型映射表
    MODEL_MAP = {
        'deepseek-chat': deepseek_chat,
        'deepseek-reasoner': deepseek_reasoner,
        'gpt4o': gpt4o,
        'gpt4o-mini': gpt4o_mini,
        'gpt52': gpt52_with_reasoning,
        'glm46': glm46_thinking,
        'glm47': glm47_thinking,
        'gemini3-pro': gemini3_pro,
        'doubao': doubao,
        'deepseek-math': deepseek_math
    }
    
    def __init__(self, model: str = "deepseek-chat", translation_prompt: str = ""):
        """
        初始化PDF2LaTeX转换器
        
        Args:
            model: 模型名称，可选值：
                - deepseek-chat: DeepSeek通用对话模型
                - deepseek-reasoner: DeepSeek推理模型
                - gpt4o: GPT-4o
                - gpt4o-mini: GPT-4o Mini
                - gpt52: GPT-5.2推理模型
                - glm46: 智谱GLM-4.6
                - glm47: 智谱GLM-4.7
                - gemini3-pro: Gemini 3 Pro
                - doubao: 豆包
                - deepseek-math: DeepSeek数学模型
        """
        if model not in self.MODEL_MAP:
            raise ValueError(f"不支持的模型: {model}。支持的模型: {list(self.MODEL_MAP.keys())}")
        
        self.model_name = model
        self.client = self.MODEL_MAP[model]
        self.translation_prompt = translation_prompt.strip()
        self.document_parser = PDFDocumentParser(
            quality_fn=self._check_text_quality,
            progress_callback=self._emit_progress,
        )
        
        # 进度回调
        self.progress_callback = None
        
        # Token统计
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def _emit_progress(self, status: str, current: int, total: int, message: str, log_type: str = 'info', log_message: Optional[str] = None):
        """发送进度更新"""
        if self.progress_callback:
            # 传递当前的 token 统计信息
            tokens = {
                'prompt_tokens': self.prompt_tokens,
                'completion_tokens': self.completion_tokens,
                'total_tokens': self.total_tokens
            }
            self.progress_callback(status, current, total, message, log_type, log_message, tokens)

    def _compose_translation_guidance(self) -> str:
        """拼接用户自定义翻译要求。"""
        if not self.translation_prompt:
            return ""
        return f"\n\n用户自定义翻译要求：\n{self.translation_prompt}\n\n优先级说明：在不违反公式、符号、变量名和参考文献原文保护规则的前提下，优先满足上述要求。"
    
    def _check_text_quality(self, text: str) -> float:
        """
        检查提取文本的质量
        返回质量分数 0-1，分数越高质量越好
        """
        if not text or len(text.strip()) < 10:
            return 0.0
        
        # 计算可读字符比例
        readable_chars = sum(1 for c in text if c.isalnum() or c.isspace() or c in '.,;:!?-()[]{}')
        total_chars = len(text)
        
        if total_chars == 0:
            return 0.0
        
        readable_ratio = readable_chars / total_chars
        
        # 检查是否有大量乱码字符
        weird_chars = sum(1 for c in text if ord(c) > 1000 and not ('\u4e00' <= c <= '\u9fff'))
        weird_ratio = weird_chars / total_chars
        
        # 质量分数：可读字符多、乱码字符少
        quality_score = readable_ratio - (weird_ratio * 2)
        
        return max(0.0, min(1.0, quality_score))

    def _clean_table_cell(self, cell: Optional[str]) -> str:
        """清洗表格单元格文本。"""
        if cell is None:
            return "<EMPTY>"
        cleaned = str(cell).replace("\n", " ").strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned if cleaned else "<EMPTY>"

    def _format_tables_for_prompt(self, tables: List[List[List[Optional[str]]]]) -> str:
        """将 PDF 抽取的表格转为结构化文本，供 LLM 还原 tabular。"""
        blocks: List[str] = []

        for t_idx, table in enumerate(tables, start=1):
            rows = table or []
            valid_rows = [row for row in rows if isinstance(row, list)]
            if not valid_rows:
                continue

            max_cols = max((len(row) for row in valid_rows), default=0)
            if max_cols == 0:
                continue

            lines = [f"[TABLE {t_idx}] cols={max_cols}"]
            for r_idx, row in enumerate(valid_rows, start=1):
                normalized = [self._clean_table_cell(cell) for cell in row]
                if len(normalized) < max_cols:
                    normalized.extend(["<EMPTY>"] * (max_cols - len(normalized)))
                lines.append(f"ROW {r_idx}: " + " | ".join(normalized[:max_cols]))

            blocks.append("\n".join(lines))

        return "\n\n".join(blocks).strip()

    def _attach_tables_context(self, page_text: str, page_tables_context: str) -> str:
        """将表格上下文拼接到页面文本末尾。"""
        text = (page_text or "").strip()
        if not page_tables_context:
            return text

        marker = "\n\n[STRUCTURED_TABLE_CONTEXT]\n"
        if text:
            return f"{text}{marker}{page_tables_context}"
        return f"[STRUCTURED_TABLE_CONTEXT]\n{page_tables_context}"

    def _is_pagination_line(self, line: str, page_num: int, total_pages: int) -> bool:
        """判断一行文本是否是页码/页眉页脚中的分页噪声。"""
        s = (line or "").strip()
        if not s:
            return False

        cur = page_num + 1
        # 仅由数字构成，如 "5"
        if re.fullmatch(r"\d{1,4}", s):
            value = int(s)
            if value == cur or (total_pages > 0 and value == total_pages):
                return True

        # 纯分数样式，如 "5/26"
        frac = re.fullmatch(r"(\d{1,4})\s*/\s*(\d{1,4})", s)
        if frac:
            left = int(frac.group(1))
            right = int(frac.group(2))
            if left == cur and (total_pages <= 0 or right == total_pages):
                return True

        # 中英分页写法，如 "Page 5 of 26"、"第5页"、"第 5/26 页"
        cn_page = re.fullmatch(
            r"第\s*\d{1,4}(?:\s*/\s*\d{1,4})?\s*页(?:\s*/\s*共?\s*\d{1,4}\s*页)?",
            s,
            flags=re.IGNORECASE,
        )
        if cn_page:
            return True

        en_page = re.fullmatch(
            r"(?:page|p\.)\s*\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?",
            s,
            flags=re.IGNORECASE,
        )
        if en_page:
            return True

        return False

    def _remove_pagination_artifacts(self, text: str, page_num: int, total_pages: int) -> str:
        """清理页首页尾的分页噪声，避免被翻译成正文。"""
        raw = (text or "")
        if not raw.strip():
            return ""

        lines = raw.splitlines()
        if not lines:
            return raw.strip()

        window = min(4, len(lines))
        keep = [True] * len(lines)

        for i in range(window):
            if self._is_pagination_line(lines[i], page_num, total_pages):
                keep[i] = False

        for i in range(len(lines) - window, len(lines)):
            if i >= 0 and self._is_pagination_line(lines[i], page_num, total_pages):
                keep[i] = False

        cleaned = "\n".join(lines[i] for i in range(len(lines)) if keep[i]).strip()
        return cleaned

    def extract_text_from_pdf(
        self,
        pdf_path: str,
        pages: Optional[List[int]] = None
    ) -> List[str]:
        """从 PDF 提取文本，统一委托给 document_parser。"""
        return self.document_parser.extract_text_from_pdf(pdf_path, pages)
    
    def translate_text(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """翻译文本"""
        display_page_num = page_num if display_page_num is None else display_page_num
        display_total_pages = total_pages if display_total_pages is None else display_total_pages
        main_text, refs_text = split_references_section(text)
        if not main_text.strip():
            # 整页为参考文献时保持原文，避免错误翻译作者名/刊名等。
            return text.strip()

        system_prompt = """你是一个专业的学术翻译助手。将英文学术文档翻译成中文。

    要求：
    1. 保持学术性和专业性
    2. 数学公式、符号、变量名保持原样
    3. 专业术语使用准确的中文翻译
    4. 保持原文段落结构
    5. 翻译流畅自然
    6. 参考文献（References/Bibliography/参考文献）条目不得翻译作者名、论文名、期刊名、会议名
    7. 只输出翻译后的文本"""
        system_prompt += self._compose_translation_guidance()

        user_prompt = f"""请将以下英文学术文本翻译成中文（第 {display_page_num + 1}/{display_total_pages} 页）：

        {main_text}

    请直接输出翻译后的中文文本。"""

        try:
            self._emit_progress(
                'translating',
                page_num,
                total_pages,
                f'正在翻译第 {display_page_num + 1}/{display_total_pages} 页...'
            )
            
            # 使用异步客户端
            response = asyncio.run(self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            ))
            
            # 统计Token
            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)
            
            # 提取内容
            content = LLMClient.extract_content(response).strip()
            if refs_text.strip():
                return f"{content}\n\n{refs_text.strip()}"
            return content
            
        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")

    async def translate_text_async(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """异步翻译文本"""
        display_page_num = page_num if display_page_num is None else display_page_num
        display_total_pages = total_pages if display_total_pages is None else display_total_pages
        main_text, refs_text = split_references_section(text)
        if not main_text.strip():
            return text.strip()

        system_prompt = """你是一个专业的学术翻译助手。将英文学术文档翻译成中文。

    要求：
    1. 保持学术性和专业性
    2. 数学公式、符号、变量名保持原样
    3. 专业术语使用准确的中文翻译
    4. 保持原文段落结构
    5. 翻译流畅自然
    6. 参考文献（References/Bibliography/参考文献）条目不得翻译作者名、论文名、期刊名、会议名
    7. 只输出翻译后的文本"""
        system_prompt += self._compose_translation_guidance()

        user_prompt = f"""请将以下英文学术文本翻译成中文（第 {display_page_num + 1}/{display_total_pages} 页）：

        {main_text}

    请直接输出翻译后的中文文本。"""

        try:
            self._emit_progress(
                'translating',
                page_num,
                total_pages,
                f'正在翻译第 {display_page_num + 1}/{display_total_pages} 页...'
            )

            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )

            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)

            content = LLMClient.extract_content(response).strip()
            if refs_text.strip():
                return f"{content}\n\n{refs_text.strip()}"
            return content

        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")
    
    async def _refine_latex_quality_async(self, latex_content: str, page_num: int, total_pages: int) -> str:
        """高质量模式：对 LaTeX 做一次低温语法润色。"""
        system_prompt = """你是LaTeX质量修复助手。只做最小必要修复，不改变原文语义。

要求：
1. 修复明显的 LaTeX 语法问题（环境不匹配、命令拼写、无效转义）
2. 保持数学表达不变
3. 不新增解释文字
4. 仅输出修复后的 LaTeX 正文"""

        user_prompt = f"""请修复以下 LaTeX 正文（第 {page_num + 1}/{total_pages} 页）：

{latex_content}
"""

        response = await self.client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )

        if 'usage' in response:
            usage = response['usage']
            self.prompt_tokens += usage.get('prompt_tokens', 0)
            self.completion_tokens += usage.get('completion_tokens', 0)
            self.total_tokens += usage.get('total_tokens', 0)

        return LLMClient.extract_content(response).strip()

    def convert_text_to_latex(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        translate: bool = False,
        quality_mode: str = 'standard',
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """转换文本为LaTeX"""
        display_page_num = page_num if display_page_num is None else display_page_num
        display_total_pages = total_pages if display_total_pages is None else display_total_pages
        # 检查文本质量
        quality = self._check_text_quality(text)
        print(f"[转换] 第 {display_page_num + 1}/{display_total_pages} 页文本质量: {quality:.2f}, 长度: {len(text)}")
        
        # 如果文本为空或质量太低，提示用户
        if not text.strip():
            print(f"[转换] 警告: 第 {page_num + 1} 页没有提取到文本，可能是扫描版PDF")
            return f"% 警告：第 {page_num + 1} 页无法提取文本\n% 这可能是扫描版PDF，建议使用OCR工具处理\n"
        
        if quality < 0.3:
            print(f"[转换] 警告: 第 {display_page_num + 1}/{display_total_pages} 页文本质量较低 ({quality:.2f})，可能包含乱码")
        
        if translate:
            text = self.translate_text(
                text,
                page_num,
                total_pages,
                display_page_num=display_page_num,
                display_total_pages=display_total_pages,
            )
        
        system_prompt = """你是一个专业的LaTeX转换助手。将文本转换为规范的LaTeX格式。

要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 对于中文内容，直接使用中文字符
4. **不要输出\\documentclass, \\begin{document}, \\end{document}等文档结构**
5. **不要输出\\usepackage等导言区命令**
    6. **不要输出\\begin{theorem}/\\begin{lemma}/\\begin{proof}等需额外宏包或定理环境的结构，改为普通段落或使用\\textbf{}做标题**
    7. 若输入中存在 [STRUCTURED_TABLE_CONTEXT] 或 [TABLE n] 片段，必须优先还原为完整表格环境（建议 tabular）
    8. 每个表格行列数必须一致；缺失单元格用 -- 占位，禁止省略列
    9. 暂不处理图片内容；遇到 Figure/Fig./图像描述可保留为普通文本，禁止臆造 figure 环境
    10. 参考文献部分（References/Bibliography/参考文献）必须保持原文语言，不得翻译作者名、标题、刊名
    11. 只输出正文内容的LaTeX代码"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {display_page_num + 1}/{display_total_pages} 页）：

{text}

    只输出LaTeX内容代码，不要包含文档结构或定理/引理/证明环境。

    特别要求：如果看到 [STRUCTURED_TABLE_CONTEXT]，请据此还原完整表格，确保每行列数一致。"""

        try:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在转换第 {display_page_num + 1}/{display_total_pages} 页为LaTeX...'
            )
            
            # 使用异步客户端
            response = asyncio.run(self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            ))
            
            # 统计Token
            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)
            
            # 提取内容
            content = LLMClient.extract_content(response)
            latex_content = content.strip()
            latex_content = self._clean_document_structure(latex_content)
            latex_content = sanitize_latex_body(latex_content)

            if quality_mode == 'high':
                latex_content = asyncio.run(self._refine_latex_quality_async(latex_content, page_num, total_pages))
                latex_content = self._clean_document_structure(latex_content)
                latex_content = sanitize_latex_body(latex_content)

            return latex_content
            
        except Exception as e:
            raise Exception(f"转换失败: {str(e)}")

    async def convert_text_to_latex_async(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        translate: bool = False,
        quality_mode: str = 'standard',
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """异步转换文本为LaTeX"""
        display_page_num = page_num if display_page_num is None else display_page_num
        display_total_pages = total_pages if display_total_pages is None else display_total_pages
        quality = self._check_text_quality(text)
        print(f"[转换] 第 {display_page_num + 1}/{display_total_pages} 页文本质量: {quality:.2f}, 长度: {len(text)}")

        if not text.strip():
            print(f"[转换] 警告: 第 {page_num + 1} 页没有提取到文本，可能是扫描版PDF")
            return f"% 警告：第 {page_num + 1} 页无法提取文本\n% 这可能是扫描版PDF，建议使用OCR工具处理\n"

        if quality < 0.3:
            print(f"[转换] 警告: 第 {display_page_num + 1}/{display_total_pages} 页文本质量较低 ({quality:.2f})，可能包含乱码")

        if translate:
            text = await self.translate_text_async(
                text,
                page_num,
                total_pages,
                display_page_num=display_page_num,
                display_total_pages=display_total_pages,
            )

        system_prompt = """你是一个专业的LaTeX转换助手。将文本转换为规范的LaTeX格式。

要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 对于中文内容，直接使用中文字符
4. **不要输出\\documentclass, \\begin{document}, \\end{document}等文档结构**
5. **不要输出\\usepackage等导言区命令**
6. **不要输出\\begin{theorem}/\\begin{lemma}/\\begin{proof}等需额外宏包或定理环境的结构，改为普通段落或使用\\textbf{}做标题**
7. 若输入中存在 [STRUCTURED_TABLE_CONTEXT] 或 [TABLE n] 片段，必须优先还原为完整表格环境（建议 tabular）
8. 每个表格行列数必须一致；缺失单元格用 -- 占位，禁止省略列
9. 暂不处理图片内容；遇到 Figure/Fig./图像描述可保留为普通文本，禁止臆造 figure 环境
10. 参考文献部分（References/Bibliography/参考文献）必须保持原文语言，不得翻译作者名、标题、刊名
11. 只输出正文内容的LaTeX代码"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {display_page_num + 1}/{display_total_pages} 页）：

{text}

只输出LaTeX内容代码，不要包含文档结构或定理/引理/证明环境。

特别要求：如果看到 [STRUCTURED_TABLE_CONTEXT]，请据此还原完整表格，确保每行列数一致。"""

        try:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在转换第 {display_page_num + 1}/{display_total_pages} 页为LaTeX...'
            )

            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )

            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)

            content = LLMClient.extract_content(response)
            latex_content = content.strip()
            latex_content = self._clean_document_structure(latex_content)
            latex_content = sanitize_latex_body(latex_content)

            if quality_mode == 'high':
                latex_content = await self._refine_latex_quality_async(latex_content, page_num, total_pages)
                latex_content = self._clean_document_structure(latex_content)
                latex_content = sanitize_latex_body(latex_content)

            return latex_content

        except Exception as e:
            raise Exception(f"转换失败: {str(e)}")
    
    def _clean_document_structure(self, latex_content: str) -> str:
        """清理文档结构命令"""
        import re
        
        latex_content = re.sub(r'\\documentclass(\[.*?\])?\{.*?\}', '', latex_content)
        latex_content = re.sub(r'\\usepackage(\[.*?\])?\{.*?\}', '', latex_content)
        latex_content = re.sub(r'\\begin\{document\}', '', latex_content)
        latex_content = re.sub(r'\\end\{document\}', '', latex_content)
        latex_content = re.sub(r'\\title\{.*?\}', '', latex_content)
        latex_content = re.sub(r'\\author\{.*?\}', '', latex_content)
        latex_content = re.sub(r'\\date\{.*?\}', '', latex_content)
        latex_content = re.sub(r'\\maketitle', '', latex_content)
        latex_content = re.sub(r'\n{3,}', '\n\n', latex_content)
        
        return latex_content.strip()
    
    def convert_pdf(
        self,
        pdf_path: str,
        output_path: Optional[str] = None,
        pages: Optional[List[int]] = None,
        add_document_wrapper: bool = True,
        translate: bool = False,
        task_id: Optional[str] = None,
        template_name: str = 'article',
        quality_mode: str = 'standard'
    ) -> dict:
        """转换PDF到LaTeX"""
        print(f"\n[转换开始] PDF路径={pdf_path}, 页码={pages}, 翻译={translate}")
        start_time = time.time()
        
        # 重置统计
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        if output_path is None:
            pdf_file = Path(pdf_path)
            suffix = "_cn" if translate else ""
            output_path = str(pdf_file.parent / f"{pdf_file.stem}{suffix}.tex")
        else:
            output_path = str(output_path)
        
        # 先获取PDF总页数
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
        except:
            # 如果PyPDF2失败，用pdfplumber
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
        
        # 确定要提取的页码
        if pages is None:
            pages = list(range(total_pages))
        else:
            pages = [p for p in pages if 0 <= p < total_pages]
        
        print(f"[转换] 准备提取 {len(pages)}/{total_pages} 页: {pages}")
        
        # 只提取需要的页面
        pages_text = self.extract_text_from_pdf(pdf_path, pages)
        
        # 构建LaTeX正文
        latex_content = []
        failed_pages = []
        
        mode_desc = "翻译并转换" if translate else "转换"
        processed_pages = 0
        total_to_process = len(pages)
        
        async def process_page(idx: int, page_num: int):
            text = pages_text[page_num]
            if not text.strip():
                return page_num, None, False

            status = 'translating' if translate else 'converting'
            self._emit_progress(
                status,
                idx,
                total_to_process,
                f'正在{mode_desc}第 {idx + 1}/{total_to_process} 页...',
                'progress',
                f'⚙️ 开始{mode_desc}第 {idx + 1}/{total_to_process} 页 (原始页码: {page_num + 1})'
            )

            try:
                latex_page = await self.convert_text_to_latex_async(
                    text,
                    page_num,
                    len(pages_text),
                    translate=translate,
                    quality_mode=quality_mode,
                    display_page_num=idx,
                    display_total_pages=total_to_process,
                )

                self._emit_progress(
                    status,
                    idx + 1,
                    total_to_process,
                    f'已完成 {idx + 1}/{total_to_process} 页',
                    'success',
                    f'✓ 第 {idx + 1}/{total_to_process} 页{mode_desc}完成'
                )
                return page_num, latex_page, True
            except Exception as e:
                err_text = str(e)
                print(f"警告: 第 {page_num + 1} 页{mode_desc}失败: {err_text}")
                failed_pages.append((page_num + 1, err_text))
                return page_num, None, False

        async def process_all_pages():
            # 控制并发，避免同时发起过多LLM请求导致连接失败。
            max_concurrency = 2
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _run_with_limit(idx: int, page_num: int):
                async with semaphore:
                    return await process_page(idx, page_num)

            tasks = [_run_with_limit(idx, page_num) for idx, page_num in enumerate(pages)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(process_all_pages())

        for page_num, latex_page, ok in results:
            if not ok:
                latex_content.append(f"% 第 {page_num + 1} 页{mode_desc}失败")
                latex_content.append("")
                continue
            if latex_page is None:
                continue
            latex_content.append(f"% ===== 第 {page_num + 1} 页 =====")
            latex_content.append(latex_page)

            latex_content.append("")
            processed_pages += 1
        
        source_text = "\n\n".join([pages_text[p] for p in pages if pages_text[p].strip()]).strip()
        final_content = "\n".join(latex_content)

        if total_to_process > 0 and processed_pages == 0:
            # 全部页面失败时直接抛错，避免返回“成功但0页”。
            if failed_pages:
                sample_errors = "; ".join(
                    [f"第{page_no}页: {msg}" for page_no, msg in failed_pages[:3]]
                )
                raise Exception(f"所有页面{mode_desc}失败。示例错误: {sample_errors}")
            raise Exception(f"所有页面{mode_desc}失败")

        if add_document_wrapper:
            final_content = wrap_with_template(
                final_content,
                template_name=template_name,
                use_chinese=translate
            )
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
        
        processing_time = time.time() - start_time
        
        # 发送完成进度
        self._emit_progress(
            'completed',
            len(pages),
            len(pages),
            f'转换完成！处理了 {processed_pages} 页',
            'success',
            f'✅ 转换完成！成功处理 {processed_pages} 页'
        )
        
        # 返回详细结果
        return {
            'output_path': str(output_path),
            'total_pages': len(pages_text),
            'processed_pages': processed_pages,
            'failed_pages': [
                {'page': page_no, 'error': err}
                for page_no, err in failed_pages
            ],
            'total_tokens': self.total_tokens,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'processing_time': round(processing_time, 2),
            'source_text': source_text
        }
