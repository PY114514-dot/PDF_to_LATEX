import asyncio
from unittest.mock import Mock

from PIL import Image

from config import settings
from ocr_client import OCRClient


def test_pix2text_result_normalizes_structured_formula_output():
    result = [
        {'text': 'The identity is'},
        {'latex': r'\[E = mc^2\]'},
    ]

    assert OCRClient._pix2text_result_to_text(result) == 'The identity is\n\\[E = mc^2\\]'


def test_mixed_formula_page_routes_to_pix2text(monkeypatch):
    client = OCRClient()
    image = Image.new('RGB', (16, 16), 'white')
    monkeypatch.setattr(client, 'detect_content_type', lambda _: 'mixed')
    monkeypatch.setattr(client, 'pix2text_ocr', lambda *_args, **_kwargs: (r'\[x^2 + y^2\]', 0.82))
    monkeypatch.setattr(settings, 'ENABLE_PIX2TEXT_FORMULA_ROUTING', True)
    monkeypatch.setattr(settings, 'OCR_PROVIDER', 'mixed')
    client.provider = 'mixed'

    result = asyncio.run(client.recognize(image))

    assert result['provider'] == 'pix2text'
    assert result['text'] == r'\[x^2 + y^2\]'


def test_pix2text_empty_result_falls_back_to_paddle(monkeypatch):
    client = OCRClient()
    image = Image.new('RGB', (16, 16), 'white')
    monkeypatch.setattr(client, 'pix2text_ocr', lambda *_args, **_kwargs: ('', 0.0))
    monkeypatch.setattr(client, 'paddle_ocr', lambda *_args, **_kwargs: ('Recovered text', 0.76))
    monkeypatch.setattr(settings, 'ENABLE_PIX2TEXT_PADDLE_FALLBACK', True)

    result = asyncio.run(client.recognize(image, force_provider='pix2text'))

    assert result['provider'] == 'paddle'
    assert result['text'] == 'Recovered text'


def test_pix2text_accepts_pillow_or_numpy_recognize_contract(monkeypatch):
    client = OCRClient()
    engine = Mock()
    engine.recognize.side_effect = [TypeError('expects array'), [{'text': 'x = 1'}]]
    monkeypatch.setattr(client, '_get_pix2text_engine', lambda: engine)

    text, quality = client.pix2text_ocr(Image.new('RGB', (16, 16), 'white'))

    assert text == 'x = 1'
    assert quality > 0
    assert engine.recognize.call_count == 2
