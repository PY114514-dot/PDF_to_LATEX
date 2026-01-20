#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX 增强版 - 支持进度回调和Token统计
"""

import os
import time
from pathlib import Path
from typing import Optional, List, Callable
import PyPDF2
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


class PDF2LaTeXEnhanced:
    """PDF到LaTeX转换器 - 增强版"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat"):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")
        
        self.model = model
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        
        # 进度回调
        self.progress_callback = None
        
        # Token统计
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        
        # DeepSeek 价格 (per 1M tokens)
        self.price_per_million_input = 1.0  # $1 per 1M input tokens
        self.price_per_million_output = 2.0  # $2 per 1M output tokens
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def _emit_progress(self, status: str, current: int, total: int, message: str):
        """发送进度更新"""
        if self.progress_callback:
            self.progress_callback(status, current, total, message)
    
    def _calculate_cost(self):
        """计算估算成本（美元）"""
        input_cost = (self.prompt_tokens / 1_000_000) * self.price_per_million_input
        output_cost = (self.completion_tokens / 1_000_000) * self.price_per_million_output
        return input_cost + output_cost
    
    def extract_text_from_pdf(self, pdf_path: str) -> List[str]:
        """从PDF提取文本"""
        pages_text = []
        
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                self._emit_progress('extracting', 0, total_pages, '正在提取PDF文本...')
                
                for page_num in range(total_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    pages_text.append(text)
                    
                    self._emit_progress(
                        'extracting',
                        page_num + 1,
                        total_pages,
                        f'已提取 {page_num + 1}/{total_pages} 页'
                    )
                    
        except Exception as e:
            raise Exception(f"提取PDF文本失败: {str(e)}")
        
        return pages_text
    
    def translate_text(self, text: str, page_num: int, total_pages: int) -> str:
        """翻译文本"""
        system_prompt = """你是一个专业的学术翻译助手。将英文学术文档翻译成中文。

要求：
1. 保持学术性和专业性
2. 数学公式、符号、变量名保持原样
3. 专业术语使用准确的中文翻译
4. 保持原文段落结构
5. 翻译流畅自然
6. 只输出翻译后的文本"""

        user_prompt = f"""请将以下英文学术文本翻译成中文（第 {page_num + 1}/{total_pages} 页）：

{text}

请直接输出翻译后的中文文本。"""

        try:
            self._emit_progress(
                'translating',
                page_num,
                total_pages,
                f'正在翻译第 {page_num + 1}/{total_pages} 页...'
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            # 统计Token
            if hasattr(response, 'usage'):
                self.prompt_tokens += response.usage.prompt_tokens
                self.completion_tokens += response.usage.completion_tokens
                self.total_tokens += response.usage.total_tokens
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")
    
    def convert_text_to_latex(self, text: str, page_num: int, total_pages: int, translate: bool = False) -> str:
        """转换文本为LaTeX"""
        if translate:
            text = self.translate_text(text, page_num, total_pages)
        
        system_prompt = """你是一个专业的LaTeX转换助手。将文本转换为规范的LaTeX格式。

要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 对于中文内容，直接使用中文字符
4. **不要输出\\documentclass, \\begin{document}, \\end{document}等文档结构**
5. **不要输出\\usepackage等导言区命令**
6. 只输出正文内容的LaTeX代码"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {page_num + 1}/{total_pages} 页）：

{text}

只输出LaTeX内容代码，不要包含文档结构。"""

        try:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在转换第 {page_num + 1}/{total_pages} 页为LaTeX...'
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            
            # 统计Token
            if hasattr(response, 'usage'):
                self.prompt_tokens += response.usage.prompt_tokens
                self.completion_tokens += response.usage.completion_tokens
                self.total_tokens += response.usage.total_tokens
            
            latex_content = response.choices[0].message.content.strip()
            return self._clean_document_structure(latex_content)
            
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
        task_id: Optional[str] = None
    ) -> dict:
        """转换PDF到LaTeX"""
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
            output_path = pdf_file.parent / f"{pdf_file.stem}{suffix}.tex"
        
        # 提取PDF文本
        pages_text = self.extract_text_from_pdf(pdf_path)
        
        if pages is None:
            pages = list(range(len(pages_text)))
        else:
            pages = [p for p in pages if 0 <= p < len(pages_text)]
        
        # 构建LaTeX文档
        latex_content = []
        
        if add_document_wrapper:
            latex_content.append(r"\documentclass{article}")
            latex_content.append(r"\usepackage{amsmath,amssymb,amsthm}")
            latex_content.append(r"\usepackage{graphicx}")
            latex_content.append(r"\usepackage[utf8]{inputenc}")
            latex_content.append(r"\usepackage{hyperref}")
            
            if translate:
                latex_content.append(r"\usepackage{xeCJK}")
            
            latex_content.append(r"")
            latex_content.append(r"\begin{document}")
            latex_content.append(r"")
        
        mode_desc = "翻译并转换" if translate else "转换"
        processed_pages = 0
        
        for idx, page_num in enumerate(pages):
            text = pages_text[page_num]
            
            if not text.strip():
                continue
            
            try:
                latex_page = self.convert_text_to_latex(text, page_num, len(pages_text), translate=translate)
                latex_content.append(f"% ===== 第 {page_num + 1} 页 =====")
                latex_content.append(latex_page)
                latex_content.append("")
                processed_pages += 1
                
            except Exception as e:
                print(f"警告: 第 {page_num + 1} 页{mode_desc}失败: {str(e)}")
                latex_content.append(f"% 第 {page_num + 1} 页{mode_desc}失败")
                latex_content.append("")
        
        if add_document_wrapper:
            latex_content.append(r"\end{document}")
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(latex_content))
        
        processing_time = time.time() - start_time
        
        # 发送完成进度
        self._emit_progress(
            'completed',
            len(pages),
            len(pages),
            f'转换完成！处理了 {processed_pages} 页'
        )
        
        # 返回详细结果
        return {
            'output_path': str(output_path),
            'total_pages': len(pages_text),
            'processed_pages': processed_pages,
            'total_tokens': self.total_tokens,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'estimated_cost': self._calculate_cost(),
            'processing_time': round(processing_time, 2)
        }
