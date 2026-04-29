#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
渐进式双语对照阅读模块
将原文和翻译按段落/句子级别对齐，支持 hover 显示原文
"""

import re
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class BlockType(Enum):
    """内容块类型"""
    PARAGRAPH = "paragraph"
    MATH_BLOCK = "math"
    TABLE = "table"
    FIGURE = "figure"
    ENV_BLOCK = "environment"  # theorem, proof 等环境
    LINE = "line"  # 单行内容


@dataclass
class BilingualBlock:
    """双语对照块"""
    block_id: str  # 唯一标识
    block_type: BlockType
    original: str  # 原文
    translation: str  # 译文
    line_numbers: Tuple[int, int]  # (原文行号, 译文行号)
    is_translated: bool  # 是否已翻译
    confidence: float  # 翻译置信度（0-1）
    latex_content: Optional[str] = None  # LaTeX 渲染内容（如果有）
    page_number: Optional[int] = None  # 页码

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.block_id,
            'type': self.block_type.value,
            'original': self.original,
            'translation': self.translation,
            'line_numbers': self.line_numbers,
            'is_translated': self.is_translated,
            'confidence': self.confidence,
            'latex_content': self.latex_content,
            'page_number': self.page_number
        }


@dataclass
class BilingualDocument:
    """双语对照文档"""
    blocks: List[BilingualBlock] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'blocks': [b.to_dict() for b in self.blocks],
            'statistics': self.statistics
        }

    def get_html_hover_format(self) -> str:
        """
        生成支持 hover 的 HTML 格式
        翻译显示在主位置，hover 时显示原文
        """
        html_parts = []

        for block in self.blocks:
            if block.block_type == BlockType.MATH_BLOCK:
                # 数学公式直接渲染
                html_parts.append(f'<div class="bilingual-block math" data-original="{self._escape_html(block.original)}">{block.translation or block.original}</div>')
            elif block.block_type == BlockType.TABLE:
                # 表格保持原样
                html_parts.append(f'<div class="bilingual-block table">{block.translation or block.original}</div>')
            elif block.is_translated:
                # 已翻译的内容：显示译文，hover 显示原文
                tooltip = self._escape_html(block.original)
                html_parts.append(
                    f'<div class="bilingual-block" '
                    f'data-original="{tooltip}" '
                    f'data-translation="{self._escape_html(block.translation)}">'
                    f'{block.translation}</div>'
                )
            else:
                # 未翻译的内容
                html_parts.append(f'<div class="bilingual-block untranslated">{block.original}</div>')

        return '\n'.join(html_parts)

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符"""
        if not text:
            return ""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_blocks = len(self.blocks)
        translated_blocks = sum(1 for b in self.blocks if b.is_translated)
        math_blocks = sum(1 for b in self.blocks if b.block_type == BlockType.MATH_BLOCK)
        table_blocks = sum(1 for b in self.blocks if b.block_type == BlockType.TABLE)

        return {
            'total_blocks': total_blocks,
            'translated_blocks': translated_blocks,
            'untranslated_blocks': total_blocks - translated_blocks,
            'translation_rate': translated_blocks / total_blocks if total_blocks > 0 else 0,
            'math_blocks': math_blocks,
            'table_blocks': table_blocks,
            'paragraph_blocks': sum(1 for b in self.blocks if b.block_type == BlockType.PARAGRAPH)
        }


