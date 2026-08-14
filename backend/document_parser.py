"""PDF document parser with text-layer extraction and OCR fallback."""

from __future__ import annotations

import asyncio
import io
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple


import PyPDF2
import pdfplumber
from PIL import Image

from ocr_client import ocr_client

logger = logging.getLogger(__name__)


@dataclass
class _ImageRegion:
    bbox: Tuple[float, float, float, float]
    area: float
    source: str


@dataclass
class ChapterBoundary:
    """PDF绔犺妭杈圭晫淇℃伅"""
    page_num: int           # 璧峰椤?(0-indexed)
    title: str              # 绔犺妭鏍囬鏂囨湰
    level: int              # 1=Chapter, 2=Section, 3=Subsection
    font_size: float        # 鏍囬瀛楀彿
    char_count: int         # 鏍囬瀛楃鏁?


@dataclass
class PageFeatures:
    """鍗曢〉鐗瑰緛 - 鐢ㄤ簬鍥伴毦椤靛垽瀹?"""
    page_num: int
    formula_density: float      # 鍏紡瀵嗗害 0-1
    table_density: float        # 琛ㄦ牸瀵嗗害 0-1
    image_density: float        # 鍥惧儚瀵嗗害 0-1
    is_difficult: bool          # 浠讳竴瀵嗗害瓒呴槇鍊?

@dataclass
class PageExtraction:
    """鍗曢〉鎻愬彇缁撴灉锛屽吋瀹规棫娴嬭瘯鍜岃繍琛屾爣棰樻娴嬮€昏緫銆?"""
    page_num: int
    text: str
    is_running_header: bool = False


