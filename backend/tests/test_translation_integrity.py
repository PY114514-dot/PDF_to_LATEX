"""Regression tests for lossless page translation and algorithm detection."""

import asyncio
import sys
from pathlib import Path


backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from pdf2latex_enhanced import PDF2LaTeXEnhanced


def _converter_without_client():
    """The methods below do not require a configured external model client."""
    return PDF2LaTeXEnhanced.__new__(PDF2LaTeXEnhanced)


def test_batch_parser_refuses_to_guess_page_boundaries_from_paragraphs():
    converter = _converter_without_client()

    result = converter._parse_batch_translation(
        "第一段翻译\n\n第二段翻译", [(0, 0), (1, 1)]
    )

    assert result == []


def test_batch_translation_backfills_pages_omitted_by_model_response():
    converter = _converter_without_client()
    converter._chapter_boundaries = []

    async def partial_chunk(_texts, info, _total):
        return [(info[0][0], "第一个页面的翻译")]

    async def fallback(texts, info, _total):
        return [(page, f"补译：{text}") for text, (page, _display) in zip(texts, info)]

    converter._translate_chunk = partial_chunk
    converter._fallback_translate_pages = fallback

    result = asyncio.run(converter.translate_batch_async(
        ["page one", "page two"], [(0, 0), (1, 1)], 2,
    ))

    assert dict(result) == {0: "第一个页面的翻译", 1: "补译：page two"}


def test_algorithm_marker_requires_title_and_control_flow_signal():
    converter = _converter_without_client()

    algorithm = "Algorithm 1 Solver\nInput: A, b\nInitialize x\nwhile k < K\nreturn x"
    ordinary_list = "1. Initialize the experiment\n2. Return to the introduction"

    assert converter._attach_algorithm_context(algorithm).startswith("[ALGORITHM_CONTEXT]")
    assert converter._attach_algorithm_context(ordinary_list) == ordinary_list
