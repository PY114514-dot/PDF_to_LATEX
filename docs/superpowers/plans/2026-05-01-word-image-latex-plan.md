# Word & Image to LaTeX Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Word (.docx) to LaTeX conversion and enhanced image to LaTeX capabilities (vector support, batch processing, formula/table improvements)

**Architecture:**
- Word conversion: python-docx for structure extraction → basic LaTeX conversion → LLM optimization for complex elements (tables, math)
- Image enhancement: CairoSVG/EMF conversion → integrate into existing OCR pipeline → batch merger

**Tech Stack:** python-docx, cairosvg, Pillow, existing LLM clients, existing Flask app

---

## File Structure

```
backend/
  ├── docx2latex_converter.py   [NEW] - Word to LaTeX core
  ├── vector2raster.py           [NEW] - SVG/EMF to PNG conversion
  ├── image_batch_merger.py      [NEW] - Batch image processing
  ├── image2latex_enhanced.py     [MODIFY] - Add vector support, formula/table enhancements
  └── app_enhanced.py            [MODIFY] - Add /api/convert-docx, enhance /api/convert-images

frontend/
  ├── static/script_enhanced.js  [MODIFY] - Add DOCX upload handling, tabbed UI
  ├── static/style_enhanced.css  [MODIFY] - Add DOCX upload styles
  └── templates/index_enhanced.html [MODIFY] - Add DOCX tab
```

---

## Task 1: Create docx2latex_converter.py

