#!/usr/bin/env python3
"""测试模拟 _process_pages_batch 的行为"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import asyncio

# 模拟 clients.py 中的 chat 方法
class MockClient:
    async def chat(self, messages, temperature=None, max_tokens=None, **kwargs):
        print(f"MockClient.chat called with {len(messages)} messages")
        await asyncio.sleep(0.5)  # 模拟网络延迟
        return {'choices': [{'message': {'content': 'translated text'}}]}

# 模拟 PDF2LaTeXEnhanced.translate_batch_async
class MockPDFConverter:
    def __init__(self):
        self.client = MockClient()
        self.BATCH_SIZE = 12

    async def translate_batch_async(self, page_extractions, batch_start, batch_end, total_batches, total_pages):
        print(f"translate_batch_async called: batch_start={batch_start}, batch_end={batch_end}")

        # 模拟API调用
        response = await self.client.chat(
            messages=[
                {"role": "system", "content": "translate"},
                {"role": "user", "content": "translate this"}
            ],
            temperature=0.3,
            max_tokens=16000
        )
        print(f"translate_batch_async got response")
        return ["translated_page_1", "translated_page_2"]

    def _process_pages_batch(self, page_extractions, page_latex_list, start_page, end_page, total_batches, total_pages, quality_mode):
        """模拟原来的 _process_pages_batch"""
        print(f"_process_pages_batch called: start_page={start_page}, end_page={end_page}")

        new_loop = asyncio.new_event_loop()
        batch_results = new_loop.run_until_complete(
            self.translate_batch_async(
                page_extractions,
                start_page,
                end_page,
                total_batches,
                total_pages
            )
        )
        new_loop.close()
        print(f"_process_pages_batch returning: {len(batch_results)} results")
        return batch_results, 100

# 测试
def test():
    converter = MockPDFConverter()

    # 模拟 convert_pdf 中的批处理循环
    pages = list(range(26))
    batch_size = converter.BATCH_SIZE
    total_batches = (len(pages) + batch_size - 1) // batch_size

    print(f"Total pages: {len(pages)}, batch_size: {batch_size}, total_batches: {total_batches}")
    print(f"BATCH_CONCURRENCY = 1, so processing sequentially")

    latex_content = []
    processed_pages = 0

    # 分批并发执行（每个批次同步处理）
    for batch_idx in range(total_batches):
        start_page = batch_idx * batch_size
        end_page = min(start_page + batch_size, len(pages))

        print(f"\n--- Processing batch {batch_idx + 1}/{total_batches}: pages {start_page}-{end_page} ---")

        batch_latex, chars_used = converter._process_pages_batch(
            None,  # page_extractions
            None,  # page_latex_list
            start_page,
            end_page,
            total_batches,
            len(pages),
            'standard'
        )
        print(f"Batch {batch_idx + 1} completed, got {len(batch_latex)} results")
        latex_content.extend(batch_latex)
        processed_pages += len(batch_latex)

    print(f"\n=== Final result: {processed_pages} pages processed ===")

if __name__ == '__main__':
    test()