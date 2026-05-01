#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Word (.docx) to LaTeX converter
Uses python-docx for structure extraction, LLM for complex elements
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph

from clients import LLMClient
from config import settings
from latex_utils import sanitize_latex_body, wrap_with_template


class Docx2LaTeXConverter:
    """Word (.docx) to LaTeX converter with hybrid strategy"""

    def __init__(
        self,
        model_name: str = "deepseek-math",
        translate: bool = False,
        translation_prompt: str = "",
        progress_callback: Optional[callable] = None
    ):
        self.model_name = model_name
        self.translate = translate
        self.translation_prompt = translation_prompt.strip()
        self.progress_callback = progress_callback
        self.llm_client = self._init_llm_client()

    def _init_llm_client(self) -> LLMClient:
        """Initialize LLM client for complex element optimization."""
        model_configs = {
            'deepseek-math': {
                'api_key': settings.CANOPY_WAVE_API_KEY,
                'base_url': 'https://api.canopywave.io/v1/chat/completions',
                'model': 'deepseek-ai/DeepSeek-Math-V2'
            }
        }
        config = model_configs.get(self.model_name, model_configs['deepseek-math'])
        return LLMClient(
            api_key=config['api_key'],
            base_url=config['base_url'],
            model=config['model'],
            timeout=settings.DEFAULT_TIMEOUT
        )

    def _emit_progress(self, status: str, current: int, total: int, message: str):
        """Emit progress update if callback is set."""
        if self.progress_callback:
            self.progress_callback(status, current, total, message)

    def extract_content(self, docx_path: str) -> Dict[str, Any]:
        """Extract structured content from .docx file."""
        doc = Document(docx_path)

        content = {
            'paragraphs': [],
            'headings': [],
            'tables': [],
            'lists': [],
            'equations': []
        }

        for element in doc.element.body:
            if isinstance(element, CT_P):
                para = Paragraph(element, doc)
                text = para.text.strip()
                if not text:
                    continue

                style_name = para.style.name if para.style else ''
                if style_name.startswith('Heading'):
                    try:
                        level = int(style_name.replace('Heading ', ''))
                    except ValueError:
                        level = 1
                    content['headings'].append({
                        'text': text,
                        'level': level
                    })
                else:
                    content['paragraphs'].append(text)

            elif isinstance(element, CT_Tbl):
                table = DocxTable(element, doc)
                table_data = []
                for row in table.rows:
                    row_data = [cell.text.strip() for cell in row.cells]
                    table_data.append(row_data)
                if table_data:
                    content['tables'].append(table_data)

        return content

    def convert_structure(self, content: Dict[str, Any]) -> str:
        """Convert extracted structure to basic LaTeX."""
        latex_parts = []

        for heading in content.get('headings', []):
            level = heading['level']
            text = heading['text']
            if level == 1:
                latex_parts.append(f'\\section{{{text}}}')
            elif level == 2:
                latex_parts.append(f'\\subsection{{{text}}}')
            elif level == 3:
                latex_parts.append(f'\\subsubsection{{{text}}}')
            else:
                latex_parts.append(f'\\paragraph{{{text}}}')

        for para in content.get('paragraphs', []):
            if para:
                latex_parts.append(para)

        for i, table in enumerate(content.get('tables', [])):
            latex_parts.append(f'% [TABLE_PLACEHOLDER_{i}]')
            latex_parts.append(self._convert_table_basic(table))

        return '\n\n'.join(latex_parts)

    def _convert_table_basic(self, table_data: List[List[str]]) -> str:
        """Basic table to LaTeX conversion."""
        if not table_data:
            return ''

        rows = len(table_data)
        cols = len(table_data[0]) if table_data else 0

        col_sep = "".join(["c|" for _ in range(cols)])
        lines = ['\\begin{table}[htbp]', '\\centering', '\\begin{tabular}{|' + col_sep + '}']
        lines.append('\\hline')

        for row_data in table_data:
            lines.append(' & '.join(row_data) + ' \\\\')
            lines.append('\\hline')

        lines.append('\\end{tabular}')
        lines.append('\\end{table}')

        return '\n'.join(lines)

    def _convert_list_basic(self, items: List[str], ordered: bool = False) -> str:
        """Basic list to LaTeX conversion."""
        env = 'enumerate' if ordered else 'itemize'
        lines = [f'\\begin{{{env}}}']
        for item in items:
            lines.append(f'\\item {item}')
        lines.append(f'\\end{{{env}}}')
        return '\n'.join(lines)

    async def process_complex_elements(
        self,
        basic_latex: str,
        tables: List[List[List[str]]]
    ) -> str:
        """Send complex elements to LLM for quality improvement."""
        if not tables:
            return basic_latex

        table_contexts = []
        for i, table in enumerate(tables):
            rows = table or []
            max_cols = max((len(row) for row in rows), default=0) if rows else 0
            lines = [f'[TABLE {i+1}] cols={max_cols}']
            for r_idx, row in enumerate(rows, start=1):
                normalized = [str(cell).replace('\n', ' ').strip() if cell else '<EMPTY>' for cell in row]
                if len(normalized) < max_cols:
                    normalized.extend(['<EMPTY>'] * (max_cols - len(normalized)))
                lines.append(f'ROW {r_idx}: ' + ' | '.join(normalized[:max_cols]))
            table_contexts.append('\n'.join(lines))

        table_prompt = '\n\n'.join(table_contexts)

        system_prompt = """你是一个LaTeX表格转换专家。
任务：将用户提供的表格数据转换为高质量的LaTeX表格格式。

要求：
1. 使用标准的LaTeX表格环境（table + tabular）
2. 保持行列对齐
3. 如果有合并单元格，需要使用 \\multicolumn 或 \\multirow
4. 不要翻译内容，保持原样
5. 只输出LaTeX代码，不要解释"""

        try:
            response = await self.llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请转换以下表格为LaTeX格式：\n\n{table_prompt}"}
                ],
                temperature=0.1,
                max_tokens=4000
            )

            optimized = LLMClient.extract_content(response).strip()

            result = basic_latex
            for i in range(len(tables)):
                placeholder = f'% [TABLE_PLACEHOLDER_{i}]'
                if placeholder in result:
                    result = result.replace(placeholder, '')

            return result

        except Exception as e:
            print(f"LLM optimization failed: {e}")
            return basic_latex

    async def convert_async(
        self,
        docx_path: str,
        output_path: Optional[str] = None,
        add_document_wrapper: bool = True,
        template_name: str = 'article'
    ) -> Dict[str, Any]:
        """Async conversion of .docx to LaTeX."""
        import asyncio
        import time

        start_time = time.time()
        self._emit_progress('extracting', 0, 3, '正在提取Word文档内容...')

        content = self.extract_content(docx_path)

        self._emit_progress('converting', 1, 3, '正在转换为LaTeX结构...')

        basic_latex = self.convert_structure(content)

        self._emit_progress('optimizing', 2, 3, '正在优化复杂元素...')

        final_latex = await self.process_complex_elements(
            basic_latex,
            content.get('tables', [])
        )

        final_latex = sanitize_latex_body(final_latex)

        if add_document_wrapper:
            final_latex = wrap_with_template(
                final_latex,
                template_name=template_name,
                use_chinese=self.translate
            )

        if output_path is None:
            output_path = str(Path(docx_path).with_suffix('.tex'))
        else:
            output_path = str(Path(output_path))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(final_latex, encoding='utf-8')

        elapsed_time = time.time() - start_time

        self._emit_progress('completed', 3, 3, f'转换完成！耗时 {elapsed_time:.1f}秒')

        return {
            'success': True,
            'output_path': output_path,
            'elapsed_time': elapsed_time,
            'messages': [
                f'提取了 {len(content.get("paragraphs", []))} 个段落',
                f'提取了 {len(content.get("headings", []))} 个标题',
                f'提取了 {len(content.get("tables", []))} 个表格'
            ]
        }

    def convert(
        self,
        docx_path: str,
        output_path: Optional[str] = None,
        add_document_wrapper: bool = True,
        template_name: str = 'article'
    ) -> Dict[str, Any]:
        """Synchronous conversion."""
        import asyncio
        return asyncio.run(self.convert_async(
            docx_path, output_path, add_document_wrapper, template_name
        ))