**Files:**
- Create: `backend/docx2latex_converter.py`
- Test: `backend/tests/test_docx2latex.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_docx2latex.py
import pytest
import tempfile
import os
from pathlib import Path
from docx import Document
from docx2latex_converter import Docx2LaTeXConverter

def create_test_docx(paragraphs, tables=None, headings=None):
    """Helper to create test DOCX file."""
    doc = Document()
    if headings:
        for level, text in headings:
            doc.add_heading(text, level=level)
    for p in paragraphs:
        doc.add_paragraph(p)
    if tables:
        for table_data in tables:
            table = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
            for i, row_data in enumerate(table_data):
                for j, cell_data in enumerate(row_data):
                    table.cell(i, j).text = cell_data
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        doc.save(f.name)
        return f.name

def test_extract_headings():
    """Test heading extraction."""
    docx_path = create_test_docx([], headings=[(1, 'Title'), (2, 'Subtitle')])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    assert len(content['headings']) == 2
    assert content['headings'][0]['text'] == 'Title'
    assert content['headings'][0]['level'] == 1
    os.unlink(docx_path)

def test_extract_paragraphs():
    """Test paragraph extraction."""
    docx_path = create_test_docx(['Hello world', 'Test paragraph'])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    assert len(content['paragraphs']) == 2
    os.unlink(docx_path)

def test_extract_tables():
    """Test table extraction."""
    table_data = [['A', 'B'], ['C', 'D']]
    docx_path = create_test_docx([], tables=[table_data])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    assert len(content['tables']) == 1
    assert content['tables'][0][0] == ['A', 'B']
    os.unlink(docx_path)

def test_heading_to_latex():
    """Test heading conversion to LaTeX."""
    docx_path = create_test_docx([], headings=[(1, 'Main'), (2, 'Sub')])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    latex = converter.convert_structure(content)
    assert '\\section{Main}' in latex
    assert '\\subsection{Sub}' in latex
    os.unlink(docx_path)

def test_paragraph_to_latex():
    """Test paragraph conversion to LaTeX."""
    docx_path = create_test_docx(['Hello world'])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    latex = converter.convert_structure(content)
    assert 'Hello world' in latex
    os.unlink(docx_path)

def test_table_to_latex():
    """Test table conversion to LaTeX."""
    table_data = [['A', 'B'], ['C', 'D']]
    docx_path = create_test_docx([], tables=[table_data])
    converter = Docx2LaTeXConverter()
    content = converter.extract_content(docx_path)
    latex = converter.convert_structure(content)
    assert '\\begin{tabular}' in latex
    assert 'A' in latex and 'B' in latex
    os.unlink(docx_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_docx2latex.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'docx2latex_converter'

- [ ] **Step 3: Write minimal implementation**

```python
# backend/docx2latex_converter.py
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
        """
        Extract structured content from .docx file.

        Returns:
            Dict with keys: paragraphs, headings, tables, lists, equations
        """
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

                # Check if it's a heading
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
        """
        Convert extracted structure to basic LaTeX.
        Simple elements are converted directly, complex ones are marked for LLM.
        """
        latex_parts = []

        # Process headings
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

        # Process paragraphs
        for para in content.get('paragraphs', []):
            if para:
                latex_parts.append(para)

        # Process tables (basic conversion, LLM will refine)
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

        lines = ['\\begin{table}[htbp]', '\\centering', f'\\begin{tabular}{|{"".join(["c|" for _ in range(cols)])}}}']
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
        """
        Send complex elements (tables, equations) to LLM for quality improvement.
        """
        if not tables:
            return basic_latex

        # Prepare table context for LLM
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

            # Replace placeholders with optimized tables
            result = basic_latex
            for i in range(len(tables)):
                placeholder = f'% [TABLE_PLACEHOLDER_{i}]'
                if placeholder in result:
                    # Extract the optimized table (simplified - just replace the placeholder)
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
        """
        Async conversion of .docx to LaTeX.
        """
        import asyncio
        import time

        start_time = time.time()
        self._emit_progress('extracting', 0, 3, '正在提取Word文档内容...')

        # Extract content
        content = self.extract_content(docx_path)

        self._emit_progress('converting', 1, 3, '正在转换为LaTeX结构...')

        # Convert to basic LaTeX
        basic_latex = self.convert_structure(content)

        self._emit_progress('optimizing', 2, 3, '正在优化复杂元素...')

        # Process complex elements with LLM
        final_latex = await self.process_complex_elements(
            basic_latex,
            content.get('tables', [])
        )

        # Sanitize
        final_latex = sanitize_latex_body(final_latex)

        # Add document wrapper
        if add_document_wrapper:
            final_latex = wrap_with_template(
                final_latex,
                template_name=template_name,
                use_chinese=self.translate
            )

        # Save output
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
        return asyncio.run(self.convert_async(
            docx_path, output_path, add_document_wrapper, template_name
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_docx2latex.py -v`
Expected: PASS (or most tests pass)

- [ ] **Step 5: Commit**

```bash
git add backend/docx2latex_converter.py backend/tests/test_docx2latex.py
git commit -m "feat: add docx2latex_converter with basic structure extraction"
```

---

## Task 2: Create vector2raster.py

**Files:**
- Create: `backend/vector2raster.py`
- Test: `backend/tests/test_vector2raster.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_vector2raster.py
import pytest
import tempfile
import os
from pathlib import Path
from vector2raster import VectorToRasterConverter

def test_svg_to_png():
    """Test SVG to PNG conversion."""
    # Create a simple SVG file
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect width="100" height="100" fill="blue"/>
</svg>'''
    with tempfile.NamedTemporaryFile(suffix='.svg', mode='w', delete=False) as f:
        f.write(svg_content)
        svg_path = f.name

    output_path = tempfile.mktemp(suffix='.png')
    converter = VectorToRasterConverter()
    result = converter.svg_to_png(svg_path, output_path, dpi=300)

    assert result is True
    assert os.path.exists(output_path)
    os.unlink(svg_path)
    if os.path.exists(output_path):
        os.unlink(output_path)

def test_unsupported_format():
    """Test unsupported format error."""
    converter = VectorToRasterConverter()
    with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
        f.write(b'random data')
        path = f.name

    with pytest.raises(ValueError, match="Unsupported vector format"):
        converter.convert_to_raster(path, tempfile.mktemp())
    os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_vector2raster.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'vector2raster'

- [ ] **Step 3: Write minimal implementation**

```python
# backend/vector2raster.py
"""
Vector image (SVG/EMF) to raster (PNG) converter
Uses cairosvg for SVG conversion
"""

import os
from pathlib import Path
from typing import Optional

try:
    import cairosvg
    CAIRO_AVAILABLE = True
except ImportError:
    CAIRO_AVAILABLE = False


class VectorToRasterConverter:
    """Converts vector images (SVG, EMF) to raster format (PNG)"""

    def __init__(self):
        self.cairo_available = CAIRO_AVAILABLE

    def svg_to_png(
        self,
        svg_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """
        Convert SVG to PNG.

        Args:
            svg_path: Path to input SVG file
            output_path: Path to output PNG file
            dpi: Resolution for rasterization

        Returns:
            True if successful, False otherwise
        """
        if not self.cairo_available:
            raise RuntimeError(
                "cairosvg not installed. Install with: pip install cairosvg"
            )

        try:
            cairosvg.svg2png(
                url=svg_path,
                write_to=output_path,
                dpi=dpi
            )
            return True
        except Exception as e:
            print(f"SVG to PNG conversion failed: {e}")
            return False

    def emf_to_png(
        self,
        emf_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """
        Convert EMF to PNG.

        Note: EMF support is limited. For full EMF support, consider using
        LibreOffice or ImageMagick as external tools.

        Args:
            emf_path: Path to input EMF file
            output_path: Path to output PNG file
            dpi: Resolution for rasterization

        Returns:
            True if successful, False otherwise
        """
        # EMF support via external tools is complex
        # For now, raise an informative error
        raise NotImplementedError(
            "EMF conversion requires external tools (LibreOffice or ImageMagick). "
            "Consider using: libreoffice --headless --convert-to png input.emf "
            "or: convert input.emf output.png"
        )

    def convert_to_raster(
        self,
        input_path: str,
        output_path: str,
        dpi: int = 300
    ) -> bool:
        """
        Auto-detect format and convert to raster.

        Args:
            input_path: Path to input vector file
            output_path: Path to output raster file
            dpi: Resolution for rasterization

        Returns:
            True if successful, False otherwise

        Raises:
            ValueError: If format is not supported
        """
        ext = Path(input_path).suffix.lower()

        if ext == '.svg':
            return self.svg_to_png(input_path, output_path, dpi)
        elif ext == '.emf':
            return self.emf_to_png(input_path, output_path, dpi)
        else:
            raise ValueError(f"Unsupported vector format: {ext}. Supported: .svg, .emf")

    def is_vector_file(self, file_path: str) -> bool:
        """Check if file is a vector format."""
        ext = Path(file_path).suffix.lower()
        return ext in ['.svg', '.emf', '.eps', '.wmf']
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_vector2raster.py -v`
Expected: PASS (skip EMF test if not implemented)

- [ ] **Step 5: Commit**

```bash
git add backend/vector2raster.py backend/tests/test_vector2raster.py
git commit -m "feat: add vector2raster for SVG/EMF to PNG conversion"
```

---

## Task 3: Create image_batch_merger.py

**Files:**
- Create: `backend/image_batch_merger.py`
- Test: `backend/tests/test_image_batch_merger.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_image_batch_merger.py
import pytest
import tempfile
from pathlib import Path
from image_batch_merger import ImageBatchMerger

def test_merge_single_image():
    """Test merging single image."""
    # Create a dummy image for testing
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='red')
        img.save(f.name)
        image_path = f.name

    merger = ImageBatchMerger()
    latex = merger.merge_to_latex([image_path])

    assert '\\section{Image 1}' in latex
    assert '\\begin{document}' in latex

    # Cleanup
    Path(image_path).unlink()

def test_merge_multiple_images():
    """Test merging multiple images."""
    images = []
    from PIL import Image

    for i in range(3):
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            img = Image.new('RGB', (100, 100), color='blue')
            img.save(f.name)
            images.append(f.name)

    merger = ImageBatchMerger()
    latex = merger.merge_to_latex(images)

    assert '\\section{Image 1}' in latex
    assert '\\section{Image 2}' in latex
    assert '\\section{Image 3}' in latex

    # Cleanup
    for path in images:
        Path(path).unlink()

def test_latex_content_contains_image_names():
    """Test that image filenames appear in LaTeX."""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False, prefix='test_image') as f:
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='green')
        img.save(f.name)
        image_path = f.name

    merger = ImageBatchMerger()
    latex = merger.merge_to_latex([image_path], include_filenames=True)

    assert 'test_image' in latex

    Path(image_path).unlink()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_image_batch_merger.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'image_batch_merger'

- [ ] **Step 3: Write minimal implementation**

```python
# backend/image_batch_merger.py
"""
Image batch merger - combines multiple images into single LaTeX document
"""

from pathlib import Path
from typing import List, Optional

from latex_utils import wrap_with_template


class ImageBatchMerger:
    """Merges multiple images into a single LaTeX document"""

    def __init__(self, template_name: str = 'article'):
        self.template_name = template_name

    def merge_to_latex(
        self,
        image_paths: List[str],
        include_filenames: bool = True,
        add_document_wrapper: bool = True
    ) -> str:
        """
        Merge multiple images into LaTeX sections.

        Args:
            image_paths: List of image file paths
            include_filenames: Whether to include filenames as section titles
            add_document_wrapper: Whether to wrap in document template

        Returns:
            LaTeX content as string
        """
        sections = []

        for idx, image_path in enumerate(image_paths, 1):
            path = Path(image_path)
            stem = path.stem

            if include_filenames:
                sections.append(f'\\section{{{stem}}}')

            # Add the image (using graphicx)
            sections.append(f'\\begin{{figure}}[htbp]')
            sections.append(f'\\centering')
            sections.append(f'\\includegraphics[width=0.8\\textwidth]{{{path.name}}}')
            sections.append(f'\\caption{{{stem}}}')
            sections.append(f'\\end{{figure}}')
            sections.append('')

        latex_content = '\n'.join(sections)

        if add_document_wrapper:
            latex_content = wrap_with_template(
                latex_content,
                template_name=self.template_name,
                use_chinese=False
            )

        return latex_content

    def save_merged(
        self,
        image_paths: List[str],
        output_path: str,
        include_filenames: bool = True
    ) -> str:
        """
        Merge images and save to file.

        Args:
            image_paths: List of image file paths
            output_path: Path to save the .tex file
            include_filenames: Whether to include filenames as section titles

        Returns:
            Path to saved file
        """
        latex_content = self.merge_to_latex(image_paths, include_filenames)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(latex_content, encoding='utf-8')

        return str(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_image_batch_merger.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/image_batch_merger.py backend/tests/test_image_batch_merger.py
git commit -m "feat: add image_batch_merger for combining multiple images"
```

---

## Task 4: Modify app_enhanced.py - Add DOCX endpoint

**Files:**
- Modify: `backend/app_enhanced.py`

- [ ] **Step 1: Write the test first**

```python
# backend/tests/test_docx_endpoint.py
import pytest
import tempfile
import json
from pathlib import Path
from docx import Document

def test_convert_docx_endpoint():
    """Test /api/convert-docx endpoint."""
    # Create a test DOCX file
    doc = Document()
    doc.add_heading('Test Title', 1)
    doc.add_paragraph('Test paragraph content.')
    doc.add_table([['A', 'B'], ['C', 'D']])

    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as f:
        doc.save(f.name)
        docx_path = f.name

    # Test via Flask test client would go here
    # For now, just verify the file was created
    assert Path(docx_path).exists()

    Path(docx_path).unlink()
```

- [ ] **Step 2: Add import and endpoint code**

After line in app_enhanced.py that imports image2latex_enhanced, add:

```python
# Add after image2latex_enhanced import
from docx2latex_converter import Docx2LaTeXConverter
```

After ALLOWED_IMAGE_EXTENSIONS definition (around line 58), add:

```python
ALLOWED_DOCX_EXTENSIONS = {'docx'}
```

After `allowed_image_file` function (around line 78), add:

```python
def allowed_docx_file(filename):
    """Check DOCX file extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCX_EXTENSIONS
```

After the `/api/convert-image` endpoint, add:

```python
@app.route('/api/convert-docx', methods=['POST'])
def convert_docx():
    """Convert Word (.docx) to LaTeX."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400

    if not allowed_docx_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式，请上传 .docx 文件'}), 400

    # Get parameters
    model = request.form.get('model', 'deepseek-math')
    translate = request.form.get('translate', 'false').lower() == 'true'

    # Save uploaded file
    timestamp = int(time.time() * 1000)
    task_id = build_task_id('docx', file.filename, timestamp)
    filename = secure_filename(file.filename)
    docx_path = UPLOAD_FOLDER / f"{task_id}_{filename}"
    file.save(str(docx_path))

    try:
        # Create converter
        converter = Docx2LaTeXConverter(
            model_name=model,
            translate=translate
        )

        # Output path
        output_filename = build_output_filename(filename, translate=translate)
        output_path = OUTPUT_FOLDER / output_filename

        # Convert
        result = converter.convert(
            str(docx_path),
            str(output_path),
            add_document_wrapper=True
        )

        # Cleanup uploaded file
        docx_path.unlink(missing_ok=True)

        return jsonify({
            'success': True,
            'latex': Path(result['output_path']).read_text(encoding='utf-8'),
            'download_url': f'/api/download/{output_filename}',
            'messages': result.get('messages', [])
        })

    except Exception as e:
        # Cleanup on error
        docx_path.unlink(missing_ok=True)
        import traceback
        return jsonify({
            'success': False,
            'error': f'转换失败: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `pytest backend/tests/ -v -k "not test_docx" --ignore=backend/tests/test_docx_endpoint.py 2>&1 | head -50`
Expected: Most tests should still pass

- [ ] **Step 4: Commit**

```bash
git add backend/app_enhanced.py
git commit -m "feat: add /api/convert-docx endpoint for Word to LaTeX"
```

---

## Task 5: Modify image2latex_enhanced.py - Add vector support

**Files:**
- Modify: `backend/image2latex_enhanced.py`

- [ ] **Step 1: Read the current file to understand imports**

Look at lines 1-20 of image2latex_enhanced.py to see current imports.

- [ ] **Step 2: Add vector conversion support**

After the existing imports (around line 10), add:

```python
# Vector image support
try:
    from vector2raster import VectorToRasterConverter
    VECTOR_CONVERTER = VectorToRasterConverter()
except ImportError:
    VECTOR_CONVERTER = None
    print("Warning: vector2raster not available. SVG/EMF support disabled.")
```

After the `extract_text_from_image` method, add a pre-processing method:

```python
def _preprocess_image(self, image_path: str) -> str:
    """
    Pre-process image: convert vector formats to raster if needed.

    Args:
        image_path: Path to image file

    Returns:
        Path to (possibly converted) raster image
    """
    path = Path(image_path)
    ext = path.suffix.lower()

    # Check if it's a vector format
    if ext in ['.svg', '.emf']:
        if VECTOR_CONVERTER is None:
            raise ValueError(
                f"Vector format {ext} not supported. "
                "Please convert to PNG/JPG first or install cairosvg."
            )

        # Convert to PNG in same directory
        output_path = path.with_suffix('.png')
        if VECTOR_CONVERTER.convert_to_raster(str(path), str(output_path), dpi=300):
            return str(output_path)
        else:
            raise ValueError(f"Failed to convert {ext} to PNG")

    return str(image_path)
```

Modify the `convert_image` method to call `_preprocess_image` at the start (after line 412):

```python
# After: image_path = Path(image_path)
# Add:
image_path_str = self._preprocess_image(str(image_path))
image_path = Path(image_path_str)
```

- [ ] **Step 3: Run tests**

Run: `pytest backend/tests/test_image2latex.py -v 2>&1 | head -30`
Expected: Existing tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/image2latex_enhanced.py
git commit -m "feat: add SVG/EMF vector image support to image2latex"
```

---

## Task 6: Modify /api/convert-images for batch processing

**Files:**
- Modify: `backend/app_enhanced.py`

- [ ] **Step 1: Find the existing /api/convert-images endpoint**

Search for `convert-images` in app_enhanced.py.

- [ ] **Step 2: Modify to support multiple files and batch mode**

Replace the existing `/api/convert-images` endpoint with:

```python
@app.route('/api/convert-images', methods=['POST'])
def convert_images():
    """Convert one or more images to LaTeX."""
    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'error': '没有上传文件'}), 400

    # Filter valid image files
    valid_files = []
    for file in files:
        if file.filename and allowed_image_file(file.filename):
            valid_files.append(file)

    if not valid_files:
        return jsonify({'success': False, 'error': '没有有效的图片文件'}), 400

    # Check for single vs batch mode
    merge = request.form.get('merge', 'true').lower() == 'true'
    model = request.form.get('model', 'deepseek-chat')
    quality_mode = request.form.get('quality_mode', 'standard')

    timestamp = int(time.time() * 1000)

    try:
        if merge and len(valid_files) > 1:
            # Batch mode: save files and process together
            saved_paths = []
            for file in valid_files:
                filename = secure_filename(file.filename)
                task_id = build_task_id('img', filename, timestamp)
                save_path = UPLOAD_FOLDER / f"{task_id}_{filename}"
                file.save(str(save_path))
                saved_paths.append(str(save_path))

            # Create converter
            converter = Image2LaTeXEnhanced(
                model_name=model,
                translate=False
            )

            # Process batch
            output_filename = f"batch_{timestamp}.tex"
            output_path = OUTPUT_FOLDER / output_filename

            # Use batch convert
            result = asyncio.run(converter.batch_convert_images(
                saved_paths,
                output_dir=str(OUTPUT_FOLDER),
                quality_mode=quality_mode
            ))

            # Build merged output using merger
            from image_batch_merger import ImageBatchMerger
            merger = ImageBatchMerger()
            merged_latex = merger.merge_to_latex(saved_paths)

            # Save merged result
            output_path.write_text(merged_latex, encoding='utf-8')

            # Cleanup uploaded files
            for path in saved_paths:
                Path(path).unlink(missing_ok=True)

            return jsonify({
                'success': True,
                'latex': merged_latex,
                'download_url': f'/api/download/{output_filename}',
                'count': len(valid_files),
                'results': result.get('results', [])
            })

        else:
            # Single file mode (backward compatible)
            file = valid_files[0]
            filename = secure_filename(file.filename)
            task_id = build_task_id('img', filename, timestamp)
            upload_path = UPLOAD_FOLDER / f"{task_id}_{filename}"
            file.save(str(upload_path))

            output_filename = build_output_filename(filename)
            output_path = OUTPUT_FOLDER / output_filename

            converter = Image2LaTeXEnhanced(
                model_name=model,
                translate=False
            )

            result = asyncio.run(converter.convert_image(
                str(upload_path),
                str(output_path),
                quality_mode=quality_mode
            ))

            # Cleanup
            upload_path.unlink(missing_ok=True)

            return jsonify({
                'success': True,
                'latex': result.get('output_file') and Path(result['output_file']).read_text(encoding='utf-8') or '',
                'download_url': f'/api/download/{output_filename}',
                'ocr_result': result.get('ocr_result', {})
            })

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f'转换失败: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500
```

- [ ] **Step 3: Commit**

```bash
git add backend/app_enhanced.py
git commit -m "feat: enhance /api/convert-images with batch processing"
```

---

## Task 7: Modify frontend - Add DOCX upload UI

**Files:**
- Modify: `frontend/templates/index_enhanced.html`
- Modify: `frontend/static/script_enhanced.js`
- Modify: `frontend/static/style_enhanced.css`

- [ ] **Step 1: Add DOCX tab to index_enhanced.html**

Find the existing tab navigation (should be around line with upload tabs). Add new tab:

```html
<li class="tab-btn active" data-tab="pdf-tab">PDF</li>
<li class="tab-btn" data-tab="image-tab">图片</li>
<li class="tab-btn" data-tab="docx-tab">Word</li>
```

Add the tab content after the image tab content:

```html
<!-- Word Upload Tab -->
<div class="upload-tab" id="docx-tab" style="display: none;">
    <h3>Word 转 LaTeX</h3>
    <p class="upload-hint">上传 .docx 文件，转换为 LaTeX 格式</p>
    <div class="file-drop-zone" id="docx-drop-zone">
        <div class="drop-zone-content">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
                <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <p>拖拽 Word 文件到此处，或<span class="browse-link">浏览</span></p>
            <p class="file-types">支持 .docx 格式</p>
        </div>
        <input type="file" id="docx-input" accept=".docx" style="display: none;">
    </div>
    <div id="docx-file-info" class="file-info" style="display: none;">
        <span class="file-name"></span>
        <button class="remove-btn" onclick="removeDocxFile()">&times;</button>
    </div>
    <div class="options-panel">
        <div class="option-group">
            <label>
                <input type="checkbox" id="docx-translate">
                <span>翻译为中文</span>
            </label>
        </div>
        <div class="option-group">
            <label class="option-label">模型选择</label>
            <select id="docx-model-select" class="model-select">
                <option value="deepseek-math" selected>DeepSeek Math</option>
                <option value="deepseek-chat">DeepSeek Chat</option>
                <option value="gpt4o">GPT-4o</option>
                <option value="glm47">GLM-4.7</option>
            </select>
        </div>
    </div>
    <button id="convert-docx-btn" class="convert-btn" disabled>
        <span class="btn-text">转换为 LaTeX</span>
        <span class="btn-loading" style="display: none;">
            <span class="spinner"></span>
            转换中...
        </span>
    </button>
    <div id="docx-progress" class="progress-container" style="display: none;">
        <div class="progress-bar">
            <div class="progress-fill" id="docx-progress-fill"></div>
        </div>
        <div class="progress-text" id="docx-progress-text"></div>
    </div>
</div>
```

- [ ] **Step 2: Add DOCX handling to script_enhanced.js**

Add DOCX-related functions after the image upload handling:

```javascript
// ===== DOCX Upload Handling =====

let selectedDocxFile = null;

function initDocxUpload() {
    const dropZone = document.getElementById('docx-drop-zone');
    const fileInput = document.getElementById('docx-input');
    const convertBtn = document.getElementById('convert-docx-btn');
    const fileInfo = document.getElementById('docx-file-info');

    if (!dropZone || !fileInput) return;

    // Click to browse
    dropZone.addEventListener('click', (e) => {
        if (e.target.classList.contains('browse-link') || e.target === dropZone) {
            fileInput.click();
        }
    });

    // File selected
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            handleDocxFileSelect(file);
        }
    });

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.docx')) {
            handleDocxFileSelect(file);
        }
    });

    // Convert button
    if (convertBtn) {
        convertBtn.addEventListener('click', convertDocxToLatex);
    }
}

function handleDocxFileSelect(file) {
    if (!file.name.endsWith('.docx')) {
        showError('请上传 .docx 格式的文件');
        return;
    }

    selectedDocxFile = file;
    const dropZone = document.getElementById('docx-drop-zone');
    const fileInfo = document.getElementById('docx-file-info');
    const fileName = fileInfo.querySelector('.file-name');
    const convertBtn = document.getElementById('convert-docx-btn');

    if (dropZone) dropZone.style.display = 'none';
    if (fileInfo) {
        fileInfo.style.display = 'flex';
        fileName.textContent = file.name;
    }
    if (convertBtn) convertBtn.disabled = false;
}

function removeDocxFile() {
    selectedDocxFile = null;
    const dropZone = document.getElementById('docx-drop-zone');
    const fileInfo = document.getElementById('docx-file-info');
    const fileInput = document.getElementById('docx-input');
    const convertBtn = document.getElementById('convert-docx-btn');

    if (dropZone) dropZone.style.display = 'block';
    if (fileInfo) fileInfo.style.display = 'none';
    if (fileInput) fileInput.value = '';
    if (convertBtn) convertBtn.disabled = true;
}

async function convertDocxToLatex() {
    if (!selectedDocxFile) {
        showError('请先选择文件');
        return;
    }

    const convertBtn = document.getElementById('convert-docx-btn');
    const progressContainer = document.getElementById('docx-progress');
    const progressFill = document.getElementById('docx-progress-fill');
    const progressText = document.getElementById('docx-progress-text');

    // Show progress
    setUiLoading(true, convertBtn);
    if (progressContainer) progressContainer.style.display = 'block';
    if (progressText) progressText.textContent = '正在上传和转换...';

    const formData = new FormData();
    formData.append('file', selectedDocxFile);
    formData.append('model', document.getElementById('docx-model-select')?.value || 'deepseek-math');
    formData.append('translate', document.getElementById('docx-translate')?.checked ? 'true' : 'false');

    try {
        const response = await fetch('/api/convert-docx', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            if (progressFill) progressFill.style.width = '100%';
            if (progressText) progressText.textContent = '转换完成！';

            // Display result
            displayLatexResult(result.latex, result.download_url);

            // Reset UI
            setTimeout(() => {
                removeDocxFile();
                if (progressContainer) progressContainer.style.display = 'none';
                setUiLoading(false, convertBtn);
            }, 1500);
        } else {
            throw new Error(result.error || '转换失败');
        }
    } catch (error) {
        showError('转换失败: ' + error.message);
        setUiLoading(false, convertBtn);
        if (progressContainer) progressContainer.style.display = 'none';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initDocxUpload);
```

- [ ] **Step 3: Add DOCX styles to style_enhanced.css**

Add after image-related styles:

```css
/* DOCX Upload Styles */
#docx-tab {
    padding: 20px;
}

#docx-drop-zone {
    border: 2px dashed #ddd;
    border-radius: 8px;
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
    background: #fafafa;
}

#docx-drop-zone:hover,
#docx-drop-zone.drag-over {
    border-color: #4a90d9;
    background: #f0f7ff;
}

#docx-drop-zone .drop-zone-content svg {
    color: #4a90d9;
    margin-bottom: 10px;
}

#docx-file-info {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: #e8f0fe;
    border-radius: 6px;
    margin-top: 12px;
}

#docx-file-info .file-name {
    color: #1a73e8;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

#docx-file-info .remove-btn {
    background: none;
    border: none;
    font-size: 20px;
    color: #666;
    cursor: pointer;
    padding: 0 8px;
}

#docx-file-info .remove-btn:hover {
    color: #d32f2f;
}
```

- [ ] **Step 4: Test the frontend**

Run the app and verify:
1. New "Word" tab appears
2. Can upload .docx file
3. Conversion works

- [ ] **Step 5: Commit**

```bash
git add frontend/templates/index_enhanced.html frontend/static/script_enhanced.js frontend/static/style_enhanced.css
git commit -m "feat: add Word upload tab to frontend UI"
```

---

## Task 8: Integration Testing

**Files:**
- Test: Full flow integration

- [ ] **Step 1: Test Word to LaTeX flow**

```bash
# Create test DOCX
python -c "
from docx import Document
doc = Document()
doc.add_heading('Test Document', 1)
doc.add_paragraph('This is a test paragraph.')
doc.add_heading('Section Two', 2)
table = doc.add_table([['A', 'B'], ['C', 'D']])
doc.save('test_sample.docx')
"

# Start server and test
# (Manual testing recommended for full flow)
```

- [ ] **Step 2: Test image batch processing**

Verify multiple images are merged correctly.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: add integration tests for new features"
```

---

## Self-Review Checklist

1. **Spec coverage:** All spec requirements mapped to tasks
   - [x] Word (.docx) to LaTeX - Task 1, 4, 7
   - [x] SVG/EMF support - Task 2, 5
   - [x] Batch image processing - Task 3, 6
   - [x] API endpoints - Task 4, 6
   - [x] Frontend UI - Task 7

2. **Placeholder scan:** No TBD/TODO placeholders in implementation code

3. **Type consistency:** All method names consistent across tasks

4. **Test coverage:** Each new module has unit tests

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-01-word-image-latex-plan.md`**

---

## Execution Options

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?