class BilingualSegmenter:
    """双语对照分段器"""

    # LaTeX 环境模式
    MATH_ENVIRONMENTS = [
        'equation', 'equation*', 'eqnarray', 'eqnarray*',
        'align', 'align*', 'gather', 'gather*',
        'multline', 'multline*', 'flalign', 'flalign*',
        'math', 'displaymath', 'verbatim'
    ]

    TABLE_ENVIRONMENTS = ['tabular', 'tabular*', 'table', 'table*']

    THEOREM_ENVIRONMENTS = [
        'theorem', 'lemma', 'proposition', 'corollary',
        'proof', 'definition', 'example', 'remark',
        'exercise', 'problem', 'solution'
    ]

    def __init__(self):
        self.math_pattern = re.compile(
            r'(\$\$?.*?\$\$?|' +
            r'\\\[.*?\\\]|' +
            r'\\\(['
            r'.*?\\\])',
            re.DOTALL
        )
        self.paragraph_separator = re.compile(r'\n\s*\n')
        self.multicol_pattern = re.compile(r'\\begin\{multicols\*?\}')

    def segment(
        self,
        original_content: str,
        translated_content: str,
        original_lines: Optional[List[str]] = None,
        translated_lines: Optional[List[str]] = None
    ) -> BilingualDocument:
        """
        将原文和译文分段并对齐

        Args:
            original_content: 原始文本
            translated_content: 翻译文本
            original_lines: 原始文本分行（用于行号对应）
            translated_lines: 翻译文本分行

        Returns:
            BilingualDocument 对象
        """
        doc = BilingualDocument()

        # 默认分行
        if original_lines is None:
            original_lines = original_content.split('\n')
        if translated_lines is None:
            translated_lines = translated_content.split('\n')

        # 分段
        segments = self._split_into_segments(original_lines, translated_lines)

        # 构建双语块
        for idx, (orig_seg, trans_seg) in enumerate(segments):
            block_type = self._classify_segment(orig_seg)
            block_id = f"block_{idx}"

            # 判断是否已翻译
            is_translated = bool(trans_seg.strip()) and trans_seg.strip() != orig_seg.strip()

            # 估算置信度
            confidence = self._estimate_confidence(orig_seg, trans_seg)

            # 提取 LaTeX 内容（如果是数学块）
            latex_content = None
            if block_type == BlockType.MATH_BLOCK:
                latex_content = trans_seg or orig_seg

            block = BilingualBlock(
                block_id=block_id,
                block_type=block_type,
                original=orig_seg,
                translation=trans_seg,
                line_numbers=(0, 0),  # 简化处理
                is_translated=is_translated,
                confidence=confidence,
                latex_content=latex_content
            )
            doc.blocks.append(block)

        doc.statistics = doc.get_statistics()
        return doc

    def _split_into_segments(
        self,
        original_lines: List[str],
        translated_lines: List[str]
    ) -> List[Tuple[str, str]]:
        """将文本分割成段落/句子级别的块"""
        segments = []

        # 简单实现：按段落分割
        # 合并行成为段落
        orig_paragraphs = self._merge_lines_to_paragraphs(original_lines)
        trans_paragraphs = self._merge_lines_to_paragraphs(translated_lines)

        # 对齐段落
        max_len = max(len(orig_paragraphs), len(trans_paragraphs))

        for i in range(max_len):
            orig = orig_paragraphs[i] if i < len(orig_paragraphs) else ""
            trans = trans_paragraphs[i] if i < len(trans_paragraphs) else ""
            segments.append((orig, trans))

        return segments

    def _merge_lines_to_paragraphs(self, lines: List[str]) -> List[str]:
        """将行合并为段落"""
        paragraphs = []
        current_para = []

        for line in lines:
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('%'):
                continue

            # 跳过页码行
            if re.match(r'^\d+\s*$', stripped):
                continue

            # 跳过空行（分割点）
            if not stripped:
                if current_para:
                    paragraphs.append('\n'.join(current_para))
                    current_para = []
                continue

            current_para.append(stripped)

        if current_para:
            paragraphs.append('\n'.join(current_para))

        return paragraphs

    def _classify_segment(self, content: str) -> BlockType:
        """分类内容块类型"""
        if not content.strip():
            return BlockType.PARAGRAPH

        # 检查是否是数学环境
        if self._is_math_block(content):
            return BlockType.MATH_BLOCK

        # 检查是否是表格
        if '\\begin{tabular' in content or '\\begin{tabular*' in content:
            return BlockType.TABLE

        # 检查是否是定理/证明环境
        for env in self.THEOREM_ENVIRONMENTS:
            if f'\\begin{{{env}' in content.lower():
                return BlockType.ENV_BLOCK

        # 检查是否是图片
        if '\\begin{figure' in content or '\\includegraphics' in content:
            return BlockType.FIGURE

        return BlockType.PARAGRAPH

    def _is_math_block(self, content: str) -> bool:
        """判断是否是数学公式块"""
        # 独立的数学行
        math_indicators = [
            r'^\s*\$',  # 行内公式开始
            r'\$\s*$',  # 行内公式结束
            r'^\s*\\\[',  # display math 开始
            r'\\\]\s*$',  # display math 结束
            r'\\begin\{equation',
            r'\\begin\{align',
            r'\\begin\{gather',
            r'\\frac\{',  # 分数
            r'\\sum\{',  # 求和
            r'\\int_',  # 积分
            r'\^{',  # 上标
            r'_{',  # 下标
        ]

        for pattern in math_indicators:
            if re.search(pattern, content):
                return True

        # 检查数学符号密度
        math_chars = sum(1 for c in content if c in '{}∫∑∏∞≤≥≈≠+-=')
        total_chars = len(content)
        if total_chars > 0 and math_chars / total_chars > 0.1:
            return True

        return False

    def _estimate_confidence(self, original: str, translation: str) -> float:
        """估算翻译置信度"""
        if not translation.strip():
            return 0.0

        if not original.strip():
            return 0.5

        # 完全相同，置信度低
        if original.strip() == translation.strip():
            return 0.3

        # 检查翻译长度是否合理
        len_ratio = len(translation) / max(len(original), 1)
        if len_ratio < 0.3 or len_ratio > 3.0:
            return 0.5

        # 检查是否包含乱码
        chinese_chars = sum(1 for c in translation if '一' <= c <= '鿿')
        total_chars = len(translation)
        if total_chars > 0:
            chinese_ratio = chinese_chars / total_chars
            if chinese_ratio < 0.1 and len(original) > 50:
                # 长文本但几乎没有中文字符，可能是未翻译
                return 0.4

        return 0.8  # 默认置信度


# 快捷函数
def create_bilingual_view(
    original_content: str,
    translated_content: str
) -> Dict[str, Any]:
    """
    创建双语对照视图数据

    Returns:
        {
            'blocks': [...],  # 双语块列表
            'statistics': {...},  # 统计信息
            'html': '...'  # 可选的 HTML 格式
        }
    """
    segmenter = BilingualSegmenter()
    doc = segmenter.segment(original_content, translated_content)

    return {
        'blocks': [b.to_dict() for b in doc.blocks],
        'statistics': doc.statistics,
        'html': doc.get_html_hover_format()
    }