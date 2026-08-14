#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLMClient 单元测试（使用 mock）
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from clients import LLMClient


class TestLLMClient:
    """测试 LLMClient 基础功能"""

    @pytest.fixture
    def client(self):
        """创建一个测试用 LLMClient 实例"""
        return LLMClient(
            api_key="test-key",
            base_url="https://api.test.com/v1/chat/completions",
            model="test-model",
            timeout=30.0
        )

    def test_client_initialization(self, client):
        """测试客户端初始化"""
        assert client.api_key == "test-key"
        assert client.base_url == "https://api.test.com/v1/chat/completions"
        assert client.model == "test-model"
        assert client.timeout == 30.0
        assert client.default_extra_params == {}

    def test_client_with_default_params(self):
        """测试带默认参数的客户端"""
        client = LLMClient(
            api_key="test-key",
            base_url="https://api.test.com/v1/chat/completions",
            model="test-model",
            default_extra_params={"temperature": 0.8}
        )
        assert client.default_extra_params == {"temperature": 0.8}

    @pytest.mark.asyncio
    async def test_chat_request_structure(self, client):
        """测试聊天请求结构"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"}
        ]

        # Mock httpx.AsyncClient
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello! How can I help?"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await client.chat(messages, temperature=0.7)

            # 验证请求结构
            call_args = mock_client.post.call_args
            assert call_args is not None

            # 验证 URL
            assert call_args[0][0] == "https://api.test.com/v1/chat/completions"

            # 验证请求体
            request_body = call_args[1]['json']
            assert request_body['model'] == "test-model"
            assert request_body['messages'] == messages
            assert request_body['temperature'] == 0.7

    @pytest.mark.asyncio
    async def test_chat_with_custom_params(self, client):
        """测试带自定义参数的聊天"""
        messages = [{"role": "user", "content": "Test"}]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Result"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await client.chat(
                messages,
                temperature=0.5,
                max_tokens=1000,
                top_p=0.9
            )

            request_body = mock_client.post.call_args[1]['json']
            assert request_body['temperature'] == 0.5
            assert request_body['max_tokens'] == 1000

    @pytest.mark.asyncio
    async def test_chat_timeout(self, client):
        """测试超时处理"""
        messages = [{"role": "user", "content": "Test"}]

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = Exception("timeout")

            with pytest.raises(Exception, match="请求失败"):
                await client.chat(messages)

    def test_extract_content(self):
        """测试内容提取静态方法"""
        response = {
            "choices": [{"message": {"content": "Hello World"}}]
        }
        content = LLMClient.extract_content(response)
        assert content == "Hello World"

    def test_extract_content_empty(self):
        """测试空响应处理"""
        response = {}
        content = LLMClient.extract_content(response)
        assert content == ""

    def test_extract_content_none(self):
        """测试 None 内容处理"""
        response = {"choices": [{"message": {"content": None}}]}
        content = LLMClient.extract_content(response)
        assert content == ""


class TestDeepseekClient:
    """测试 DeepSeek 模型客户端"""

    def test_deepseek_chat_exists(self):
        """验证 deepseek_chat 实例存在"""
        from clients import deepseek_chat
        assert deepseek_chat is not None
        assert deepseek_chat.model == "deepseek-chat"

    def test_deepseek_reasoner_exists(self):
        """验证 deepseek_reasoner 实例存在"""
        from clients import deepseek_reasoner
        assert deepseek_reasoner is not None
        assert deepseek_reasoner.model == "deepseek-reasoner"


class TestDoubaoClient:
    """测试豆包模型客户端"""

    def test_doubao_exists(self):
        """验证 doubao 实例存在"""
        from clients import doubao
        assert doubao is not None
        assert "doubao" in doubao.model or "seed" in doubao.model.lower()