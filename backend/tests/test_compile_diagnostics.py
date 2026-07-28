import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app_enhanced import _latex_compile_errors


def test_extracts_tex_live_file_line_error():
    errors = _latex_compile_errors(
        r"C:/temporary/document.tex:12: Undefined control sequence."
    )

    assert errors == [{'line': 12, 'message': 'Undefined control sequence.'}]


def test_extracts_classic_latex_error_with_line_number():
    errors = _latex_compile_errors(
        "! Missing $ inserted.\nl.8 \\section{broken}"
    )

    assert errors == [{'line': 8, 'message': 'Missing $ inserted.'}]
