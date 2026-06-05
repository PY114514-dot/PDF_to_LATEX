"""通用文档解析器：优先文本层，必要时回退到 OCR。"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple


def _safe_re_sub(pattern: str, replacement: str, text: str) -> str:
    """
    安全地执行 re.sub，捕获无效正则表达式错误。
    如果正则表达式编译失败，返回原文不变。
    """
    try:
        compiled = re.compile(pattern)
        return compiled.sub(replacement, text)
    except re.error:
        # 如果正则表达式无效，返回原文
        return text

import PyPDF2
import pdfplumber
from PIL import Image

from ocr_client import ocr_client


@dataclass
class _ImageRegion:
    bbox: Tuple[float, float, float, float]
    area: float
    source: str


@dataclass
class ChapterBoundary:
    """PDF章节边界信息"""
    page_num: int           # 起始页 (0-indexed)
    title: str              # 章节标题文本
    level: int              # 1=Chapter, 2=Section, 3=Subsection
    font_size: float        # 标题字号
    char_count: int         # 标题字符数


@dataclass
class PageFeatures:
    """单页特征 - 用于困难页判定"""
    page_num: int
    formula_density: float      # 公式密度 0-1
    table_density: float        # 表格密度 0-1
    image_density: float        # 图像密度 0-1
    is_difficult: bool          # 任一密度超阈值


class PDFDocumentParser:
    """PDF 文档解析：文本层优先，扫描页和图片区域走 OCR。"""

    def __init__(
        self,
        quality_fn: Optional[Callable[[str], float]] = None,
        progress_callback: Optional[Callable[..., None]] = None,
        ocr_provider: Optional[str] = None,
        render_resolution: int = 220,
    ):
        self.quality_fn = quality_fn or self._default_quality
        self.progress_callback = progress_callback
        self.ocr_provider = ocr_provider
        self.render_resolution = render_resolution
        self.table_settings = {
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
        }

    def _emit_progress(
        self,
        status: str,
        current: int,
        total: int,
        message: str,
        log_type: str = 'info',
        log_message: Optional[str] = None,
    ):
        if self.progress_callback:
            self.progress_callback(status, current, total, message, log_type, log_message)

    def _default_quality(self, text: str) -> float:
        if not text or len(text.strip()) < 10:
            return 0.0

        readable_chars = sum(1 for c in text if c.isalnum() or c.isspace() or c in '.,;:!?-()[]{}')
        total_chars = len(text)
        if total_chars == 0:
            return 0.0

        readable_ratio = readable_chars / total_chars
        weird_chars = sum(1 for c in text if ord(c) > 1000 and not ('\u4e00' <= c <= '\u9fff'))
        weird_ratio = weird_chars / total_chars
        return max(0.0, min(1.0, readable_ratio - (weird_ratio * 2)))

    def _normalize_text(self, text: str, layout_hint: str = 'text') -> str:
        raw = (text or '').replace('\r\n', '\n').replace('\r', '\n')
        lines = raw.split('\n')
        if layout_hint in {'table', 'code'}:
            cleaned = [line.rstrip() for line in lines]
            return '\n'.join(cleaned).strip('\n')
        cleaned = [line.strip() for line in lines]
        return '\n'.join(cleaned).strip()

    def _fix_math_extraction(self, text: str) -> str:
        """
        修复 PDF 文本提取时丢失的数学符号。

        PDF 文本层对矩阵转置的上标 T 处理很差：
        - W^T (上标) → W.T, W T, W•T
        - A^T B → A.T B, A T B
        - X_i^T → X_i.T, X_i T

        这个修复在将文本送给 AI 之前应用，确保 AI 能正确理解数学表达式。
        """
        if not text:
            return text

        try:
            # 模式1: W.T, A.T, X_i.T → W^{T}, A^{T}, X_i^{T}
            text = re.sub(
                r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\.([T])',
                r'\1^{\mathsf{T}}',
                text
            )

            # 模式2: W T, A T (空格表示的转置，在数学上下文中)
            # 只匹配 T 后面不是字母的情况
            text = re.sub(
                r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\s+([T])(?![a-zA-Z{])',
                r'\1^{\mathsf{T}}',
                text
            )

            # 模式3: 修复类似 W.t 的情况（小写 t 有时也表示转置）
            text = re.sub(
                r'([A-Z])\.t\b',
                r'\1^{\mathsf{T}}',
                text
            )

            # 模式4: 修复 ^2, ^3 等上标数字缺失大括号
            text = re.sub(
                r'(\w)\^(\d+)(?![}a-zA-Z])',
                r'\1^{\2}',
                text
            )

            # 模式5: W\top → W^{\top} (有时 PDF 或 OCR 会产生这个)
            text = re.sub(
                r'(\w)\s*\\top\b',
                r'\1^{\\top}',
                text
            )

            # 模式6: 保留 \tag{xxx} 命令，转换为可渲染格式（在公式后面显示编号）
            # \tag{1.15} -> \qquad (1.15)
            text = re.sub(r'\\tag\{([^}]*)\}', r'\\qquad (\\1)', text)
        except re.error as e:
            # 如果正则表达式错误（如 bad escape），返回原文
            print(f"[WARNING] _fix_math_extraction failed: {e}")
            return text

        return text

    def _cleanup_pagination(self, text: str, page_num: int, total_pages: int) -> str:
        raw = text or ''
        if not raw.strip():
            return ''

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

        return '\n'.join(lines[i] for i in range(len(lines)) if keep[i]).strip()

    def _is_pagination_line(self, line: str, page_num: int, total_pages: int) -> bool:
        s = (line or '').strip()
        if not s:
            return False

        current_page = page_num + 1
        if re.fullmatch(r'\d{1,4}', s):
            value = int(s)
            if value == current_page or (total_pages > 0 and value == total_pages):
                return True

        frac = re.fullmatch(r'(\d{1,4})\s*/\s*(\d{1,4})', s)
        if frac:
            left = int(frac.group(1))
            right = int(frac.group(2))
            if left == current_page and (total_pages <= 0 or right == total_pages):
                return True

        cn_page = re.fullmatch(
            r'第\s*\d{1,4}(?:\s*/\s*\d{1,4})?\s*页(?:\s*/\s*共?\s*\d{1,4}\s*页)?',
            s,
            flags=re.IGNORECASE,
        )
        if cn_page:
            return True

        en_page = re.fullmatch(
            r'(?:page|p\.)\s*\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?',
            s,
            flags=re.IGNORECASE,
        )
        if en_page:
            return True

        # 删除运行标题模式（如 "1. 不可压缩欧拉方程" 或 "Chapter 1 Introduction"）
        # 这些通常在页面的顶部或底部，作为章节导航
        # 关键：只匹配单独出现的简短标题，不匹配包含句子内容的行
        running_header_patterns = [
            r'^\d{1,2}\.\s*[一-鿿]{2,10}$',           # 数字. 中文标题 (如 "1. 不可压缩欧拉方程")，后面不能有更多内容
            r'^第\s*\d+\s*章\s*[一-鿿]{2,10}$',       # 第X章 + 简短标题
            r'^[一-鿿]{2,8}\s+\d+\.\d+(?:\s+[一-鿿]+)?$',  # 简短中文词 + 数字.数字 (如 "欧拉方程 1.3")
            r'^\s*\d+\s+\d+\.\s*[一-鿿]',  # 页码 + 空格 + 章节号 + 标题 (如 "6    1. 不可压缩欧拉方程")
        ]
        for pattern in running_header_patterns:
            if re.match(pattern, s, re.IGNORECASE):
                return True

        return False

    def _clean_table_cell(self, cell: Optional[str]) -> str:
        if cell is None:
            return '<EMPTY>'
        cleaned = str(cell).replace('\n', ' ').strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned if cleaned else '<EMPTY>'

    def _format_tables_for_prompt(self, tables: List[List[List[Optional[str]]]]) -> str:
        blocks: List[str] = []

        for t_idx, table in enumerate(tables, start=1):
            rows = table or []
            valid_rows = [row for row in rows if isinstance(row, list)]
            if not valid_rows:
                continue

            max_cols = max((len(row) for row in valid_rows), default=0)
            if max_cols == 0:
                continue

            lines = [f'[TABLE {t_idx}] cols={max_cols}']
            for r_idx, row in enumerate(valid_rows, start=1):
                normalized = [self._clean_table_cell(cell) for cell in row]
                if len(normalized) < max_cols:
                    normalized.extend(['<EMPTY>'] * (max_cols - len(normalized)))
                lines.append(f'ROW {r_idx}: ' + ' | '.join(normalized[:max_cols]))

            blocks.append('\n'.join(lines))

        return '\n\n'.join(blocks).strip()

    def _extract_table_regions(self, page: pdfplumber.page.Page) -> Tuple[str, List[Tuple[float, float, float, float]]]:
        try:
            tables = page.extract_tables(table_settings=self.table_settings) or []
        except Exception:
            tables = []

        try:
            table_objects = page.find_tables(table_settings=self.table_settings) or []
            table_bboxes = [tuple(table.bbox) for table in table_objects if getattr(table, 'bbox', None)]
        except Exception:
            table_bboxes = []

        return self._format_tables_for_prompt(tables), table_bboxes

    def _extract_page_text_layer(self, page: pdfplumber.page.Page) -> str:
        try:
            text = page.extract_text(layout=True)
        except Exception:
            try:
                text = page.extract_text()
            except Exception:
                text = ''
        return self._normalize_text(text or '')

    def _render_page_image(self, page: pdfplumber.page.Page) -> Optional[Image.Image]:
        try:
            page_image = page.to_image(resolution=self.render_resolution)
            pil_image = getattr(page_image, 'original', None)
            if pil_image is not None:
                return pil_image.convert('RGB')
        except Exception:
            return None
        return None

    def _stream_to_pil(self, stream_obj) -> Optional[Image.Image]:
        if stream_obj is None:
            return None

        try:
            data = stream_obj.get_data() if hasattr(stream_obj, 'get_data') else None
        except Exception:
            data = None

        if not data:
            return None

        try:
            return Image.open(io.BytesIO(data)).convert('RGB')
        except Exception:
            pass

        width = self._stream_int(stream_obj, '/Width')
        height = self._stream_int(stream_obj, '/Height')
        if not width or not height:
            return None

        mode = 'RGB'
        color_space = self._stream_value(stream_obj, '/ColorSpace')
        color_space_text = str(color_space or '')
        if 'Gray' in color_space_text:
            mode = 'L'
        elif 'CMYK' in color_space_text:
            mode = 'CMYK'

        try:
            return Image.frombytes(mode, (width, height), data).convert('RGB')
        except Exception:
            return None

    def _stream_int(self, stream_obj, key: str) -> int:
        try:
            value = stream_obj.get(key) if hasattr(stream_obj, 'get') else None
            return int(value) if value is not None else 0
        except Exception:
            return 0

    def _stream_value(self, stream_obj, key: str):
        try:
            if hasattr(stream_obj, 'get'):
                return stream_obj.get(key)
        except Exception:
            return None
        return None

    def _extract_embedded_images_from_plumber(self, page: pdfplumber.page.Page) -> List[_ImageRegion]:
        regions: List[_ImageRegion] = []
        for image in getattr(page, 'images', []) or []:
            stream = image.get('stream')
            pil_image = self._stream_to_pil(stream)
            if pil_image is None:
                continue
            x0 = float(image.get('x0', 0) or 0)
            y0 = float(image.get('y0', 0) or 0)
            x1 = float(image.get('x1', x0 + pil_image.width) or (x0 + pil_image.width))
            y1 = float(image.get('y1', y0 + pil_image.height) or (y0 + pil_image.height))
            bbox = (x0, y0, x1, y1)
            area = abs((x1 - x0) * (y1 - y0))
            regions.append(_ImageRegion(bbox=bbox, area=area, source='plumber'))
        return regions

    def _extract_embedded_images_from_pypdf(self, pypdf_page) -> List[_ImageRegion]:
        regions: List[_ImageRegion] = []
        try:
            resources = pypdf_page.get('/Resources')
            if not resources:
                return regions
            xobject = resources.get('/XObject')
            if not xobject:
                return regions
            xobject = xobject.get_object()
            for name in xobject:
                obj = xobject[name]
                try:
                    obj = obj.get_object()
                except Exception:
                    pass
                if obj.get('/Subtype') != '/Image':
                    continue
                pil_image = self._stream_to_pil(obj)
                if pil_image is None:
                    continue
                width = self._stream_int(obj, '/Width') or pil_image.width
                height = self._stream_int(obj, '/Height') or pil_image.height
                area = float(width * height)
                regions.append(_ImageRegion(bbox=(0.0, 0.0, float(width), float(height)), area=area, source='pypdf'))
        except Exception:
            return regions
        return regions

    def _extract_primary_pypdf_image(self, pypdf_page) -> Optional[Image.Image]:
        """从 PyPDF2 的 XObject 中取出面积最大的图片。"""
        best_image: Optional[Image.Image] = None
        best_area = 0.0
        try:
            resources = pypdf_page.get('/Resources')
            if not resources:
                return None
            xobject = resources.get('/XObject')
            if not xobject:
                return None
            xobject = xobject.get_object()
            for name in xobject:
                obj = xobject[name]
                try:
                    obj = obj.get_object()
                except Exception:
                    pass
                if obj.get('/Subtype') != '/Image':
                    continue
                pil_image = self._stream_to_pil(obj)
                if pil_image is None:
                    continue
                width = self._stream_int(obj, '/Width') or pil_image.width
                height = self._stream_int(obj, '/Height') or pil_image.height
                area = float(width * height)
                if area > best_area:
                    best_area = area
                    best_image = pil_image
        except Exception:
            return best_image
        return best_image

    def _extract_best_image(self, page: pdfplumber.page.Page, pypdf_page) -> Optional[Image.Image]:
        plumber_images = self._extract_embedded_images_from_plumber(page)
        pypdf_images = self._extract_embedded_images_from_pypdf(pypdf_page)
        candidates = plumber_images + pypdf_images
        if not candidates:
            return self._render_page_image(page)

        best = max(candidates, key=lambda item: item.area)
        if best.source == 'plumber':
            for image in getattr(page, 'images', []) or []:
                x0 = float(image.get('x0', 0) or 0)
                y0 = float(image.get('y0', 0) or 0)
                x1 = float(image.get('x1', 0) or 0)
                y1 = float(image.get('y1', 0) or 0)
                if abs(x0 - best.bbox[0]) < 1 and abs(y0 - best.bbox[1]) < 1 and abs(x1 - best.bbox[2]) < 1 and abs(y1 - best.bbox[3]) < 1:
                    pil_image = self._stream_to_pil(image.get('stream'))
                    if pil_image is not None:
                        return pil_image

        if best.source == 'pypdf':
            pypdf_image = self._extract_primary_pypdf_image(pypdf_page)
            if pypdf_image is not None:
                return pypdf_image

        return self._render_page_image(page)

    def _crop_page_image(self, image: Image.Image, bbox: Tuple[float, float, float, float], page_height: float) -> Image.Image:
        x0, y0, x1, y1 = bbox
        left = max(0, int(round(x0)))
        top = max(0, int(round(page_height - y1)))
        right = min(image.width, int(round(x1)))
        bottom = min(image.height, int(round(page_height - y0)))
        return image.crop((left, top, right, bottom))

    def _guess_layout_hint(self, text: str, table_bboxes: List[Tuple[float, float, float, float]], image_regions: List[_ImageRegion]) -> str:
        if table_bboxes:
            return 'table'

        text = text or ''
        if re.search(r'\b(def|class|import|from|return|if|else|for|while|switch|case|function|public|private|printf|std::|cout)\b', text, flags=re.IGNORECASE):
            return 'code'
        if re.search(r'[{};<>]{2,}', text):
            return 'code'

        if image_regions:
            best = max(image_regions, key=lambda item: item.area)
            width = best.bbox[2] - best.bbox[0]
            height = best.bbox[3] - best.bbox[1]
            if height > 0 and width / height > 1.35:
                return 'code'

        return 'text'

    def _detect_two_column_layout(self, page: pdfplumber.page.Page, page_width: float) -> bool:
        """
        检测页面是否为双栏布局。
        通过分析文字块的 x 坐标分布，判断是否存在两个明显的文本列。
        """
        try:
            chars = page.chars
            if not chars:
                return False

            # 收集所有文字块的 x0（左边缘）坐标
            x_coords = [c['x0'] for c in chars if c.get('x0') is not None]

            if len(x_coords) < 20:
                return False

            # 计算中位数 x 坐标
            sorted_x = sorted(x_coords)
            mid = len(sorted_x) // 2
            median_x = sorted_x[mid]

            # 双栏布局时，文字会集中在左右两侧（中间有较大空白）
            # 左栏文字的 x0 应该在页面宽度的 5%~45% 之间
            # 右栏文字的 x0 应该在页面宽度的 55%~95% 之间
            left_threshold = page_width * 0.45
            right_threshold = page_width * 0.55

            left_chars = sum(1 for x in x_coords if x < left_threshold)
            right_chars = sum(1 for x in x_coords if x > right_threshold)

            total_chars = len(x_coords)
            left_ratio = left_chars / total_chars
            right_ratio = right_chars / total_chars

            # 如果左右两栏各有 > 20% 的文字，认为是双栏布局
            if left_ratio > 0.2 and right_ratio > 0.2:
                # 额外检查：中间区域（35%~65%）的文字应该很少
                mid_chars = sum(1 for x in x_coords if left_threshold <= x <= right_threshold)
                mid_ratio = mid_chars / total_chars
                if mid_ratio < 0.15:
                    return True

            return False
        except Exception:
            return False

    def _should_use_ocr(self, text: str, quality: float, image_regions: List[_ImageRegion], table_bboxes: List[Tuple[float, float, float, float]]) -> bool:
        if not text.strip():
            return True
        # 有表格结构但文本层缺少换行符（表格内容可能为图片格式嵌入），强制 OCR
        if table_bboxes and '\n' not in text and quality < 0.5:
            return True
        if quality < 0.28 and (image_regions or table_bboxes):
            return True
        if quality < 0.18:
            return True
        return False

    async def _ocr_image(self, image: Image.Image, layout_hint: str) -> Tuple[str, float]:
        result = await ocr_client.recognize(
            image,
            force_provider=self.ocr_provider if self.ocr_provider and self.ocr_provider != 'mixed' else None,
            layout_hint=layout_hint,
        )
        return result.get('text', '').strip(), float(result.get('quality', 0.0) or 0.0)

    def _run_ocr(self, image: Image.Image, layout_hint: str) -> Tuple[str, float]:
        return asyncio.run(self._ocr_image(image, layout_hint))

    def _merge_text(self, primary: str, secondary: str) -> str:
        primary = (primary or '').strip()
        secondary = (secondary or '').strip()
        if not primary:
            return secondary
        if not secondary:
            return primary
        if secondary in primary:
            return primary
        return f"{primary}\n\n[OCR补充]\n{secondary}"

    # ==================== v0.9 章节检测与困难页分类 ====================

    def detect_chapter_boundaries(self, pdf_path: str) -> List[ChapterBoundary]:
        """
        检测PDF的章节边界。

        算法:
        1. 用pdfplumber读取每页所有chars
        2. 按y坐标聚类成行
        3. 计算每页的「正文基线字号」= 中位数
        4. 字号 > 基线*1.25 且 < 基线*3.0 的行 → 候选标题
        5. 正则二次确认（中英文）
        6. 过滤过短（<2字）和过长（>80字）的标题

        Returns:
            按页码排序的 ChapterBoundary 列表
        """
        boundaries: List[ChapterBoundary] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    chars = page.chars
                    if not chars or len(chars) < 10:
                        continue

                    # 1. 计算每行字号（按y坐标聚类）
                    lines = self._group_chars_into_lines(chars)
                    if not lines:
                        continue

                    # 2. 找正文基线字号（页面字号中位数）
                    sizes = [ln['size'] for ln in lines if ln['size'] > 0]
                    if not sizes:
                        continue
                    sorted_sizes = sorted(sizes)
                    median_size = sorted_sizes[len(sorted_sizes) // 2]
                    if median_size <= 0:
                        continue

                    # 3. 找候选标题行：字号 > 基线*1.25 且 < 基线*3.0
                    for line in lines:
                        if not (median_size * 1.25 < line['size'] < median_size * 3.0):
                            continue
                        text = line['text'].strip()
                        if not text or len(text) < 2 or len(text) > 80:
                            continue
                        # 跳过纯数字（页码/章节编号后面没标题的）
                        if not any(c.isalpha() or '一' <= c <= '鿿' for c in text):
                            continue
                        # 正则二次确认
                        if not self._looks_like_heading(text):
                            continue
                        # 过滤页眉/页脚区域（前5%或后5%）
                        page_height = page.height or 792
                        if line['y0'] < page_height * 0.05 or line['y0'] > page_height * 0.95:
                            continue
                        # 判断标题级别
                        level = self._classify_heading_level(text, line['size'], median_size)
                        boundaries.append(ChapterBoundary(
                            page_num=page_idx,
                            title=text,
                            level=level,
                            font_size=round(line['size'], 2),
                            char_count=len(text),
                        ))
        except Exception as exc:
            # 任何异常都返回空列表，调用方回退到4-页块
            print(f"[章节检测] 失败: {exc}")
            return []

        # 去重：相邻页出现相同标题 → 保留字号更大的
        deduped: List[ChapterBoundary] = []
        for b in boundaries:
            if deduped and deduped[-1].title == b.title and abs(deduped[-1].page_num - b.page_num) <= 1:
                if b.font_size > deduped[-1].font_size:
                    deduped[-1] = b
                continue
            deduped.append(b)
        return deduped

    def _group_chars_into_lines(self, chars: List[dict]) -> List[dict]:
        """把chars按y坐标聚类成行，返回 [{text, size, y0, x0}, ...]"""
        if not chars:
            return []
        # 按top(y0)排序
        sorted_chars = sorted(chars, key=lambda c: (c.get('top', c.get('y0', 0)), c.get('x0', 0)))
        lines: List[dict] = []
        current: List[dict] = []
        current_y = None
        y_tolerance = 3.0
        for c in sorted_chars:
            y = c.get('top', c.get('y0', 0))
            if current_y is None or abs(y - current_y) <= y_tolerance:
                current.append(c)
                current_y = y if current_y is None else (current_y + y) / 2
            else:
                if current:
                    lines.append(self._chars_to_line_dict(current))
                current = [c]
                current_y = y
        if current:
            lines.append(self._chars_to_line_dict(current))
        return lines

    def _chars_to_line_dict(self, chars: List[dict]) -> dict:
        """一行chars → {text, size, y0, x0}"""
        text = ''.join(c.get('text', '') for c in chars).strip()
        sizes = [c.get('size', 0) for c in chars if c.get('size', 0) > 0]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        y0 = min((c.get('top', c.get('y0', 0)) for c in chars), default=0)
        x0 = min((c.get('x0', 0) for c in chars), default=0)
        return {'text': text, 'size': avg_size, 'y0': y0, 'x0': x0}

    def _looks_like_heading(self, text: str) -> bool:
        """正则确认是否像标题（中英文）"""
        patterns = [
            # 英文: Chapter N, Section N, N. Title, N.M Title, Abstract, References
            r'^(Chapter|CHAPTER|Section|SECTION|Part|PART)\s+[\dIVX]+',
            r'^(Abstract|ABSTRACT|Introduction|INTRODUCTION|Conclusion|CONCLUSION|References|REFERENCES|Bibliography|Acknowledgement|Appendix)\b',
            r'^\d+(\.\d+){0,3}\.?\s+[A-Z][\w\s\-:,\(\)]{2,60}$',
            r'^\d+\.\s+[A-Z][a-zA-Z]+',
            # 中文: 第X章/节, 摘要, 结论, 参考文献
            r'^第\s*[一二三四五六七八九十\d]+\s*[章节]\s*[一-鿿]',
            r'^(摘要|Abstract|引言|前言|背景|相关工作|方法|实验|结果|讨论|结论|总结|参考文献|致谢|附录)\b',
        ]
        for p in patterns:
            if re.match(p, text):
                return True
        return False

    def _classify_heading_level(self, text: str, font_size: float, median_size: float) -> int:
        """根据字号和文本模式判断标题级别"""
        ratio = font_size / median_size if median_size > 0 else 1.0
        # 字号 > 2x 基线 → Chapter (level 1)
        if ratio > 2.0:
            return 1
        # 含 Chapter/第X章 → level 1
        if re.match(r'^(Chapter|CHAPTER|第\s*[一二三四五六七八九十\d]+\s*章)', text):
            return 1
        # 含 Section/第X节 → level 2
        if re.match(r'^(Section|SECTION|第\s*[一二三四五六七八九十\d]+\s*节)', text):
            return 2
        # 数字编号 N.M(.K) → 推测 level (深度 = 点数+1)
        m = re.match(r'^(\d+)(\.\d+)+', text)
        if m:
            depth = m.group(0).count('.') + 1
            return min(3, depth)
        # 纯 N. → level 2
        if re.match(r'^\d+\.', text):
            return 2
        # 中等字号 → level 2
        if ratio > 1.6:
            return 1
        return 2

    def classify_difficult_pages(self, pdf_path: str) -> List[PageFeatures]:
        """
        分类每页难度：公式密度/表格密度/图像密度。

        Returns:
            PageFeatures 列表
        """
        results: List[PageFeatures] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ''
                    # 公式密度
                    formula_lines = self._count_formula_lines(text)
                    total_lines = max(1, len([l for l in text.split('\n') if l.strip()]))
                    formula_density = formula_lines / total_lines
                    # 表格密度（多列结构：同行含多个 ≥2 空格的序列）
                    table_lines = sum(1 for l in text.split('\n') if re.search(r'\S\s{2,}\S\s{2,}\S', l))
                    table_density = table_lines / total_lines
                    # 图像密度
                    image_area = sum(
                        (img.get('x1', 0) - img.get('x0', 0)) * (img.get('bottom', img.get('y1', 0)) - img.get('top', img.get('y0', 0)))
                        for img in page.images
                    )
                    page_area = (page.width or 612) * (page.height or 792)
                    image_density = image_area / page_area if page_area > 0 else 0.0
                    # 判定困难
                    is_difficult = (
                        formula_density > 0.30
                        or table_density > 0.20
                        or image_density > 0.15
                    )
                    results.append(PageFeatures(
                        page_num=page_idx,
                        formula_density=round(formula_density, 3),
                        table_density=round(table_density, 3),
                        image_density=round(image_density, 3),
                        is_difficult=is_difficult,
                    ))
        except Exception as exc:
            print(f"[困难页分类] 失败: {exc}")
            return []
        return results

    def _count_formula_lines(self, text: str) -> int:
        """统计含数学公式的行数"""
        if not text:
            return 0
        formula_patterns = [
            r'\$[^$]+\$',                # $...$
            r'\\\([^)]+\\\)',            # \(...\)
            r'\\\[[^\]]+\\\]',           # \[...\]
            r'\\begin\{equation',        # \begin{equation}
            r'\\begin\{align',           # \begin{align}
            r'\\frac\b',                 # \frac
            r'\\sum\b|\\int\b|\\prod\b',  # 求和/积分/乘积
            r'\\partial\b|\\nabla\b',    # 偏导/梯度
            r'\\alpha|\\beta|\\gamma|\\theta|\\lambda|\\mu|\\sigma|\\omega',
            r'\^[_a-zA-Z0-9\{\(]',        # 上标
            r'[_a-zA-Z0-9\}]\^',         # 上标（在前）
        ]
        count = 0
        for line in text.split('\n'):
            if not line.strip():
                continue
            for p in formula_patterns:
                if re.search(p, line):
                    count += 1
                    break
        return count

    def extract_text_from_pdf(self, pdf_path: str, pages: Optional[List[int]] = None) -> List[str]:
        """提取 PDF 的每页文本，优先文本层，必要时 OCR 兜底。"""
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f'PDF文件不存在: {pdf_path}')

        print(f"\n[PDF提取] 开始提取文件: {pdf_path}")
        try:
            with pdfplumber.open(pdf_path) as pdf, open(pdf_path, 'rb') as pdf_handle:
                reader = PyPDF2.PdfReader(pdf_handle)
                total_pages = len(pdf.pages)
                if pages is None:
                    pages_to_extract = list(range(total_pages))
                else:
                    pages_to_extract = [p for p in pages if 0 <= p < total_pages]

                pages_text = [''] * total_pages
                self._emit_progress(
                    'extracting',
                    0,
                    len(pages_to_extract),
                    '正在使用增强解析器提取PDF文本...',
                    'info',
                    '📄 开始解析PDF文本层、表格和OCR回退',
                )

                for idx, page_num in enumerate(pages_to_extract):
                    page = pdf.pages[page_num]
                    pypdf_page = reader.pages[page_num]

                    text_layer = self._extract_page_text_layer(page)
                    table_context, table_bboxes = self._extract_table_regions(page)
                    image_regions = [
                        _ImageRegion(
                            bbox=(
                                float(img.get('x0', 0) or 0),
                                float(img.get('y0', 0) or 0),
                                float(img.get('x1', 0) or 0),
                                float(img.get('y1', 0) or 0),
                            ),
                            area=abs(float(img.get('width', 0) or 0) * float(img.get('height', 0) or 0)),
                            source='page-image',
                        )
                        for img in (getattr(page, 'images', []) or [])
                    ]
                    quality = self.quality_fn(text_layer)

                    # 检测双栏布局
                    try:
                        page_width = page.width if hasattr(page, 'width') else 0
                        is_two_column = self._detect_two_column_layout(page, page_width) if page_width > 0 else False
                        if is_two_column:
                            print(f"[PDF提取] 第 {page_num + 1} 页: 检测到双栏布局")
                    except Exception:
                        is_two_column = False

                    print(f"[PDF提取] 第 {page_num + 1}/{total_pages} 页 - 文本层长度: {len(text_layer)}, 质量: {quality:.2f}")

                    extracted_text = text_layer
                    ocr_used = False

                    if self._should_use_ocr(text_layer, quality, image_regions, table_bboxes):
                        page_image = self._render_page_image(page)
                        if page_image is None:
                            page_image = self._extract_best_image(page, pypdf_page)

                        if page_image is not None:
                            layout_hint = self._guess_layout_hint(text_layer, table_bboxes, image_regions)

                            if table_bboxes:
                                table_texts: List[str] = []
                                for t_idx, bbox in enumerate(table_bboxes[:8], start=1):
                                    try:
                                        crop = self._crop_page_image(page_image, bbox, getattr(page, 'height', page_image.height))
                                        ocr_text, ocr_quality = self._run_ocr(crop, 'table')
                                        if ocr_text:
                                            table_texts.append(f'[OCR_TABLE {t_idx}]\n{ocr_text}')
                                        print(f"[PDF提取] 第 {page_num + 1} 页表格区域 {t_idx} OCR 质量: {ocr_quality:.2f}")
                                    except Exception as crop_err:
                                        print(f"[PDF提取] 第 {page_num + 1} 页表格区域 OCR 失败: {crop_err}")

                                if table_texts:
                                    ocr_text = '\n\n'.join(table_texts)
                                else:
                                    ocr_text, _ = self._run_ocr(page_image, layout_hint)
                            else:
                                ocr_text, ocr_quality = self._run_ocr(page_image, layout_hint)
                                print(f"[PDF提取] 第 {page_num + 1} 页 OCR 质量: {ocr_quality:.2f}, 模式: {layout_hint}")

                            ocr_text = self._normalize_text(ocr_text, layout_hint=layout_hint)
                            if ocr_text:
                                if not extracted_text.strip() or self.quality_fn(ocr_text) >= quality:
                                    extracted_text = ocr_text
                                    ocr_used = True
                                else:
                                    extracted_text = self._merge_text(extracted_text, ocr_text)
                                    ocr_used = True

                    if table_context:
                        if extracted_text.strip():
                            extracted_text = f"{extracted_text}\n\n[STRUCTURED_TABLE_CONTEXT]\n{table_context}"
                        else:
                            extracted_text = f"[STRUCTURED_TABLE_CONTEXT]\n{table_context}"

                    # 双栏布局提示
                    if is_two_column:
                        extracted_text = f"[TWO_COLUMN_PAGE]\n{extracted_text}"

                    extracted_text = self._cleanup_pagination(extracted_text, page_num, total_pages)
                    extracted_text = self._normalize_text(extracted_text)

                    # 修复 PDF 提取时丢失的数学符号
                    extracted_text = self._fix_math_extraction(extracted_text)

                    if not extracted_text.strip():
                        try:
                            backup_text = pypdf_page.extract_text() or ''
                            backup_text = self._cleanup_pagination(backup_text, page_num, total_pages)
                            extracted_text = self._normalize_text(backup_text)
                        except Exception:
                            extracted_text = ''

                    page_quality = self.quality_fn(extracted_text)
                    source_label = 'OCR' if ocr_used else 'text-layer'
                    print(f"[PDF提取] 第 {page_num + 1}/{total_pages} 页完成 - 来源: {source_label}, 长度: {len(extracted_text)}, 质量: {page_quality:.2f}")

                    pages_text[page_num] = extracted_text
                    self._emit_progress(
                        'extracting',
                        idx + 1,
                        len(pages_to_extract),
                        f'已解析 {idx + 1}/{len(pages_to_extract)} 页',
                        'success',
                        f'✓ 第 {page_num + 1} 页解析完成 (来源: {source_label}, 质量: {page_quality:.0%})',
                    )

                print(f"[PDF提取] 完成！共解析 {len(pages_to_extract)}/{total_pages} 页")
        except Exception as exc:
            raise Exception(f"PDF解析失败: {exc}")

        return pages_text