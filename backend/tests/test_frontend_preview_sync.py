"""Regression coverage for editor-to-preview navigation wiring."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_editor_double_click_sends_preview_line_focus_message():
    script = (ROOT / 'frontend' / 'static' / 'script_enhanced.js').read_text(encoding='utf-8')

    assert "latexEditor.addEventListener('dblclick', focusLatexPreviewAtEditorLine)" in script
    assert "type: 'latex-preview-focus-line'" in script


def test_embedded_preview_keeps_source_line_anchors_and_highlights_target():
    template = (ROOT / 'frontend' / 'templates' / 'latex_render.html').read_text(encoding='utf-8')

    assert 'SOURCE_LINE:${startsAt}' in template
    assert 'data-source-line' in template
    assert "target.classList.add('source-line-focus')" in template


def test_page_review_can_locate_latex_marker_and_source_pdf_page():
    script = (ROOT / 'frontend' / 'static' / 'script_enhanced.js').read_text(encoding='utf-8')

    assert 'function focusReviewPage(pageNum)' in script
    assert 'sourcePdfFrame.src = `${sourcePdfObjectUrl}#page=${pageNum}`' in script
    assert "row.dataset.reviewPage = String(page.page)" in script


def test_page_review_inspector_only_replaces_the_selected_page_block():
    template = (ROOT / 'frontend' / 'templates' / 'index_enhanced.html').read_text(encoding='utf-8')
    script = (ROOT / 'frontend' / 'static' / 'script_enhanced.js').read_text(encoding='utf-8')

    assert 'id="pageInspectorLatex"' in template
    assert 'function getLatexPageBlock(pageNum' in script
    assert '第 ${pageNum} 页修改已应用' in script


def test_page_review_loads_source_text_on_demand():
    template = (ROOT / 'frontend' / 'templates' / 'index_enhanced.html').read_text(encoding='utf-8')
    script = (ROOT / 'frontend' / 'static' / 'script_enhanced.js').read_text(encoding='utf-8')

    assert 'id="pageInspectorExtract"' in template
    assert "fetch('/api/review-page-source'" in script
