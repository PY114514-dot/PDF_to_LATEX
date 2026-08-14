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
from typing import Optional, List, Callable, Tuple
import PyPDF2
import pdfplumber
from dotenv import load_dotenv
from document_parser import PDFDocumentParser
from clients import (
    deepseek_v4_flash,
    deepseek_v4_pro,
    LLMClient,
    InsufficientBalanceError,
)
from config import settings
from costs import calculate_llm_cost
from latex_utils import (
    sanitize_latex_body, split_references_section, validate_latex_page,
    wrap_with_template, stitch_cross_page_formula_fragments,
)
from logger import get_module_logger

load_dotenv()

# 获取模块 logger
logger = get_module_logger(__name__)


class PDF2LaTeXEnhanced:
    """PDF到LaTeX转换器 - 增强版，支持多种LLM模型"""
    MAX_CHARS_PER_BATCH = 80000
    
    # 模型映射表
    MODEL_MAP = {
        'deepseek_v4_flash': deepseek_v4_flash,
        'deepseek_v4_pro': deepseek_v4_pro,
    }
    
    def __init__(
        self, model: str = "deepseek_v4_flash", translation_prompt: str = "",
        api_key: str = "", reasoning_effort: str = "",
    ):
        """
        初始化PDF2LaTeX转换器
        
        Args:
            model: 模型名称，可选值：
                - deepseek_v4_flash: DeepSeek V4 Flash 最新模型
                - deepseek_v4_pro: DeepSeek V4 Pro，高质量模式推荐
        """
        if model not in self.MODEL_MAP:
            raise ValueError(f"不支持的模型: {model}。支持的模型: {list(self.MODEL_MAP.keys())}")
        
        self.model_name = model
        configured_client = self.MODEL_MAP[model]
        # 用户提供的密钥只用于本次转换。不要写入任务历史、日志或磁盘。
        if api_key.strip() or reasoning_effort.strip():
            extra_params = dict(configured_client.default_extra_params)
            if reasoning_effort.strip():
                extra_params['reasoning_effort'] = reasoning_effort.strip()
            self.client = LLMClient(
                api_key=api_key.strip() or configured_client.api_key,
                base_url=configured_client.base_url,
                model=configured_client.model,
                timeout=configured_client.timeout,
                default_extra_params=extra_params,
            )
        else:
            self.client = configured_client
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

        # v0.9 章节感知 - 每次 convert_pdf 前由调用方注入
        self._chapter_boundaries: List = []
        self._difficult_pages: set = set()
    
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
                'total_tokens': self.total_tokens,
                'cost': calculate_llm_cost(
                    self.model_name, self.prompt_tokens, self.completion_tokens
                ),
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

    def _has_algorithm_structure(self, text: str) -> bool:
        """保守识别论文中的伪代码块，避免把普通编号列表误判为算法。"""
        if not text:
            return False
        normalized = re.sub(r"\s+", " ", text)
        has_title = bool(re.search(r"\balgorithm\s*\d+\b|算法\s*\d+", normalized, re.IGNORECASE))
        has_control = bool(re.search(
            r"\b(?:input|output|require|ensure|initialize|initialise|while|for|if|then|return|end)\b|"
            r"(?:输入|输出|初始化|当|循环|如果|则|返回|结束)",
            normalized,
            re.IGNORECASE,
        ))
        # 标题是必要条件；再要求至少一个控制/初始化信号，降低章节列表误判率。
        return has_title and has_control

    def _attach_algorithm_context(self, page_text: str) -> str:
        """给算法页加入轻量语义标记，交由 LaTeX 转换阶段恢复伪代码环境。"""
        text = (page_text or "").strip()
        if not text or '[ALGORITHM_CONTEXT]' in text or not self._has_algorithm_structure(text):
            return text
        return f"[ALGORITHM_CONTEXT]\n{text}"

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
        """Synchronously translate text through the canonical async implementation."""
        return asyncio.run(self.translate_text_async(
            text,
            page_num,
            total_pages,
            display_page_num=display_page_num,
            display_total_pages=display_total_pages,
        ))

    async def translate_batch_async(
        self,
        pages_text: List[str],
        pages_info: List[Tuple[int, int]],  # (original_page_num, display_idx)
        display_total: int,
        translate: bool = True
    ) -> List[Tuple[int, str]]:
        """
        批量翻译多页文本，v0.9 章节感知版。

        策略：
        1. 若启用章节感知且PDF有检测到章节 → 按章节切分（每块最多 MAX_PAGES_PER_CHAPTER 页）
        2. 否则回退到固定 4-页块（v0.8 行为，完全兼容）
        3. 单块失败 → 并发回退到逐页翻译
        """
        if not translate:
            return [(p[0], t) for p, t in zip(pages_info, pages_text)]

        # 决定切分策略
        chunks = self._plan_chunks(pages_text, pages_info)
        logger.info(f"批量翻译分块: 共 {len(chunks)} 块（{'章节感知' if self._chapter_aware_active() else '4-页固定'}）")

        results: List[Tuple[int, str]] = []
        for chunk_texts, chunk_info in chunks:
            chunk_results = await self._translate_chunk(
                chunk_texts, chunk_info, display_total,
            )
            results.extend(chunk_results)
            translated_pages = {page for page, translated in chunk_results if translated.strip()}
            missing_indices = [
                idx for idx, (page, _display_idx) in enumerate(chunk_info)
                if idx < len(chunk_texts) and chunk_texts[idx].strip() and page not in translated_pages
            ]
            if missing_indices:
                missing_pages = [chunk_info[idx][0] + 1 for idx in missing_indices]
                logger.warning("批量翻译响应缺页 %s，改为逐页补译", missing_pages)
                results.extend(await self._fallback_translate_pages(
                    [chunk_texts[idx] for idx in missing_indices],
                    [chunk_info[idx] for idx in missing_indices],
                    display_total,
                ))
        return results

    def _chapter_aware_active(self) -> bool:
        """判断是否启用章节感知（CONFIG开关 + 缓存的边界非空）"""
        return bool(getattr(settings, 'ENABLE_CHAPTER_AWARE', False)) and bool(self._chapter_boundaries)

    def _plan_chunks(
        self,
        pages_text: List[str],
        pages_info: List[Tuple[int, int]],
    ) -> List[Tuple[List[str], List[Tuple[int, int]]]]:
        """
        决定如何切分页：章节感知 vs 4-页块。
        返回 [(chunk_texts, chunk_info), ...]
        """
        max_per_chunk = max(1, getattr(settings, 'MAX_PAGES_PER_CHAPTER', 8))

        # 章节感知路径
        if self._chapter_aware_active() and self._chapter_boundaries:
            # 把 boundaries 按 page_num 排序，构造 (start, end) 区间
            starts = sorted({b.page_num for b in self._chapter_boundaries} | {len(pages_text)})
            chunks: List[Tuple[List[str], List[Tuple[int, int]]]] = []
            prev_start = 0
            for s in starts:
                if s <= prev_start:
                    continue
                # 一个章节区间 [prev_start, s)，但单块不超过 max_per_chunk
                while prev_start < s:
                    end = min(prev_start + max_per_chunk, s)
                    chunks.append((
                        pages_text[prev_start:end],
                        pages_info[prev_start:end],
                    ))
                    prev_start = end
            return chunks

        # 4-页固定块（v0.8 兼容）
        CHUNK_SIZE = 4
        chunks = []
        for i in range(0, len(pages_text), CHUNK_SIZE):
            chunks.append((
                pages_text[i:i + CHUNK_SIZE],
                pages_info[i:i + CHUNK_SIZE],
            ))
        return chunks

    async def _translate_chunk(
        self,
        chunk_texts: List[str],
        chunk_info: List[Tuple[int, int]],
        display_total: int,
    ) -> List[Tuple[int, str]]:
        """
        翻译单个块（4页或一个章节）。
        v0.9: 块内 difficult 页抽出做双次翻译+LLM评分，其余走批量翻译。
        失败时回退到逐页并发翻译。
        """
        if not chunk_texts or all(not t.strip() for t in chunk_texts):
            return []

        # 分离 difficult 页与 normal 页
        normal_indices: List[int] = []
        difficult_indices: List[int] = []
        for idx, (original_page, _display_idx) in enumerate(chunk_info):
            if idx < len(chunk_texts) and chunk_texts[idx].strip():
                if original_page in self._difficult_pages:
                    difficult_indices.append(idx)
                else:
                    normal_indices.append(idx)

        results: List[Tuple[int, str]] = []

        # 1) difficult 页：双次翻译 + LLM评分（并发）
        if difficult_indices and getattr(settings, 'ENABLE_DIFFICULT_DOUBLE_TRANSLATE', False):
            difficult_results = await self._translate_difficult_pages(
                [chunk_texts[i] for i in difficult_indices],
                [chunk_info[i] for i in difficult_indices],
                display_total,
            )
            results.extend(difficult_results)

        # 2) normal 页：原批量翻译（difficulty 索引排除）
        remaining_texts = [chunk_texts[i] for i in normal_indices]
        remaining_info = [chunk_info[i] for i in normal_indices]

        if remaining_texts and any(t.strip() for t in remaining_texts):
            batch_results = await self._translate_pages_batch(
                remaining_texts, remaining_info, display_total,
            )
            results.extend(batch_results)

        # 3) 如果difficult全部失败回退到了空 → 把difficult页也用原批量兜底
        if difficult_indices and not any(p == chunk_info[i][0] for p, _ in results for i in difficult_indices):
            # 没有返回任何 difficult 页结果（说明被完全降级），让外层兜底处理
            pass

        return results

    async def _translate_pages_batch(
        self,
        chunk_texts: List[str],
        chunk_info: List[Tuple[int, int]],
        display_total: int,
    ) -> List[Tuple[int, str]]:
        """
        原批量翻译（仅 normal 页），失败时回退逐页并发。
        """
        if not chunk_texts or all(not t.strip() for t in chunk_texts):
            return []

        block_content = []
        for idx, (original_page, _display_idx) in enumerate(chunk_info):
            page_text = chunk_texts[idx] if idx < len(chunk_texts) else ''
            if not page_text.strip():
                continue
            block_content.append(f"[PAGE {original_page + 1}]\n{page_text}")

        if not block_content:
            return []

        combined_text = "\n---\n".join(block_content)
        combined_text = self._mark_duplicate_headers(combined_text)

        system_prompt = """你是一个专业的学术翻译助手。将英文学术文档翻译成中文。

要求：
1. 保持学术性和专业性
2. 数学公式、符号、变量名保持原样
3. 专业术语使用准确的中文翻译
4. 保持原文段落结构
5. 翻译流畅自然
6. **绝对禁止翻译参考文献条目**（包括 [10]、[11] 等编号格式的文献），保持英文原样
7. 如果参考文献在原文已经是中文，保留其中文内容不变
8. [PAGE X] 标记表示这是第X页，保留这些标记在输出中
9. [DUPLICATE_HEADER] 和 [DUPLICATE_FOOTER] 标记的内容是页眉页脚，通常不需要翻译（或只翻译一次）
10. [ALGORITHM_CONTEXT] 表示该页含伪代码；必须原样保留此标记，并翻译其自然语言内容
11. 只输出翻译后的文本，不要解释"""

        user_prompt = f"""请将以下多页学术文本翻译成中文（第 {display_total} 页中的 {len(chunk_info)} 页）：

{combined_text}

请保持 [PAGE X] 标记，对 [DUPLICATE_HEADER]/[DUPLICATE_FOOTER] 标记的内容只翻译一次。"""

        try:
            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=16000
            )

            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)

            content = LLMClient.extract_content(response)
            return self._parse_batch_translation(content, chunk_info)

        except Exception as e:
            logger.warning(f"批量翻译块失败: {e}")
            return await self._fallback_translate_pages(chunk_texts, chunk_info, display_total)

    async def _translate_difficult_pages(
        self,
        pages_text: List[str],
        pages_info: List[Tuple[int, int]],
        display_total: int,
    ) -> List[Tuple[int, str]]:
        """
        对每个 difficult 页：
        1. 并发调两次LLM（temperature=0.3 和 0.7）
        2. 调第三次 LLM 评分挑选最佳
        3. 失败时回退单次翻译或原文
        """
        if not pages_text:
            return []

        # 1) 两次并发翻译
        results: List[Tuple[int, str]] = []
        tasks_per_page: List = []  # [(page_num, [v1, v2]), ...]

        for text, (original_page, display_idx) in zip(pages_text, pages_info):
            try:
                v1, v2 = await asyncio.gather(
                    self._single_translate_for_difficult(text, original_page, display_total, temperature=0.3),
                    self._single_translate_for_difficult(text, original_page, display_total, temperature=0.7),
                    return_exceptions=True,
                )
            except Exception as e:
                logger.warning(f"困难页双次翻译并发失败 page {original_page + 1}: {e}")
                v1, v2 = None, None

            valid_versions: List[str] = []
            for v in (v1, v2):
                if isinstance(v, str) and v.strip():
                    valid_versions.append(v)
                elif isinstance(v, Exception):
                    logger.warning(f"困难页翻译失败 page {original_page + 1}: {v}")

            if not valid_versions:
                # 完全失败：回退到单次同步调用
                try:
                    fallback = await self._single_translate_for_difficult(
                        text, original_page, display_total, temperature=0.3,
                    )
                    results.append((original_page, fallback or text))
                except Exception as e:
                    logger.warning(f"困难页最终回退失败 page {original_page + 1}: {e}")
                    results.append((original_page, text))
                continue

            if len(valid_versions) == 1:
                results.append((original_page, valid_versions[0]))
                continue

            # 2) LLM 评分挑选最佳
            chosen = await self._pick_better_translation(text, valid_versions[0], valid_versions[1])
            results.append((original_page, chosen))

        return results

    async def _single_translate_for_difficult(
        self,
        text: str,
        original_page: int,
        display_total: int,
        temperature: float = 0.3,
    ) -> str:
        """单次同步翻译（不维护 [PAGE X] 标记，专为 difficult 页单页用）"""
        system_prompt = """你是一个专业的学术翻译助手。将英文学术文档翻译成中文。

要求：
1. 保持学术性和专业性
2. 数学公式、LaTeX 命令、变量名保持原样
3. 专业术语使用准确的中文翻译
4. 保持原文段落结构
5. 翻译流畅自然
6. 不要添加任何解释、注释或额外标记
7. 完整保留所有公式、表格和代码结构"""

        user_prompt = f"""请将以下单页内容（第 {original_page + 1} / {display_total} 页）翻译成中文：

{text}"""

        response = await self.client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=8000,
        )

        if 'usage' in response:
            usage = response['usage']
            self.prompt_tokens += usage.get('prompt_tokens', 0)
            self.completion_tokens += usage.get('completion_tokens', 0)
            self.total_tokens += usage.get('total_tokens', 0)

        return LLMClient.extract_content(response).strip()

    async def _pick_better_translation(self, original: str, v1: str, v2: str) -> str:
        """
        LLM 评分对比两版翻译，挑选最佳。
        失败时默认返回 v1（temperature=0.3，更稳定）。
        """
        try:
            system_prompt = "你是学术翻译质量评审，请严格按JSON格式输出。"
            user_prompt = f"""下面是对同一段英文的两种中文翻译版本。

【原文】
{original[:2000]}

【版本1】
{v1[:2000]}

【版本2】
{v2[:2000]}

请按以下维度评分（每项0-10分）：
- 准确性：是否准确传达原文意思
- 公式/LaTeX：数学公式、LaTeX命令保留是否完整
- 学术性：表达是否符合学术规范
- 流畅度：中文表达是否自然

输出JSON（严格遵循，不要解释）：
{{"winner": 1或2, "score1": x.x, "score2": y.y, "reason": "简短理由"}}"""

            response = await self.client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=500,
            )

            if 'usage' in response:
                usage = response['usage']
                self.prompt_tokens += usage.get('prompt_tokens', 0)
                self.completion_tokens += usage.get('completion_tokens', 0)
                self.total_tokens += usage.get('total_tokens', 0)

            content = LLMClient.extract_content(response).strip()
            # 简单 JSON 提取：找 winner 字段
            import json as _json
            # 容错：去掉 markdown 代码块
            cleaned = content
            if cleaned.startswith('```'):
                cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', cleaned, flags=re.MULTILINE).strip()
            try:
                data = _json.loads(cleaned)
                winner = int(data.get('winner', 1))
                return v1 if winner == 1 else v2
            except (ValueError, _json.JSONDecodeError):
                # 退而求其次：找 "winner": 1 或 2
                m = re.search(r'"winner"\s*:\s*([12])', content)
                if m:
                    return v1 if m.group(1) == '1' else v2
                logger.warning(f"评分JSON解析失败，默认选v1: {content[:100]}")
                return v1
        except Exception as e:
            logger.warning(f"LLM评分失败，默认选v1: {e}")
            return v1

    async def _fallback_translate_pages(
        self,
        chunk_texts: List[str],
        chunk_info: List[Tuple[int, int]],
        display_total: int,
    ) -> List[Tuple[int, str]]:
        """并发回退到逐页翻译"""
        fallback_tasks = []
        fallback_pages = []
        for idx, (original_page, display_idx) in enumerate(chunk_info):
            if idx < len(chunk_texts) and chunk_texts[idx].strip():
                fallback_tasks.append(
                    self.translate_text_async(
                        chunk_texts[idx], original_page, display_total,
                        display_page_num=display_idx, display_total_pages=display_total
                    )
                )
                fallback_pages.append(original_page)

        if not fallback_tasks:
            return []

        fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=True)
        results = []
        for original_page, result in zip(fallback_pages, fallback_results):
            if isinstance(result, Exception):
                logger.warning(f"回退失败 page {original_page + 1}: {result}")
            else:
                results.append((original_page, result))
        return results

    def _mark_duplicate_headers(self, combined_text: str) -> str:
        """检测连续出现的重复内容（页眉页脚），标记为需要去重"""
        lines = combined_text.split('\n')
        marked_lines = []
        prev_line = ""
        seen_lines = {}  # 记录已见过的短行及其首次出现的索引

        for line in lines:
            stripped = line.strip()
            is_short_duplicate = len(stripped) < 60 and stripped and stripped == prev_line

            if is_short_duplicate and stripped not in seen_lines:
                # 第一次出现重复，标记
                seen_lines[stripped] = len(marked_lines)
                marked_lines.append(f"[DUPLICATE_HEADER]{stripped}[/DUPLICATE_HEADER]")
            elif is_short_duplicate and stripped in seen_lines:
                # 后续重复行跳过
                pass
            else:
                marked_lines.append(line)

            prev_line = stripped

        return '\n'.join(marked_lines)

    def _parse_batch_translation(self, content: str, chunk_info: List[Tuple[int, int]]) -> List[Tuple[int, str]]:
        """解析批量翻译结果，按PAGE标记分割"""
        results = []

        # 按PAGE标记分割
        pages_content = re.split(r'\[PAGE\s+(\d+)\]', content)

        if len(pages_content) <= 1:
            # 段落数和页数没有可靠对应关系。此前按空行硬切会导致英文原文被
            # 静默送入后续“已翻译”转换流程；返回空，让调用方逐页补译。
            logger.warning("批量翻译响应缺少 PAGE 标记，拒绝按段落猜测页映射")
            return results

        # pages_content[0]是前缀，[1]=页码1, [2]=内容1, [3]=页码2, [4]=内容2, ...
        for i in range(1, len(pages_content), 2):
            if i + 1 >= len(pages_content):
                break
            page_num = int(pages_content[i])
            page_content = pages_content[i + 1]

            # 清理duplicate标记
            page_content = re.sub(r'\[DUPLICATE_HEADER\].*?\[/DUPLICATE_HEADER\]', '', page_content)
            page_content = re.sub(r'\[DUPLICATE_FOOTER\].*?\[/DUPLICATE_FOOTER\]', '', page_content)

            # 只接受当前块请求的页，防止模型生成幻觉页码污染映射。
            original_page = page_num - 1
            requested_pages = {page for page, _display_idx in chunk_info}
            if original_page in requested_pages and page_content.strip():
                results.append((original_page, page_content.strip()))

        return results

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
        # Column markers are extraction metadata, not output-layout commands.
        text = text.replace('[TWO_COLUMN_PAGE]', '')
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
    6. **绝对禁止翻译参考文献条目**（包括 [10]、[11] 等编号格式的文献），保持英文原样：作者名、论文标题、期刊名、会议名、出版社全部保持原文
    7. 如果参考文献在原文已经是中文，保留其中文内容不变
    8. 只输出翻译后的文本
    9. 忽略任何页面布局标记；只翻译文本，不生成任何 LaTeX 排版环境或命令。"""
        system_prompt += self._compose_translation_guidance()

        user_prompt = f"""请将以下英文学术文本翻译成中文（第 {display_page_num + 1}/{display_total_pages} 页）：
