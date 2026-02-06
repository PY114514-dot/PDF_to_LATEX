#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF2LaTeX 增强版 - 支持进度回调、Token统计和多模型
"""

import os
import time
import asyncio
from pathlib import Path
from typing import Optional, List, Callable
import PyPDF2
import pdfplumber
from dotenv import load_dotenv
from clients import (
    deepseek_chat, deepseek_reasoner, gpt4o, gpt4o_mini, gpt52_with_reasoning,
    glm46_thinking, glm47_thinking, gemini3_pro, doubao, deepseek_math,
    LLMClient
)
from config import settings

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
    
    # 模型价格配置 (per 1M tokens)
    MODEL_PRICING = {
        'deepseek-chat': {'input': 1.0, 'output': 2.0},
        'deepseek-reasoner': {'input': 1.0, 'output': 2.0},
        'gpt4o': {'input': 2.5, 'output': 10.0},
        'gpt4o-mini': {'input': 0.15, 'output': 0.6},
        'gpt52': {'input': 5.0, 'output': 15.0},
        'glm46': {'input': 1.0, 'output': 1.0},
        'glm47': {'input': 1.0, 'output': 1.0},
        'gemini3-pro': {'input': 1.25, 'output': 5.0},
        'doubao': {'input': 0.8, 'output': 2.0},
        'deepseek-math': {'input': 1.0, 'output': 2.0}
    }
    
    def __init__(self, model: str = "deepseek-chat"):
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
        
        # 进度回调
        self.progress_callback = None
        
        # Token统计
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        
        # 获取价格配置
        pricing = self.MODEL_PRICING.get(model, {'input': 1.0, 'output': 2.0})
        self.price_per_million_input = pricing['input']
        self.price_per_million_output = pricing['output']
    
    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def _emit_progress(self, status: str, current: int, total: int, message: str, log_type: str = 'info', log_message: str = None):
        """发送进度更新"""
        if self.progress_callback:
            # 传递当前的 token 统计信息
            tokens = {
                'prompt_tokens': self.prompt_tokens,
                'completion_tokens': self.completion_tokens,
                'total_tokens': self.total_tokens,
                'estimated_cost': self._calculate_cost()
            }
            self.progress_callback(status, current, total, message, log_type, log_message, tokens)
    
    def _calculate_cost(self):
        """计算估算成本（美元）"""
        input_cost = (self.prompt_tokens / 1_000_000) * self.price_per_million_input
        output_cost = (self.completion_tokens / 1_000_000) * self.price_per_million_output
        return input_cost + output_cost
    
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
    
    def extract_text_from_pdf(self, pdf_path: str, pages: Optional[List[int]] = None) -> List[str]:
        """
        从PDF提取文本，使用多种方法以获得最佳效果
        优先级：pdfplumber > PyPDF2
        
        Args:
            pdf_path: PDF文件路径
            pages: 要提取的页码列表（0-based），None表示提取所有页
        
        Returns:
            提取的文本列表，索引对应页码
        """
        pages_text = []
        
        try:
            # 首先尝试使用 pdfplumber（效果更好）
            print(f"\n[PDF提取] 开始提取文件: {pdf_path}")
            print("[PDF提取] 方法: pdfplumber (优先)")
            
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                
                # 确定要提取的页码
                if pages is None:
                    pages_to_extract = list(range(total_pages))
                else:
                    pages_to_extract = [p for p in pages if 0 <= p < total_pages]
                
                # 初始化所有页面为空字符串
                pages_text = [''] * total_pages
                
                self._emit_progress('extracting', 0, len(pages_to_extract), '正在使用增强方法提取PDF文本...', 'info', '📄 开始提取PDF文本 (需要提取 {}/{} 页)'.format(len(pages_to_extract), total_pages))
                
                for idx, page_num in enumerate(pages_to_extract):
                    page = pdf.pages[page_num]
                    text = page.extract_text()
                    
                    if text:
                        text = text.strip()
                    else:
                        text = ""
                    
                    # 检查文本质量
                    quality = self._check_text_quality(text)
                    print(f"[PDF提取] 第 {page_num + 1}/{total_pages} 页 - 长度: {len(text)}, 质量: {quality:.2f}")
                    
                    # 发送质量日志
                    self._emit_progress(
                        'extracting',
                        idx,
                        len(pages_to_extract),
                        f'提取第 {idx + 1}/{len(pages_to_extract)} 页',
                        'quality',
                        f'第 {page_num + 1} 页: 文本长度 {len(text)}, 质量 {quality:.0%}'
                    )
                    
                    # 如果质量太低，尝试使用 PyPDF2 备用方法
                    if quality < 0.5 and len(text) < 50:
                        print(f"[PDF提取] 第 {page_num + 1} 页质量低，尝试备用方法...")
                        try:
                            with open(pdf_path, 'rb') as file:
                                pdf_reader = PyPDF2.PdfReader(file)
                                if page_num < len(pdf_reader.pages):
                                    backup_text = pdf_reader.pages[page_num].extract_text()
                                    backup_quality = self._check_text_quality(backup_text)
                                    
                                    if backup_quality > quality:
                                        text = backup_text
                                        print(f"[PDF提取] 备用方法更好，质量: {backup_quality:.2f}")
                        except Exception as e:
                            print(f"[PDF提取] 备用方法失败: {str(e)}")
                    
                    pages_text[page_num] = text
                    
                    self._emit_progress(
                        'extracting',
                        idx + 1,
                        len(pages_to_extract),
                        f'已提取 {idx + 1}/{len(pages_to_extract)} 页 (质量: {quality:.0%})',
                        'success',
                        f'✓ 第 {page_num + 1} 页提取完成 (质量: {quality:.0%})'
                    )
                
                print(f"[PDF提取] 完成！共提取 {len(pages_to_extract)}/{total_pages} 页")
                    
        except Exception as e:
            # 如果 pdfplumber 失败，降级到 PyPDF2
            print(f"[PDF提取] pdfplumber 失败: {str(e)}")
            print("[PDF提取] 降级到 PyPDF2...")
            
            try:
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    total_pages = len(pdf_reader.pages)
                    
                    # 确定要提取的页码
                    if pages is None:
                        pages_to_extract = list(range(total_pages))
                    else:
                        pages_to_extract = [p for p in pages if 0 <= p < total_pages]
                    
                    # 初始化所有页面为空字符串
                    pages_text = [''] * total_pages
                    
                    self._emit_progress('extracting', 0, len(pages_to_extract), '正在使用基础方法提取PDF文本...', 'info', '📄 使用基础方法提取PDF文本 (需要提取 {}/{} 页)'.format(len(pages_to_extract), total_pages))
                    
                    for idx, page_num in enumerate(pages_to_extract):
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()
                        pages_text[page_num] = text
                        
                        quality = self._check_text_quality(text)
                        print(f"[PDF提取] 第 {page_num + 1}/{total_pages} 页 - 长度: {len(text)}, 质量: {quality:.2f}")
                        
                        self._emit_progress(
                            'extracting',
                            idx + 1,
                            len(pages_to_extract),
                            f'已提取 {idx + 1}/{len(pages_to_extract)} 页',
                            'success',
                            f'✓ 第 {page_num + 1} 页提取完成 (质量: {quality:.0%})'
                        )
                        
            except Exception as e2:
                raise Exception(f"所有PDF提取方法均失败: PyPDF2={str(e2)}, pdfplumber={str(e)}")
        
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
            return content.strip()
            
        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")

    async def translate_text_async(self, text: str, page_num: int, total_pages: int) -> str:
        """异步翻译文本"""
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
            return content.strip()

        except Exception as e:
            raise Exception(f"翻译失败: {str(e)}")
    
    def convert_text_to_latex(self, text: str, page_num: int, total_pages: int, translate: bool = False) -> str:
        """转换文本为LaTeX"""
        # 检查文本质量
        quality = self._check_text_quality(text)
        print(f"[转换] 第 {page_num + 1} 页文本质量: {quality:.2f}, 长度: {len(text)}")
        
        # 如果文本为空或质量太低，提示用户
        if not text.strip():
            print(f"[转换] 警告: 第 {page_num + 1} 页没有提取到文本，可能是扫描版PDF")
            return f"% 警告：第 {page_num + 1} 页无法提取文本\n% 这可能是扫描版PDF，建议使用OCR工具处理\n"
        
        if quality < 0.3:
            print(f"[转换] 警告: 第 {page_num + 1} 页文本质量较低 ({quality:.2f})，可能包含乱码")
        
        if translate:
            text = self.translate_text(text, page_num, total_pages)
        
        system_prompt = """你是一个专业的LaTeX转换助手。将文本转换为规范的LaTeX格式。

