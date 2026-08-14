#!/usr/bin/env python3
"""测试实际API调用"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

import asyncio
from clients import deepseek_v4

async def test_deepseek_chat():
    """测试DeepSeek API调用"""
    print("Testing DeepSeek chat...")
    try:
        response = await deepseek_v4.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'hello' in one word."}
            ],
            temperature=0.3,
            max_tokens=100
        )
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_sync_call():
    """测试从同步函数调用async chat"""
    print("Testing sync call to async chat...")
    try:
        new_loop = asyncio.new_event_loop()
        result = new_loop.run_until_complete(test_deepseek_chat())
        new_loop.close()
        print(f"Result: {result}")
        return result
    except Exception as e:
        print(f"Sync call error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_sync_call()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")