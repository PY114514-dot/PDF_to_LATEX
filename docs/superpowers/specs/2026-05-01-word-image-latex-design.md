# Word & Image to LaTeX Enhancement Design

**Date:** 2026-05-01
**Status:** Approved

## Overview

Extend the PDF2LATEX system with two new capabilities:
1. Word (.docx) to LaTeX conversion
2. Enhanced image to LaTeX conversion

---

## 1. Word (.docx) to LaTeX

### Architecture

```
.docx file
    │
    ▼
┌─────────────────────────────┐
│  python-docx                 │
│  - Extract paragraphs        │
│  - Extract headings (H1-H6)  │
│  - Extract tables             │
│  - Extract lists (ul/ol)      │
│  - Extract math equations     │
│  - Detect images (skip)      │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│  Structure Converter         │
│  - Headings → \section{}     │
│  - Paragraphs → text         │
│  - Tables → LaTeX tables     │
│  - Lists → itemize/enumerate │
│  - Math → $...$ or \[...\]   │
└─────────────────────────────┘
    │
    ├──────────────────────────┐
    │                          │
    ▼                          ▼
Simple Content           Complex Content
(text, headings)         (tables, math)
    │                          │
    ▼                          ▼
Direct Output          LLM Optimization
    │                     (deepseek-math)
    │                          │
    └──────────┬───────────────┘
               │
               ▼
      ┌────────────────┐
      │ Merge & Sanitize│
      └────────────────┘
               │
               ▼
         Final .tex file
```

### Module: `docx2latex_converter.py`

**Class:** `Docx2LaTeXConverter`

**Methods:**
| Method | Description |
|--------|-------------|
| `convert(docx_path, output_path)` | Main conversion entry point |
| `extract_content(docx_path)` | Extract structured content from .docx |
| `convert_structure(content)` | Convert to LaTeX structure |
| `process_complex_elements(tables, equations)` | Send complex elements to LLM |
| `sanitize_latex(latex_content)` | Clean and validate output |

**Dependencies:**
- `python-docx` - DOCX parsing
- Existing LLM clients from `clients.py`
- Existing `latex_utils.py` for sanitization

### API Endpoint

```
POST /api/convert-docx
  - Input: docx file (multipart/form-data)
  - Output: { success, latex, download_url, messages }
```

### Supported Elements

| DOCX Element | LaTeX Output |
|--------------|--------------|
| Heading 1-6 | \section{}, \subsection{}, etc. |
| Paragraph | Plain text with \\\\ for breaks |
| Bulleted list | \begin{itemize} ... \end{itemize} |
| Numbered list | \begin{enumerate} ... \end{enumerate} |
| Table | \begin{table} with \begin{tabular} |
| Inline math | $...$ |
| Display math | \[ ... \] |
| Image | **Skipped** (not processed) |

### Processing Strategy

**Step 1 - Fast Conversion (no LLM):**
- Extract structure
- Convert simple text, headings, lists
- Generate "draft" LaTeX

**Step 2 - LLM Optimization (async):**
- Identify complex tables (merged cells, nested tables)
- Identify math equations
- Send to LLM for quality improvement
- Merge optimized content

---

## 2. Image to LaTeX Enhancement

### Current State

Existing `image2latex_enhanced.py` provides:
- Tesseract OCR + DeepSeek Vision hybrid
- Single image conversion

### Enhancements

#### A. Vector Image Support (SVG/EMF)

**Implementation:**
1. Use `cairosvg` for SVG → PNG conversion
2. Use `pyemf` or `libsodium` for EMF → PNG conversion
3. Feed rasterized image to existing OCR pipeline

**New Module:** `vector2raster.py`

```python
class VectorToRasterConverter:
    def svg_to_png(svg_path, output_path, dpi=300)
    def emf_to_png(emf_path, output_path, dpi=300)
```

#### B. Batch Processing

**Enhancement to existing API:**
```
POST /api/convert-images
  - Input: multiple image files
  - Output: combined LaTeX document
```

**Behavior:**
- Process each image individually
- Combine results into single .tex with \section{} per image
- Return as single downloadable .tex file

**New Module:** `image_batch_merger.py`

#### C. Formula Recognition Enhancement

**Improvements:**
1. Pre-process image: contrast enhancement, deskew
2. Use math-specific prompt engineering for LLM
3. Post-process: validate LaTeX math syntax

**Module update:** `image2latex_enhanced.py`

#### D. Table Structure Recovery

**Improvements:**
1. Detect table grids and borders
2. Identify row/column headers
3. Preserve alignment information

---

## 3. File Structure Changes

```
backend/
  ├── docx2latex_converter.py   [NEW]
  ├── vector2raster.py          [NEW]
  ├── image_batch_merger.py     [NEW]
  ├── image2latex_enhanced.py   [MODIFIED - enhancements]
  └── app_enhanced.py            [MODIFIED - new endpoints]

frontend/
  ├── static/script_enhanced.js [MODIFIED - docx upload UI]
  ├── static/style_enhanced.css [MODIFIED - new upload styles]
  └── templates/index_enhanced.html [MODIFIED - tab for docx]
```

---

## 4. API Changes

### New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convert-docx` | POST | Convert .docx to LaTeX |
| `/api/convert-docx-async` | POST | Async .docx conversion |
| `/api/convert-images` | POST | Batch image to LaTeX |

### Endpoint Details

**POST /api/convert-docx**
```json
Request:
{
  "file": <multipart docx file>,
  "translate": false,
  "model": "deepseek-math"
}

Response:
{
  "success": true,
  "latex": "\\section{...}",
  "download_url": "/api/download/xxx.tex",
  "messages": ["converted 5 paragraphs", "optimized 2 tables"]
}
```

**POST /api/convert-images**
```json
Request:
{
  "files": [<image1>, <image2>, ...],
  "merge": true,
  "model": "deepseek-math"
}

Response:
{
  "success": true,
  "latex": "\\section{Image 1}...\\section{Image 2}...",
  "download_url": "/api/download/xxx.tex",
  "count": 3
}
```

---

## 5. Frontend Changes

### New Upload Tab

Add tabbed interface:
- **Tab 1:** PDF Upload
- **Tab 2:** Image Upload (single/batch)
- **Tab 3:** Word Upload (.docx)

### Word Upload UI

```html
<div class="upload-tab" id="docx-tab">
  <h3>Word to LaTeX</h3>
  <input type="file" accept=".docx" id="docx-input">
  <div class="options">
    <label><input type="checkbox" id="docx-translate"> Translate to Chinese</label>
  </div>
  <button id="convert-docx-btn">Convert</button>
</div>
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Invalid .docx file | Return error: "Invalid DOCX file" |
| Encrypted .docx | Return error: "DOCX is encrypted" |
| No text content | Return warning + empty LaTeX |
| LLM failure | Fall back to basic conversion |
| SVG/EMF parse error | Return error with supported formats |

---

## 7. Testing Requirements

- Unit test for `docx2latex_converter.py`
- Unit test for `vector2raster.py`
- Integration test for `/api/convert-docx`
- Integration test for batch image processing