class PDFDocumentParser:
    """PDF 鏂囨。瑙ｆ瀽锛氭枃鏈眰浼樺厛锛屾壂鎻忛〉鍜屽浘鐗囧尯鍩熻蛋 OCR銆?"""

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
        # cid:N 是 PDF 字体缺少 Unicode 映射时留下的占位符，不是正文或公式。
        raw = re.sub(r'\(?cid:\d+\)?', '', raw, flags=re.IGNORECASE)
        lines = raw.split('\n')
        if layout_hint in {'table', 'code'}:
            cleaned = [line.rstrip() for line in lines]
            return '\n'.join(cleaned).strip('\n')
        cleaned = [line.strip() for line in lines]
        return '\n'.join(cleaned).strip()

    def _remove_bottom_small_text(self, page: pdfplumber.page.Page, text: str) -> str:
        """Remove footer-like small text from the bottom margin without touching body text."""
        if not text or not getattr(page, 'chars', None):
            return text

        try:
            chars = [char for char in page.chars if (char.get('text') or '').strip()]
            sizes = sorted(float(char.get('size', 0) or 0) for char in chars if char.get('size'))
            if len(sizes) < 10:
                return text
            median_size = sizes[len(sizes) // 2]
            if median_size <= 0:
                return text

            page_height = float(page.height or 0)
            small_limit = median_size * 0.78
            line_groups = {}
            for char in chars:
                top = float(char.get('top', 0) or 0)
                size = float(char.get('size', median_size) or median_size)
                if top < page_height * 0.84 or size > small_limit:
                    continue
                key = round(top / 2.0) * 2.0
                line_groups.setdefault(key, []).append(char)

            candidates = []
            for line_chars in line_groups.values():
                line_chars.sort(key=lambda char: float(char.get('x0', 0) or 0))
                candidate = ''.join(char.get('text', '') for char in line_chars).strip()
                normalized = re.sub(r'\s+', '', candidate).lower()
                if len(normalized) >= 3:
                    candidates.append(normalized)

            if not candidates:
                return text

            kept_lines = []
            for line in text.splitlines():
                normalized = re.sub(r'\s+', '', line).lower()
                if normalized and any(candidate in normalized for candidate in candidates):
                    continue
                kept_lines.append(line)
            return '\n'.join(kept_lines).strip()
        except Exception:
            return text

    def _fix_math_extraction(self, text: str) -> str:
        """
        淇 PDF 鏂囨湰鎻愬彇鏃朵涪澶辩殑鏁板绗﹀彿銆?

        PDF 鏂囨湰灞傚鐭╅樀杞疆鐨勪笂鏍?T 澶勭悊寰堝樊锛?
        - W^T (涓婃爣) 鈫?W.T, W T, W鈥
        - A^T B 鈫?A.T B, A T B
        - X_i^T 鈫?X_i.T, X_i T

        杩欎釜淇鍦ㄥ皢鏂囨湰閫佺粰 AI 涔嬪墠搴旂敤锛岀‘淇?AI 鑳芥纭悊瑙ｆ暟瀛﹁〃杈惧紡銆?
        """
        if not text:
            return text

        try:
            # 妯″紡1: W.T, A.T, X_i.T 鈫?W^{T}, A^{T}, X_i^{T}
            text = re.sub(
                r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\.([T])',
                r'\1^{\\mathsf{T}}',
                text
            )

            # 妯″紡2: W T, A T (绌烘牸琛ㄧず鐨勮浆缃紝鍦ㄦ暟瀛︿笂涓嬫枃涓?
            # 鍙尮閰?T 鍚庨潰涓嶆槸瀛楁瘝鐨勬儏鍐?
            text = re.sub(
                r'([A-Za-z](?:_[a-zA-Z0-9]+)?)\s+([T])(?![a-zA-Z{])',
                r'\1^{\\mathsf{T}}',
                text
            )

            # 妯″紡3: 淇绫讳技 W.t 鐨勬儏鍐碉紙灏忓啓 t 鏈夋椂涔熻〃绀鸿浆缃級
            text = re.sub(
                r'([A-Z])\.t\b',
                r'\1^{\\mathsf{T}}',
                text
            )

            # 妯″紡4: 淇 ^2, ^3 绛変笂鏍囨暟瀛楃己澶卞ぇ鎷彿
            text = re.sub(
                r'(\w)\^(\d+)(?![}a-zA-Z])',
                r'\1^{\2}',
                text
            )

            # 妯″紡5: W\top 鈫?W^{\top} (鏈夋椂 PDF 鎴?OCR 浼氫骇鐢熻繖涓?
            text = re.sub(
                r'(\w)\s*\\top\b',
                r'\1^{\\top}',
                text
            )

            # 妯″紡6: 淇濈暀 \tag{xxx} 鍛戒护锛岃浆鎹负鍙覆鏌撴牸寮忥紙鍦ㄥ叕寮忓悗闈㈡樉绀虹紪鍙凤級
            # \tag{1.15} -> \qquad (1.15)
            text = re.sub(r'\\tag\{([^}]*)\}', r'\\qquad (\\1)', text)
        except re.error as e:
            # 濡傛灉姝ｅ垯琛ㄨ揪寮忛敊璇紙濡?bad escape锛夛紝杩斿洖鍘熸枃
            logger.warning("Math extraction cleanup failed: %s", e)
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
            r'\u7b2c\s*\d{1,4}\s*\u9875(?:\s*(?:/|\u5171)\s*\d{1,4}\s*\u9875?)?',
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

        # 鍒犻櫎杩愯鏍囬妯″紡锛堝 "1. 涓嶅彲鍘嬬缉娆ф媺鏂圭▼" 鎴?"Chapter 1 Introduction"锛?
        # 杩欎簺閫氬父鍦ㄩ〉闈㈢殑椤堕儴鎴栧簳閮紝浣滀负绔犺妭瀵艰埅
        # 鍏抽敭锛氬彧鍖归厤鍗曠嫭鍑虹幇鐨勭畝鐭爣棰橈紝涓嶅尮閰嶅寘鍚彞瀛愬唴瀹圭殑琛?
        running_header_patterns = [
            r'^\d{1,2}\.\s*[\u4e00-\u9fff]{2,20}$',
            r'^\u7b2c\s*\d+\s*\u7ae0\s*[\u4e00-\u9fff]{2,20}$',
            r'^[\u4e00-\u9fff]{2,12}\s+\d+\.\d+(?:\s+[\u4e00-\u9fff]{1,12})?$',
            r'^\s*\d+\s+\d+(?:\.\d+)?\.?\s*[\u4e00-\u9fff]{1,20}$',
            r'^(?:chapter|section)\s+\d+(?:\.\d+)*\s+.{2,40}$',
        ]
        for pattern in running_header_patterns:
            if re.match(pattern, s, re.IGNORECASE):
                return True

        return False

    def _normalize_margin_candidate(self, line: str) -> str:
        s = re.sub(r'\s+', ' ', (line or '').strip())
        s = re.sub(r'\d+', '#', s)
        return s.lower()

    def _is_margin_noise_candidate(self, line: str) -> bool:
        s = (line or '').strip()
        if not s or s.startswith('['):
            return False
        if len(s) > 120:
            return False
        if re.search(r'[銆傦紒锛?!?]\s*$', s) and len(s) > 40:
            return False
        return True

    def _remove_repeated_marginal_lines(self, pages_text: List[str], pages_to_extract: List[int]) -> List[str]:
        if len(pages_to_extract) < 2:
            return pages_text

        margin_counts = {}
        page_lines = {}
        for page_num in pages_to_extract:
            lines = (pages_text[page_num] or '').splitlines()
            nonempty = [(idx, line) for idx, line in enumerate(lines) if line.strip()]
            edge_lines = nonempty[:3] + nonempty[-3:]
            seen = set()
            for _, line in edge_lines:
                if not self._is_margin_noise_candidate(line):
                    continue
                key = self._normalize_margin_candidate(line)
                if not key or key in seen:
                    continue
                seen.add(key)
                margin_counts[key] = margin_counts.get(key, 0) + 1
            page_lines[page_num] = lines

        threshold = max(2, int(len(pages_to_extract) * 0.25 + 0.999))
        repeated = {key for key, count in margin_counts.items() if count >= threshold}
        if not repeated:
            return pages_text

        cleaned = list(pages_text)
        for page_num in pages_to_extract:
            lines = page_lines.get(page_num, [])
            keep = [True] * len(lines)
            nonempty_indices = [idx for idx, line in enumerate(lines) if line.strip()]
            removable_indices = set(nonempty_indices[:4] + nonempty_indices[-4:])
            for idx in removable_indices:
                line = lines[idx]
                if (
                    self._is_margin_noise_candidate(line)
                    and self._normalize_margin_candidate(line) in repeated
                ):
                    keep[idx] = False
            cleaned[page_num] = '\n'.join(
                line for idx, line in enumerate(lines) if keep[idx]
            ).strip()
        return cleaned

    def _find_running_headers(self, pages: List[PageExtraction], window: int = 5) -> List[PageExtraction]:
        """鏍规嵁鐩搁偦椤甸潰閲嶅鐨勯琛屾爣璁拌繍琛屾爣棰樸€?"""
        if not pages:
            return []

        first_line_counts = {}
        normalized_by_index = []
        for page in pages:
            first_line = ''
            for line in (page.text or '').splitlines():
                candidate = line.strip()
                if candidate:
                    first_line = candidate
                    break
            normalized_by_index.append(first_line)
            if first_line:
                first_line_counts[first_line] = first_line_counts.get(first_line, 0) + 1

        result = []
        for idx, page in enumerate(pages):
            first_line = normalized_by_index[idx]
            is_repeated = bool(first_line) and first_line_counts.get(first_line, 0) >= 2
            result.append(PageExtraction(
                page_num=page.page_num,
                text=page.text,
                is_running_header=is_repeated,
            ))
        return result

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
        """浠?PyPDF2 鐨?XObject 涓彇鍑洪潰绉渶澶х殑鍥剧墖銆?"""
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

    def _should_use_ocr(self, text: str, quality: float, image_regions: List[_ImageRegion], table_bboxes: List[Tuple[float, float, float, float]]) -> bool:
        if not text.strip():
            return True
        # 鏈夎〃鏍肩粨鏋勪絾鏂囨湰灞傜己灏戞崲琛岀锛堣〃鏍煎唴瀹瑰彲鑳戒负鍥剧墖鏍煎紡宓屽叆锛夛紝寮哄埗 OCR
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
        return f"{primary}\n\n[OCR琛ュ厖]\n{secondary}"

    # ==================== v0.9 绔犺妭妫€娴嬩笌鍥伴毦椤靛垎绫?====================

    def detect_chapter_boundaries(self, pdf_path: str) -> List[ChapterBoundary]:
        """
        妫€娴婸DF鐨勭珷鑺傝竟鐣屻€?

        绠楁硶:
        1. 鐢╬dfplumber璇诲彇姣忛〉鎵€鏈塩hars
        2. 鎸墆鍧愭爣鑱氱被鎴愯
        3. 璁＄畻姣忛〉鐨勩€屾鏂囧熀绾垮瓧鍙枫€? 涓綅鏁?
        4. 瀛楀彿 > 鍩虹嚎*1.25 涓?< 鍩虹嚎*3.0 鐨勮 鈫?鍊欓€夋爣棰?
        5. 姝ｅ垯浜屾纭锛堜腑鑻辨枃锛?
        6. 杩囨护杩囩煭锛?2瀛楋級鍜岃繃闀匡紙>80瀛楋級鐨勬爣棰?

        Returns:
            鎸夐〉鐮佹帓搴忕殑 ChapterBoundary 鍒楄〃
        """
        boundaries: List[ChapterBoundary] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    chars = page.chars
                    if not chars or len(chars) < 10:
                        continue

                    # 1. 璁＄畻姣忚瀛楀彿锛堟寜y鍧愭爣鑱氱被锛?
                    lines = self._group_chars_into_lines(chars)
                    if not lines:
                        continue

                    # 2. 鎵炬鏂囧熀绾垮瓧鍙凤紙椤甸潰瀛楀彿涓綅鏁帮級
                    sizes = [ln['size'] for ln in lines if ln['size'] > 0]
                    if not sizes:
                        continue
                    sorted_sizes = sorted(sizes)
                    median_size = sorted_sizes[len(sorted_sizes) // 2]
                    if median_size <= 0:
                        continue

                    # 3. 鎵惧€欓€夋爣棰樿锛氬瓧鍙?> 鍩虹嚎*1.25 涓?< 鍩虹嚎*3.0
                    for line in lines:
                        if not (median_size * 1.25 < line['size'] < median_size * 3.0):
                            continue
                        text = line['text'].strip()
                        if not text or len(text) < 2 or len(text) > 80:
                            continue
                        # 璺宠繃绾暟瀛楋紙椤电爜/绔犺妭缂栧彿鍚庨潰娌℃爣棰樼殑锛?
                        if not any(c.isalpha() or '\u4e00' <= c <= '\u9fff' for c in text):
                            continue
                        # 姝ｅ垯浜屾纭
                        if not self._looks_like_heading(text):
                            continue
                        # 杩囨护椤电湁/椤佃剼鍖哄煙锛堝墠5%鎴栧悗5%锛?
                        page_height = page.height or 792
                        if line['y0'] < page_height * 0.05 or line['y0'] > page_height * 0.95:
                            continue
                        # 鍒ゆ柇鏍囬绾у埆
                        level = self._classify_heading_level(text, line['size'], median_size)
                        boundaries.append(ChapterBoundary(
                            page_num=page_idx,
                            title=text,
                            level=level,
                            font_size=round(line['size'], 2),
                            char_count=len(text),
                        ))
        except Exception as exc:
            # 浠讳綍寮傚父閮借繑鍥炵┖鍒楄〃锛岃皟鐢ㄦ柟鍥為€€鍒?-椤靛潡
            logger.warning("Chapter detection failed: %s", exc)
            return []

        # 鍘婚噸锛氱浉閭婚〉鍑虹幇鐩稿悓鏍囬 鈫?淇濈暀瀛楀彿鏇村ぇ鐨?
        deduped: List[ChapterBoundary] = []
        for b in boundaries:
            if deduped and deduped[-1].title == b.title and abs(deduped[-1].page_num - b.page_num) <= 1:
                if b.font_size > deduped[-1].font_size:
                    deduped[-1] = b
                continue
            deduped.append(b)
        return deduped

    def _group_chars_into_lines(self, chars: List[dict]) -> List[dict]:
        """鎶奵hars鎸墆鍧愭爣鑱氱被鎴愯锛岃繑鍥?[{text, size, y0, x0}, ...]"""
        if not chars:
            return []
        # 鎸塼op(y0)鎺掑簭
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
        """涓€琛宑hars 鈫?{text, size, y0, x0}"""
        text = ''.join(c.get('text', '') for c in chars).strip()
        sizes = [c.get('size', 0) for c in chars if c.get('size', 0) > 0]
        avg_size = sum(sizes) / len(sizes) if sizes else 0
        y0 = min((c.get('top', c.get('y0', 0)) for c in chars), default=0)
        x0 = min((c.get('x0', 0) for c in chars), default=0)
        return {'text': text, 'size': avg_size, 'y0': y0, 'x0': x0}

    def _looks_like_heading(self, text: str) -> bool:
        """Return True when a line looks like a Chinese or English heading."""
        patterns = [
            r'^(Chapter|CHAPTER|Section|SECTION|Part|PART)\s+[\dIVX]+',
            r'^(Abstract|ABSTRACT|Introduction|INTRODUCTION|Conclusion|CONCLUSION|References|REFERENCES|Bibliography|Acknowledgement|Appendix)\b',
            r'^\d+(\.\d+){0,3}\.?\s+[A-Z][\w\s\-:,\(\)]{2,60}$',
            r'^\d+\.\s+[A-Z][a-zA-Z]+',
            r'^\u7b2c\s*[\u4e00-\u9fff\d]+\s*[\u7ae0\u8282]\s*[\u4e00-\u9fff]*',
            r'^(\u6458\u8981|\u5f15\u8a00|\u524d\u8a00|\u80cc\u666f|\u76f8\u5173\u5de5\u4f5c|\u65b9\u6cd5|\u5b9e\u9a8c|\u7ed3\u679c|\u8ba8\u8bba|\u7ed3\u8bba|\u603b\u7ed3|\u53c2\u8003\u6587\u732e|\u81f4\u8c22|\u9644\u5f55)\b',
        ]
        return any(re.match(p, text) for p in patterns)

    def _classify_heading_level(self, text: str, font_size: float, median_size: float) -> int:
        """Classify heading level from font size and heading pattern."""
        ratio = font_size / median_size if median_size > 0 else 1.0
        if ratio > 2.0:
            return 1
        if re.match(r'^(Chapter|CHAPTER|\u7b2c\s*[\u4e00-\u9fff\d]+\s*\u7ae0)', text):
            return 1
        if re.match(r'^(Section|SECTION|\u7b2c\s*[\u4e00-\u9fff\d]+\s*\u8282)', text):
            return 2
        m = re.match(r'^(\d+)(\.\d+)+', text)
        if m:
            depth = m.group(0).count('.') + 1
            return min(3, depth)
        if re.match(r'^\d+\.', text):
            return 2
        if ratio > 1.6:
            return 1
        return 2

    def classify_difficult_pages(self, pdf_path: str) -> List[PageFeatures]:
        """
        鍒嗙被姣忛〉闅惧害锛氬叕寮忓瘑搴?琛ㄦ牸瀵嗗害/鍥惧儚瀵嗗害銆?

        Returns:
            PageFeatures 鍒楄〃
        """
        results: List[PageFeatures] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ''
                    # 鍏紡瀵嗗害
                    formula_lines = self._count_formula_lines(text)
                    total_lines = max(1, len([l for l in text.split('\n') if l.strip()]))
                    formula_density = formula_lines / total_lines
                    # 琛ㄦ牸瀵嗗害锛堝鍒楃粨鏋勶細鍚岃鍚涓?鈮? 绌烘牸鐨勫簭鍒楋級
                    table_lines = sum(1 for l in text.split('\n') if re.search(r'\S\s{2,}\S\s{2,}\S', l))
                    table_density = table_lines / total_lines
                    # 鍥惧儚瀵嗗害
                    image_area = sum(
                        (img.get('x1', 0) - img.get('x0', 0)) * (img.get('bottom', img.get('y1', 0)) - img.get('top', img.get('y0', 0)))
                        for img in page.images
                    )
                    page_area = (page.width or 612) * (page.height or 792)
                    image_density = image_area / page_area if page_area > 0 else 0.0
                    # 鍒ゅ畾鍥伴毦
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
            logger.warning("Difficult-page classification failed: %s", exc)
            return []
        return results

    def _count_formula_lines(self, text: str) -> int:
        """缁熻鍚暟瀛﹀叕寮忕殑琛屾暟"""
        if not text:
            return 0
        formula_patterns = [
            r'\$[^$]+\$',                # $...$
            r'\\\([^)]+\\\)',            # \(...\)
            r'\\\[[^\]]+\\\]',           # \[...\]
            r'\\begin\{equation',        # \begin{equation}
            r'\\begin\{align',           # \begin{align}
            r'\\frac\b',                 # \frac
            r'\\sum\b|\\int\b|\\prod\b',  # 姹傚拰/绉垎/涔樼Н
            r'\\partial\b|\\nabla\b',    # 鍋忓/姊害
            r'\\alpha|\\beta|\\gamma|\\theta|\\lambda|\\mu|\\sigma|\\omega',
            r'\^[_a-zA-Z0-9\{\(]',        # 涓婃爣
            r'[_a-zA-Z0-9\}]\^',         # 涓婃爣锛堝湪鍓嶏級
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
        """鎻愬彇 PDF 鐨勬瘡椤垫枃鏈紝浼樺厛鏂囨湰灞傦紝蹇呰鏃?OCR 鍏滃簳銆?"""
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f'PDF鏂囦欢涓嶅瓨鍦? {pdf_path}')

        logger.info("PDF text extraction started: %s", pdf_path)
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
                    '姝ｅ湪浣跨敤澧炲己瑙ｆ瀽鍣ㄦ彁鍙朠DF鏂囨湰...',
                    'info',
                    '馃搫 寮€濮嬭В鏋怭DF鏂囨湰灞傘€佽〃鏍煎拰OCR鍥為€€',
                )

                for idx, page_num in enumerate(pages_to_extract):
                    page = pdf.pages[page_num]
                    pypdf_page = reader.pages[page_num]

                    text_layer = self._extract_page_text_layer(page)
                    text_layer = self._remove_bottom_small_text(page, text_layer)
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

                    # Column geometry is not reliable enough to infer document
                    # semantics: titles, formulas and wide tables routinely
                    # resemble two columns. Keep extracted reading order only.
                    is_two_column = False

                    logger.info("Page %d/%d text layer: %d chars, quality %.2f", page_num + 1, total_pages, len(text_layer), quality)

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
                                        logger.info("Page %d table region %d OCR quality: %.2f", page_num + 1, t_idx, ocr_quality)
                                    except Exception as crop_err:
                                        logger.warning("Page %d table OCR failed: %s", page_num + 1, crop_err)

                                if table_texts:
                                    ocr_text = '\n\n'.join(table_texts)
                                else:
                                    ocr_text, _ = self._run_ocr(page_image, layout_hint)
                            else:
                                ocr_text, ocr_quality = self._run_ocr(page_image, layout_hint)
                                logger.info("Page %d OCR quality: %.2f, layout: %s", page_num + 1, ocr_quality, layout_hint)

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

                    # 鍙屾爮甯冨眬鎻愮ず
                    if is_two_column:
                        extracted_text = f"[TWO_COLUMN_PAGE]\n{extracted_text}"

                    extracted_text = self._cleanup_pagination(extracted_text, page_num, total_pages)
                    extracted_text = self._normalize_text(extracted_text)

                    # 淇 PDF 鎻愬彇鏃朵涪澶辩殑鏁板绗﹀彿
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
                    logger.info("Page %d/%d complete: source=%s, chars=%d, quality=%.2f", page_num + 1, total_pages, source_label, len(extracted_text), page_quality)

                    pages_text[page_num] = extracted_text
                    self._emit_progress(
                        'extracting',
                        idx + 1,
                        len(pages_to_extract),
                        f'Parsed {idx + 1}/{len(pages_to_extract)} pages',
                        'success',
                        f'Page {page_num + 1} parsed (source: {source_label}, quality: {page_quality:.0%})',
                    )

                logger.info("PDF extraction complete: %d/%d pages", len(pages_to_extract), total_pages)
                pages_text = self._remove_repeated_marginal_lines(pages_text, pages_to_extract)
        except Exception as exc:
            raise Exception(f"PDF瑙ｆ瀽澶辫触: {exc}")

        return pages_text
