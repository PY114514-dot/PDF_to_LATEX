#!/usr/bin/env python3
"""测试异步调用是否正常工作"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio

def test_sync_call_async():
    """测试从同步函数调用async函数"""
    async def async_func():
        print("async_func started")
        await asyncio.sleep(1)
        print("async_func completed")
        return "result"

    def sync_caller():
        print("sync_caller creating event loop")
        new_loop = asyncio.new_event_loop()
        result = new_loop.run_until_complete(async_func())
        new_loop.close()
        print(f"sync_caller got result: {result}")
        return result

    result = sync_caller()
    print(f"Final result: {result}")
    return True

def test_nested_async_call():
    """测试嵌套的async调用"""
    async def inner_async():
        print("inner_async started")
        await asyncio.sleep(0.5)
        print("inner_async completed")
        return "inner_result"

    async def outer_async():
        print("outer_async calling inner")
        result = await inner_async()
        print(f"outer_async got: {result}")
        return f"outer_{result}"

    def sync_caller_outer():
        print("sync_caller_outer creating event loop")
        new_loop = asyncio.new_event_loop()
        result = new_loop.run_until_complete(outer_async())
        new_loop.close()
        print(f"sync_caller_outer got result: {result}")
        return result

    result = sync_caller_outer()
    print(f"Final result: {result}")
    return True

if __name__ == '__main__':
    print("=== Test 1: Sync call async ===")
    test_sync_call_async()
    print()
    print("=== Test 2: Nested async call ===")
    test_nested_async_call()
    print()
    print("All tests passed!")