要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 对于中文内容，直接使用中文字符
4. **不要输出\\documentclass, \\begin{document}, \\end{document}等文档结构**
5. **不要输出\\usepackage等导言区命令**
    6. **不要输出\\begin{theorem}/\\begin{lemma}/\\begin{proof}等需额外宏包或定理环境的结构，改为普通段落或使用\\textbf{}做标题**
    7. 只输出正文内容的LaTeX代码"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {page_num + 1}/{total_pages} 页）：

{text}

    只输出LaTeX内容代码，不要包含文档结构或定理/引理/证明环境。"""

        try:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在转换第 {page_num + 1}/{total_pages} 页为LaTeX...'
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
            return self._clean_document_structure(latex_content)
            
        except Exception as e:
            raise Exception(f"转换失败: {str(e)}")

    async def convert_text_to_latex_async(self, text: str, page_num: int, total_pages: int, translate: bool = False) -> str:
        """异步转换文本为LaTeX"""
        quality = self._check_text_quality(text)
        print(f"[转换] 第 {page_num + 1} 页文本质量: {quality:.2f}, 长度: {len(text)}")

        if not text.strip():
            print(f"[转换] 警告: 第 {page_num + 1} 页没有提取到文本，可能是扫描版PDF")
            return f"% 警告：第 {page_num + 1} 页无法提取文本\n% 这可能是扫描版PDF，建议使用OCR工具处理\n"

        if quality < 0.3:
            print(f"[转换] 警告: 第 {page_num + 1} 页文本质量较低 ({quality:.2f})，可能包含乱码")

        if translate:
            text = await self.translate_text_async(text, page_num, total_pages)

        system_prompt = """你是一个专业的LaTeX转换助手。将文本转换为规范的LaTeX格式。

