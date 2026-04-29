#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF智能分析模块
提供自动页码选择、模型推荐、内容类型检测功能
"""

import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

import pdfplumber
import PyPDF2

from document_parser import PDFDocumentParser


@dataclass
class PageAnalysis:
    """单页分析结果"""
    page_num: int
    has_text: bool
    has_tables: bool
    has_images: bool
    text_length: int
    quality: float
    is_content: bool
    content_type: str  # 'text', 'table', 'image', 'mixed', 'non_content'


class PDFIntelligence:
    """
    PDF智能分析器
    自动检测有效内容页，推荐转换模型和页码范围
    """

    def __init__(self, parser: Optional[PDFDocumentParser] = None):
        self.parser = parser or PDFDocumentParser()

    def analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        全面分析PDF结构和内容

        Returns:
            {
                'total_pages': int,
                'pages': List[PageAnalysis],
                'stats': {...},
                'recommendations': {...}
            }
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f'PDF文件不存在: {pdf_path}')

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)

        with open(pdf_path, 'rb') as pdf_handle:
            reader = PyPDF2.PdfReader(pdf_handle)
            total_pages = len(reader.pages)

        pages_analysis: List[PageAnalysis] = []
        stats = {
            'text_pages': 0,
            'table_pages': 0,
            'image_pages': 0,
            'mixed_pages': 0,
            'non_content_pages': 0,
            'low_quality_pages': 0,
            'chinese_pages': 0,
            'english_pages': 0,
        }

        for page_num in range(total_pages):
            page_analysis = self._analyze_single_page(pdf_path, page_num)
            pages_analysis.append(page_analysis)

            pt = page_analysis.content_type
            if pt == 'text':
                stats['text_pages'] += 1
            elif pt == 'table':
                stats['table_pages'] += 1
            elif pt == 'image':
                stats['image_pages'] += 1
            elif pt == 'mixed':
                stats['mixed_pages'] += 1
            elif pt == 'non_content':
                stats['non_content_pages'] += 1

            if page_analysis.quality < 0.3:
                stats['low_quality_pages'] += 1

            # 语言检测（简单检查）
            if self._contains_chinese(pages_analysis[-1]):
                stats['chinese_pages'] += 1
            else:
                stats['english_pages'] += 1

        recommendations = self._generate_recommendations(stats, total_pages)

        return {
            'total_pages': total_pages,
            'pages': pages_analysis,
            'stats': stats,
            'recommendations': recommendations,
        }

    def _analyze_single_page(self, pdf_path: str, page_num: int) -> PageAnalysis:
        """分析单页内容"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num]
                text_layer = page.extract_text(layout=True) or ''

            quality = self.parser.quality_fn(text_layer)
            text_length = len(text_layer.strip())

            has_text = text_length > 50
            has_tables = len(page.extract_tables() or []) > 0 if has_text else False
            has_images = len(getattr(page, 'images', []) or []) > 0

            is_content = quality > 0.2 or (has_text and text_length > 100)

            # 判断内容类型
            if not is_content:
                content_type = 'non_content'
            elif has_tables and has_text:
                content_type = 'mixed'
            elif has_tables:
                content_type = 'table'
            elif has_images and text_length > 200:
                content_type = 'mixed'
            elif has_images:
                content_type = 'image'
            else:
                content_type = 'text'

            return PageAnalysis(
                page_num=page_num + 1,
                has_text=has_text,
                has_tables=has_tables,
                has_images=has_images,
                text_length=text_length,
                quality=quality,
                is_content=is_content,
                content_type=content_type,
            )
        except Exception as e:
            return PageAnalysis(
                page_num=page_num + 1,
                has_text=False,
                has_tables=False,
                has_images=False,
                text_length=0,
                quality=0.0,
                is_content=False,
                content_type='non_content',
            )

    def _contains_chinese(self, page: PageAnalysis) -> bool:
        """简单检测是否包含中文（基于质量分数和内容判断）"""
        return page.quality > 0.1 and page.text_length > 20

    def _generate_recommendations(self, stats: Dict[str, int], total_pages: int) -> Dict[str, Any]:
        """根据统计信息生成转换建议"""
        recommendations = {
            'suggested_pages': list(range(1, total_pages + 1)),
            'model_hint': 'deepseek-chat',
            'translate': False,
            'quality_threshold': 0.3,
            'skip_pages': [],
            'priority': 'normal',
        }

        content_pages = stats['text_pages'] + stats['table_pages'] + stats['mixed_pages']

        # 如果内容页少于一半，可能有大量非内容页（封面、目录、参考文献）
        if content_pages < total_pages * 0.6:
            recommendations['priority'] = 'selective'
            # 推荐跳过非内容页
            skip_count = total_pages - content_pages
            recommendations['skip_pages'] = list(range(1, skip_count + 1))

        # 低质量页面多，建议使用更高质量的模型
        if stats['low_quality_pages'] > total_pages * 0.3:
            recommendations['model_hint'] = 'deepseek-reasoner'

        # 表格多的文档，建议使用专门的表格处理
        if stats['table_pages'] > total_pages * 0.4:
            recommendations['model_hint'] = 'deepseek-chat'

        # 大量英文内容，建议翻译
        if stats['english_pages'] > total_pages * 0.8:
            recommendations['translate'] = True

        # 大量中文内容，可能不需要翻译
        if stats['chinese_pages'] > total_pages * 0.7:
            recommendations['translate'] = False

        return recommendations

    def get_suggested_pages(self, pdf_path: str) -> List[int]:
        """
        获取建议提取的页面（0-indexed）

        跳过：封面、目录、参考文献、空白页等非内容页
        """
        analysis = self.analyze_pdf(pdf_path)
        suggested = []

        for page in analysis['pages']:
            if page.is_content and page.quality >= 0.2:
                suggested.append(page.page_num)

        # 如果检测失败，返回所有页面
        return suggested if suggested else list(range(1, analysis['total_pages'] + 1))

    def get_model_recommendation(self, pdf_path: str) -> str:
        """获取模型推荐"""
        analysis = self.analyze_pdf(pdf_path)
        return analysis['recommendations']['model_hint']

    def should_translate(self, pdf_path: str) -> bool:
        """判断是否需要翻译"""
        analysis = self.analyze_pdf(pdf_path)
        return analysis['recommendations']['translate']


def quick_analysis(pdf_path: str) -> Dict[str, Any]:
    """
    快速分析PDF，返回建议的页码范围和模型

    Returns:
        {
            'suggested_pages': [1, 2, 3, ...],  # 1-indexed
            'model': 'deepseek-chat',
            'translate': False,
            'total_pages': int,
            'content_pages': int
        }
    """
    intelligence = PDFIntelligence()
    result = intelligence.analyze_pdf(pdf_path)

    return {
        'suggested_pages': result['recommendations']['suggested_pages'],
        'model': result['recommendations']['model_hint'],
        'translate': result['recommendations']['translate'],
        'total_pages': result['total_pages'],
        'content_pages': sum(1 for p in result['pages'] if p.is_content),
        'stats': result['stats'],
    }