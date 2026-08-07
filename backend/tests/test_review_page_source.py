"""Minimal API guardrail coverage for the on-demand review text endpoint."""

from app_enhanced import app


def test_review_source_requires_original_pdf():
    client = app.test_client()

    response = client.post('/api/review-page-source', data={})

    assert response.status_code == 400
    assert '原始 PDF' in response.get_json()['error']