注意：如果以下文本包含参考文献部分（以 [数字] 编号的条目），请勿翻译这些文献条目，保持英文原样。

{main_text}

参考文献条目必须保持英文，不翻译作者名、标题、期刊名。"""

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

        system_prompt += "\n\nKeep the output single-column. Do not add, preserve, or rewrite any page-layout command such as \\vspace, \\newpage, \\pagebreak, or multicols."

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

    def _should_use_local_latex(self, quality_mode: str) -> bool:
        return (
            getattr(settings, 'ENABLE_LOCAL_LATEX_CONVERSION', True)
            and quality_mode != 'high'
        )

    def _escape_latex_text(self, text: str) -> str:
        replacements = {
            '\\': r'\textbackslash{}',
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
        }
        return ''.join(replacements.get(ch, ch) for ch in text)

    def _escape_text_preserving_inline_math(self, text: str) -> str:
        r"""Escape prose while preserving complete ``\( ... \)`` expressions."""
        # A translated paragraph commonly contains small inline expressions such
        # as ``\(A\)`` or ``\(i^* = 1\)``. Escaping its backslashes turns it
        # into ``\textbackslash{}(``, which is neither LaTeX nor KaTeX math.
        # Keep only complete, single-line delimiters; malformed ones remain text
        # and are safely escaped.
        parts = re.split(r'(\\\([^\r\n]*?\\\))', text)
        return ''.join(
            part if index % 2 else self._escape_latex_text(part)
            for index, part in enumerate(parts)
        )

    def _looks_like_latex_or_math(self, line: str) -> bool:
        s = line.strip()
        if not s:
            return False

        # A LaTeX command or an explicit delimiter is an unambiguous signal.
        # Do not treat every underscore or percent sign as math: they are common
        # in prose and should be escaped as text instead of put in display math.
        if re.fullmatch(r'\\\([^\r\n]+?\\\)', s):
            return True
        if re.search(r'\\[a-zA-Z]+|\\\[|\\begin\{|\$[^$]+\$', s):
            return True

        # A sentence containing inline math is still prose. It must remain a
        # paragraph so the inline delimiter can be rendered in place.
        if re.search(r'\\\([^\r\n]*?\\\)', s):
            return False

        # Do not promote a fragment left by PDF extraction (for example ``√``
        # or ``√ √``) to an equation.  A Unicode symbol needs equation context.
        if re.fullmatch(r'[√∑∫∏±∓≈≠≤≥=+\-*/·.,:;()\[\]{}|\s]+', s):
            return False
        if re.search(r'[∑∫√≤≥≈∞α-ωΑ-Ω]', s):
            has_equation_context = bool(re.search(r'[A-Za-z0-9]|[_^=+\-*/]', s))
            if has_equation_context and (len(re.findall(r'[A-Za-z0-9]', s)) >= 2 or '=' in s):
                return True

        # Recognise compact equations, but never classify a prose sentence just
        # because it contains an equals sign. PDF extraction often drops spaces,
        # so this check deliberately requires a small number of word-like terms.
        compact = re.sub(r'\s+', ' ', s)
        if re.fullmatch(r'[A-Za-z](?:_[A-Za-z0-9]+)?(?:\^[A-Za-z0-9{}+-]+)?', compact):
            return True
        if not re.fullmatch(
            r'[A-Za-z0-9_{}().,+\-*/^ ]+\s*(?:=|<=|>=|<|>)\s*[A-Za-z0-9_{}().,+\-*/^ ]+',
            compact,
        ):
            return False
        word_terms = re.findall(r'[A-Za-z]{2,}', compact)
        return (
            len(word_terms) <= 2
            and not any(len(term) > 16 for term in word_terms)
            and not re.search(r'[;:!?]', compact)
        )

    def _format_math_line(self, line: str) -> str:
        s = line.strip()
        if re.match(r'^(\\begin\{|\\end\{|\\\[|\\\]|\\\(|\\\)|\$)', s):
            return s
        if re.fullmatch(r'[√∑∫∏±∓≈≠≤≥=+\-*/·.,:;()\[\]{}|\s]+', s):
            return ''
        if re.search(r'[$^_=]|\\[a-zA-Z]+', s):
            return "\\[\n" + s + "\n\\]"
        if re.search(r'[∑∫√≤≥≈∞α-ωΑ-Ω]', s) and re.search(r'[A-Za-z0-9]', s):
            return "\\[\n" + s + "\n\\]"
        return s

    def _is_formula_line_continuation(self, previous: str, following: str) -> bool:
        """Recognise a PDF line wrap only when the mathematical join is explicit."""
        previous = (previous or '').strip()
        following = (following or '').strip()
        if not previous or not following:
            return False
        unfinished = bool(
            re.search(r'(?:[=+*/^_({\[]|\\(?:frac|sum|int|prod|left))\s*$', previous)
            or previous.count('{') > previous.count('}')
            or previous.count('(') > previous.count(')')
            or previous.count('[') > previous.count(']')
        )
        if not unfinished:
            return False
        return bool(re.match(r'^(?:[+*/=,)}\]]|\\[A-Za-z]+|[A-Za-z0-9({[])', following))

    def _format_math_block(self, lines: List[str]) -> str:
        """Join proven wrapped formulas and break only long top-level expressions."""
        formula = ' '.join(line.strip() for line in lines if line.strip())
        if not formula:
            return ''
        if len(formula) <= 140:
            return self._format_math_line(formula)

        # Break only after a top-level binary operator. This keeps braces and
        # LaTeX commands intact rather than guessing a syntactic reconstruction.
        breakpoints: List[int] = []
        brace_depth = paren_depth = bracket_depth = 0
        for index, char in enumerate(formula):
            if char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth = max(0, brace_depth - 1)
            elif char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth = max(0, paren_depth - 1)
            elif char == '[':
                bracket_depth += 1
            elif char == ']':
                bracket_depth = max(0, bracket_depth - 1)
            elif char in '+-' and brace_depth == paren_depth == bracket_depth == 0:
                if index > 0 and formula[index - 1] not in '^_':
                    breakpoints.append(index + 1)

        pieces: List[str] = []
        start = 0
        target_width = 110
        while len(formula) - start > 140:
            candidates = [point for point in breakpoints if start + 30 <= point <= start + target_width]
            if not candidates:
                break
            point = candidates[-1]
            pieces.append(formula[start:point].strip())
            start = point
        pieces.append(formula[start:].strip())
        if len(pieces) == 1:
            return self._format_math_line(formula)

        aligned_lines = ['& ' + pieces[0] + r' \\']
        aligned_lines.extend(r'&\quad ' + piece + r' \\' for piece in pieces[1:-1])
        aligned_lines.append(r'&\quad ' + pieces[-1])
        return '\\[\n\\begin{aligned}\n' + '\n'.join(aligned_lines) + '\n\\end{aligned}\n\\]'

    def _looks_like_heading(self, line: str) -> bool:
        s = line.strip()
        if len(s) > 90 or s.endswith(('.', ',', ';', ':')):
            return False
        return bool(
            re.match(r'^(chapter|section)\s+\d+[\s:.-]+\S+', s, re.IGNORECASE)
            or re.match(r'^\d+(?:\.\d+){0,3}\.?\s+\S+', s)
            or re.match(r'^(摘要|引言|结论|参考文献|bibliography|references)\b', s, re.IGNORECASE)
        )

    def _convert_structured_table_context(self, text: str) -> str:
        rows = []
        for line in text.splitlines():
            match = re.match(r'\s*ROW\s+\d+\s*:\s*(.+)$', line, re.IGNORECASE)
            if not match:
                continue
            cells = [self._escape_latex_text(cell.strip() or '--') for cell in match.group(1).split('|')]
            if cells:
                rows.append(cells)
        if not rows:
            return ''

        max_cols = max(len(row) for row in rows)
        normalized = [row + ['--'] * (max_cols - len(row)) for row in rows]
        col_spec = '|' + '|'.join(['l'] * max_cols) + '|'
        body = ['\\begin{tabular}{' + col_spec + '}', '\\hline']
        for row in normalized:
            body.append(' & '.join(row) + r' \\')
            body.append('\\hline')
        body.append('\\end{tabular}')
        return '\n'.join(body)

    def _local_text_to_latex(self, text: str) -> str:
        text = text.replace('[TWO_COLUMN_PAGE]', '').strip()

        table_latex = ''
        if '[STRUCTURED_TABLE_CONTEXT]' in text:
            text, table_context = text.split('[STRUCTURED_TABLE_CONTEXT]', 1)
            table_latex = self._convert_structured_table_context(table_context)

        blocks = []
        paragraph = []
        math_lines: List[str] = []

        def flush_paragraph():
            if paragraph:
                blocks.append(' '.join(paragraph).strip())
                paragraph.clear()

        def flush_math_lines():
            if math_lines:
                blocks.append(self._format_math_block(math_lines))
                math_lines.clear()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                flush_paragraph()
                flush_math_lines()
                continue
            if line.startswith('[') and line.endswith(']'):
                continue
            if self._looks_like_heading(line):
                flush_paragraph()
                flush_math_lines()
                blocks.append(r'\section*{' + self._escape_latex_text(line) + '}')
            elif self._looks_like_latex_or_math(line) or (
                math_lines and self._is_formula_line_continuation(math_lines[-1], line)
            ):
                flush_paragraph()
                if math_lines and not self._is_formula_line_continuation(math_lines[-1], line):
                    flush_math_lines()
                math_lines.append(line)
            else:
                flush_math_lines()
                paragraph.append(self._escape_text_preserving_inline_math(line))

        flush_paragraph()
        flush_math_lines()
        if table_latex:
            blocks.append(table_latex)

        latex = '\n\n'.join(block for block in blocks if block.strip())
        return latex

    def convert_text_to_latex(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        translate: bool = False,
        quality_mode: str = 'standard',
        force_llm: bool = False,
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """Synchronously convert text through the canonical async implementation."""
        return asyncio.run(self.convert_text_to_latex_async(
            text,
            page_num,
            total_pages,
            translate=translate,
            quality_mode=quality_mode,
            force_llm=force_llm,
            display_page_num=display_page_num,
            display_total_pages=display_total_pages,
        ))

    async def convert_text_to_latex_async(
        self,
        text: str,
        page_num: int,
        total_pages: int,
        translate: bool = False,
        quality_mode: str = 'standard',
        force_llm: bool = False,
        display_page_num: Optional[int] = None,
        display_total_pages: Optional[int] = None,
    ) -> str:
        """异步转换文本为LaTeX"""
        display_page_num = page_num if display_page_num is None else display_page_num
        display_total_pages = total_pages if display_total_pages is None else display_total_pages
        text = text.replace('[TWO_COLUMN_PAGE]', '')
        quality = self._check_text_quality(text)
        logger.info(f"第 {display_page_num + 1}/{display_total_pages} 页文本质量: {quality:.2f}, 长度: {len(text)}")

        if not text.strip():
            logger.warning(f"第 {page_num + 1} 页没有提取到文本，可能是扫描版PDF")
            return f"% 警告：第 {page_num + 1} 页无法提取文本\n% 这可能是扫描版PDF，建议使用OCR工具处理\n"

        if quality < 0.3:
            logger.warning(f"第 {display_page_num + 1}/{display_total_pages} 页文本质量较低 ({quality:.2f})，可能包含乱码")

        if translate:
            text = await self.translate_text_async(
                text,
                page_num,
                total_pages,
                display_page_num=display_page_num,
                display_total_pages=display_total_pages,
            )

        if self._should_use_local_latex(quality_mode) and not force_llm:
            self._emit_progress(
                'converting',
                page_num,
                total_pages,
                f'正在本地转换第 {display_page_num + 1}/{display_total_pages} 页为 LaTeX...'
            )
            return sanitize_latex_body(self._local_text_to_latex(text))

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
11. 只输出正文内容的LaTeX代码
12. 输出必须是单栏正文；禁止使用 \\begin{multicols}、\\vspace、\\newpage 或任何页面布局命令。
13. 只将纯数学表达式放入 \\[...\\] 或其他数学环境；解释性正文、中文句子、标题和作者信息不得放入数学环境。
14. 数学环境不得嵌套，且每个 \\[ 必须有一个对应的 \\]。无法可靠恢复的公式碎片保留为普通文本，禁止输出孤立的 √、=、- 等符号。
15. 若输入含 [ALGORITHM_CONTEXT]，它是论文伪代码，不是普通表格或编号列表。必须输出 `\\begin{algorithm}`、`\\caption{...}`、`\\begin{algorithmic}[1]` 和对应的 `\\end`；用 `\\Require`/`\\Ensure`、`\\State`、`\\While`/`\\EndWhile`、`\\For`/`\\EndFor`、`\\If`/`\\EndIf`、`\\Return` 还原明确的控制结构。看不清的步骤保留为 `\\State` 文本，禁止臆造控制流。"""

        user_prompt = f"""请将以下文本转换为LaTeX格式（第 {display_page_num + 1}/{display_total_pages} 页）：

{text}

只输出LaTeX内容代码，不要包含文档结构或定理/引理/证明环境。

特别要求：如果看到 [STRUCTURED_TABLE_CONTEXT]，请据此还原完整表格，确保每行列数一致；如果看到 [ALGORITHM_CONTEXT]，请按 algorithm + algpseudocode 伪代码环境输出。"""

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

    def _find_formula_dense_pages(self, pdf_path: str, pages: List[int]) -> set[int]:
        """Choose pages that need LLM formula reconstruction in standard mode."""
        if not (
            getattr(settings, 'ENABLE_LOCAL_LATEX_CONVERSION', True)
            and pages
        ):
            return set()

        threshold = max(0.0, min(1.0, getattr(settings, 'LOCAL_MATH_DENSITY_THRESHOLD', 0.20)))
        try:
            features = self.document_parser.classify_difficult_pages(pdf_path)
            dense_pages = {
                feature.page_num
                for feature in features
                if feature.page_num in pages and feature.formula_density >= threshold
            }
            if dense_pages:
                logger.info(
                    "公式密集页将使用 LLM：%s（阈值 %.0f%%）",
                    sorted(page + 1 for page in dense_pages),
                    threshold * 100,
                )
            return dense_pages
        except Exception as exc:
            logger.warning("公式密度检测失败，回退为本地转换：%s", exc)
            return set()

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
        logger.info(f"转换开始: PDF路径={pdf_path}, 页码={pages}, 翻译={translate}")
        start_time = time.time()
        
        # 重置统计
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

        # v0.9 章节检测 + 困难页分类（仅翻译模式有效）
        self._chapter_boundaries = []
        self._difficult_pages = set()
        if translate:
            try:
                if getattr(settings, 'ENABLE_CHAPTER_AWARE', False):
                    self._chapter_boundaries = self.document_parser.detect_chapter_boundaries(pdf_path)
                    logger.info(f"章节检测: 发现 {len(self._chapter_boundaries)} 个标题边界")
                if getattr(settings, 'ENABLE_DIFFICULT_DOUBLE_TRANSLATE', False):
                    features = self.document_parser.classify_difficult_pages(pdf_path)
                    self._difficult_pages = {f.page_num for f in features if f.is_difficult}
                    logger.info(f"困难页分类: {len(self._difficult_pages)} 页标记为困难")
            except Exception as e:
                logger.warning(f"v0.9 章节/困难页检测失败，回退到4-页块: {e}")
                self._chapter_boundaries = []
                self._difficult_pages = set()
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

        if output_path is None:
            pdf_file = Path(pdf_path)
            suffix = "_cn" if translate else ""
            output_path = str(pdf_file.parent / f"{pdf_file.stem}{suffix}.tex")
        else:
            output_path = str(Path(output_path))
        
        # 先获取PDF总页数
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
        except Exception as e:
            logger.warning(f"PyPDF2读取PDF失败: {e}，尝试使用pdfplumber")
            try:
                import pdfplumber
                with pdfplumber.open(pdf_path) as pdf:
                    total_pages = len(pdf.pages)
            except Exception as e2:
                logger.error(f"pdfplumber也无法读取PDF: {e2}")
                raise RuntimeError(f"无法读取PDF文件: {pdf_path}") from e2
        
        # 确定要提取的页码
        if pages is None:
            pages = list(range(total_pages))
        else:
            pages = [p for p in pages if 0 <= p < total_pages]
        
        logger.info(f"准备提取 {len(pages)}/{total_pages} 页: {pages}")

        # 只提取需要的页面
        pages_text = self.extract_text_from_pdf(pdf_path, pages)
        algorithm_pages = {
            page_num for page_num in pages
            if page_num < len(pages_text) and self._has_algorithm_structure(pages_text[page_num])
        }
        if algorithm_pages:
            logger.info("检测到伪代码算法页：%s", sorted(page + 1 for page in algorithm_pages))

        # Formula fragments that genuinely cross a page boundary must be kept
        # together before independent page conversion starts.
        cross_page_formula_pages = stitch_cross_page_formula_fragments(pages_text, pages)
        formula_dense_pages = set()
        if quality_mode != 'high':
            formula_dense_pages = self._find_formula_dense_pages(pdf_path, pages)
        formula_dense_pages.update(cross_page_formula_pages)
        if cross_page_formula_pages:
            logger.info(
                "跨页公式相关页将使用 LLM：%s",
                sorted(page + 1 for page in cross_page_formula_pages),
            )

        # 构建LaTeX正文
        latex_content = []
        failed_pages = []
        page_diagnostics = []

        mode_desc = "翻译并转换" if translate else "转换"
        processed_pages = 0
        total_to_process = len(pages)

        # 批量翻译模式：每4页作为一块，减少API调用次数
        if translate:
            async def batch_translate_pages():
                pages_info = [(p, idx) for idx, p in enumerate(pages)]
                translated_results = await self.translate_batch_async(
                    pages_text,
                    pages_info,
                    total_to_process,
                    translate=True
                )
                return translated_results

            translated_map = {}
            try:
                translated_results = asyncio.run(batch_translate_pages())
                for original_page, translated_text in translated_results:
                    translated = self._attach_algorithm_context(translated_text)
                    # 即使翻译模型遗漏了内部标记，也要继承原始页已确认的算法结构。
                    if original_page in algorithm_pages and '[ALGORITHM_CONTEXT]' not in translated:
                        translated = f"[ALGORITHM_CONTEXT]\n{translated.strip()}"
                    translated_map[original_page] = translated
                logger.info(f"批量翻译完成: {len(translated_map)}/{len(pages)} 页")
            except Exception as e:
                logger.warning(f"批量翻译失败: {e}，回退到逐页翻译")
                translated_map = {}

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
                page_text_to_convert = self._attach_algorithm_context(text)
                if translate:
                    if page_num not in translated_map:
                        raise Exception(
                            "该页翻译未返回有效结果；已停止转换以避免把原英文混入中文输出。"
                        )
                    page_text_to_convert = translated_map[page_num]

                use_llm_for_formula = (
                    page_num in formula_dense_pages
                    or '[ALGORITHM_CONTEXT]' in page_text_to_convert
                )
                if use_llm_for_formula:
                    structure_reason = '算法伪代码' if '[ALGORITHM_CONTEXT]' in page_text_to_convert else '公式密度较高'
                    self._emit_progress(
                        'converting',
                        idx,
                        total_to_process,
                        f'检测到{structure_reason}，正在调用 LLM 转换第 {idx + 1}/{total_to_process} 页...',
                        'info',
                        f'第 {idx + 1} 页{structure_reason}，使用 LLM 重建公式与版式',
                    )

                latex_page = await self.convert_text_to_latex_async(
                    page_text_to_convert,
                    page_num,
                    len(pages_text),
                    translate=False,  # 已经翻译过了，不再重复翻译
                    quality_mode=quality_mode,
                    force_llm=use_llm_for_formula,
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
            except InsufficientBalanceError:
                # Stop the entire job: account-level failures are not page errors.
                raise
            except Exception as e:
                err_text = str(e)
                logger.warning(f"第 {page_num + 1} 页{mode_desc}失败: {err_text}")
                failed_pages.append((page_num + 1, err_text))
                return page_num, None, False

        async def process_all_pages():
            # 控制并发，避免同时发起过多LLM请求导致连接失败。
            # This limits per-page LLM-to-LaTeX conversions only; translation
            # batching has an independent request pattern.
            conversion_concurrency = max(1, settings.LLM_CONVERSION_CONCURRENCY)
            semaphore = asyncio.Semaphore(conversion_concurrency)

            async def _run_with_limit(idx: int, page_num: int):
                async with semaphore:
                    return await process_page(idx, page_num)

            tasks = [_run_with_limit(idx, page_num) for idx, page_num in enumerate(pages)]
            return await asyncio.gather(*tasks)

        results = asyncio.run(process_all_pages())

        for page_num, latex_page, ok in results:
            if not ok:
                error_text = next(
                    (message for failed_page, message in failed_pages if failed_page == page_num + 1),
                    '该页未产生 LaTeX 输出。',
                )
                page_diagnostics.append({
                    'page': page_num + 1,
                    'status': 'error',
                    'valid': False,
                    'errors_count': 1,
                    'warnings_count': 0,
                    'diagnostics': [{
                        'code': 'conversion_failed',
                        'severity': 'error',
                        'message': error_text,
                        'line': 1,
                    }],
                })
                latex_content.append(f"% 第 {page_num + 1} 页{mode_desc}失败")
                latex_content.append("")
                continue
            if latex_page is None:
                continue
            validation = validate_latex_page(latex_page)
            page_diagnostics.append({
                'page': page_num + 1,
                'status': 'warning' if validation['warnings_count'] else 'success',
                **validation,
            })
            if validation['warnings_count'] or validation['errors_count']:
                logger.warning(
                    "第 %s 页 LaTeX 校验发现 %s 个错误、%s 个警告",
                    page_num + 1, validation['errors_count'], validation['warnings_count'],
                )
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
            'page_diagnostics': page_diagnostics,
            'total_tokens': self.total_tokens,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'cost': calculate_llm_cost(
                self.model_name, self.prompt_tokens, self.completion_tokens
            ),
            'processing_time': round(processing_time, 2),
            'source_text': source_text
        }
