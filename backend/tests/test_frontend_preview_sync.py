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