要求：
1. 识别数学公式，使用LaTeX数学环境
2. 识别文本结构，使用对应的LaTeX命令
3. 对于中文内容，直接使用中文字符
4. **不要输出\\documentclass, \\begin{document}, \\end{document}等文档结构**
5. **不要输出\\usepackage等导言区命令**
6. **不要输出\\begin{theorem}/\\begin{lemma}/\\begin{proof}等需额外宏包或定理环境的结构，改为普通段落或使用\\textbf{}做标题**
7. 只输出正文内容的LaTeX代码"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {page_num + 1}/{total_pages} 页）：

{text}

只输出LaTeX内容代码，不要包含文档结构或定理/引理/证明环境。"""

        try:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在转换第 {page_num + 1}/{total_pages} 页为LaTeX...'
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
            output_path = pdf_file.parent / f"{pdf_file.stem}{suffix}.tex"
        
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
                    translate=translate
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
                print(f"警告: 第 {page_num + 1} 页{mode_desc}失败: {str(e)}")
                return page_num, None, False

        async def process_all_pages():
            tasks = [process_page(idx, page_num) for idx, page_num in enumerate(pages)]
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
            f'转换完成！处理了 {processed_pages} 页',
            'success',
            f'✅ 转换完成！成功处理 {processed_pages} 页'
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
