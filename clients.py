"""
LLM大模型API统一调用管理
包含Gemini, Canopy Wave, OpenAI, ChatGPT, 智谱GLM,豆包,DeepSeek
支持同步和异步调用
支持多种模型选择
支持多种temperature设置
支持多种最大tokens设置
"""

import asyncio
import httpx
from typing import Dict, Any, List, Optional
from config import settings

class LLMClient:

    """
    大模型客户端

封装所有大模型通用的内容：
    1. API KEY
    2. 请求地址
    3. 模型名称
    4. 超时时间
    5. 调用方法
    6. 默认额外参数（如 thinking, reasoning_effort 等）
    """

    def __init__(
        self, 
        api_key: str, 
        base_url: str, 
        model: str, 
        timeout: float = 1000.0,
        default_extra_params: Dict[str, Any] = None
    ):
        """
        初始化大模型客户端
        
        Args:
            api_key: API密钥
            base_url: 请求地址
            model: 模型名称
            timeout: 超时时间
            default_extra_params: 默认额外参数，如：
                - {"thinking": {"type": "enabled"}}  # 智谱 Thinking 模式
                - {"reasoning_effort": "medium"}     # GPT-5.2 推理努力
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.default_extra_params = default_extra_params or {}

    # =============================== 基础聊天 ===================================
    async def chat(
        self, 
        messages: List[dict[str, str]], 
        temperature: float = None,  # None 时不发送，GPT-5.2 + reasoning_effort 时必须为 None
        max_tokens: int = None,
        **kwargs
    ) -> Dict[str, Any]:
    
        """
        基础聊天接口：

        Args:
            messages: 消息列表
                格式：[{"role": "system", "content": "你是一位自身的数学题目创作专家"}, {"role": "user", "content": "请创作一道数学题目"}]
                role可以是："system", "user", "assistant"
            temperature: 温度参数，None表示不发送（GPT-5.2 + reasoning_effort 时必须为 None）
            max_tokens: 最大tokens数，None表示不限制 
            **kwargs: 其他参数，如：
                - thinking: {"type": "enabled"}  # 智谱 Thinking 模式
                - reasoning_effort: "medium"     # GPT-5.2 推理努力
                - stream, n, stop, presence_penalty, frequency_penalty 等

        Returns:
            API原始响应，格式类似：
            {
                "choices":[
                    {"messages": {"content": "回复内容"}}
                    ]
            }
        """

        # 合并默认额外参数和传入参数（传入参数优先）
        merged_params = {**self.default_extra_params, **kwargs}

        # 构建请求体
        request_body = {
            "model": self.model,
            "messages": messages,
            **merged_params
        }

        # 只有设置了 temperature 时，才添加到请求体（GPT-5.2 + reasoning_effort 时不能设置）
        if temperature is not None:
            request_body["temperature"] = temperature

        # 只有设置了 max_tokens 时，才添加到请求体
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens

        # 添加重试机制
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                ) as client:
                    response = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json=request_body
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.ConnectError as e:
                last_error = f"连接失败: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # 递增延迟
                    continue
                else:
                    raise Exception(f"所有连接尝试均失败 ({max_retries}次): {last_error}")
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                else:
                    raise Exception(f"请求超时 ({max_retries}次): {last_error}")
            except httpx.HTTPStatusError as e:
                # HTTP 错误（4xx, 5xx）不重试
                raise Exception(f"HTTP错误 {e.response.status_code}: {e.response.text}")
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                else:
                    raise Exception(f"请求失败 ({max_retries}次): {last_error}")

    # =============================== 自动续写 ===================================
    async def chat_with_auto_continue(
        self,
        messages: List[dict[str, str]],
        temperature: float = 0.8,
        max_tokens: int = None,
        max_rounds: int = 10,
        continue_prompt: str = "请从上文中断处继续，不要重复已生成内容",
        sleep_between_rounds: float = 0.5,
        **kwargs
    ) -> str:
        """
        自动续写聊天（token 用尽时自动继续）
        
        适用于：生成长内容、题目变形等需要大量输出的场景
        
        Args:
            messages: 初始消息列表
            temperature: 温度参数
            max_tokens: 每轮最大 token 数
            max_rounds: 最大续写轮数
            continue_prompt: 续写提示词
            sleep_between_rounds: 轮次间隔（秒）
            **kwargs: 其他参数
            
        Returns:
            完整的生成文本（所有轮次拼接）
        """

        full_text = ""
        current_messages = list(messages)

        for round_idx in range(max_rounds):
            print(f"[LLMClient] 开始第 {round_idx + 1}/{max_rounds} 轮续写...")

            # 构建请求体
            request_body = {
                "model": self.model,
                "messages": current_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs
            }

            # 发送请求
            async with httpx.AsyncClient(timeout = None) as client:
                response = await client.post(
                    self.base_url,
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json = request_body
                )
                response.raise_for_status()
                data = response.json()

            # 解析响应
            round_text = ""
            finish_reason = None 

            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]

                # 提取内容
                if "message" in choice and "content" in choice["message"]:
                    round_text = choice["message"]["content"] or ""

                # 提取结束原因
                finish_reason = choice.get("finish_reason", None)

            # 累加文本
            full_text += round_text

            #判断是否需要续写
            if finish_reason != "length":
                print(f"[LLMClient] 生成完成，finish_reason={finish_reason}")
                break

            print(f"[LLMClient] Token 用尽，准备续写...")

            # 添加本轮回复到消息历史
            current_messages.append({"role": "assistant", "content": round_text})

            # 添加续写提示
            current_messages.append({"role": "user", "content": continue_prompt})

            # 轮次间隔
            await asyncio.sleep(sleep_between_rounds)
        
        return full_text

    # =============================== 图片输入（OCR） ===================================
    async def chat_with_image(
        self,
        prompt: str,
        image_url: Optional[str] = None,
        image_base64: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = 2000,
        **kwargs
    ) -> Dict[str, Any]:
        """
        带图片的聊天（支持 Vision 模型）
        
        适用于：OCR 识别、图像理解、图表分析等
        
        Args:
            prompt: 文本提示词
            image_url: 图片 URL（与 image_base64 二选一）
            image_base64: 图片 Base64 编码（与 image_url 二选一）
            temperature: 温度参数（OCR 建议用低温度）
            max_tokens: 最大 token 数
            **kwargs: 其他参数
            
        Returns:
            API 原始响应
        """
        if not image_url and not image_base64:
            raise ValueError("必须提供 image_url 或 image_base64")
        
        # 构建消息内容（多模态格式）
        content = [
            {"type": "text", "text": prompt}
        ]
        
        # 添加图片
        if image_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        else:
            # Base64 格式
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        
        # 构建消息
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        # 构建请求体
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens is not None:
            request_body["max_tokens"] = max_tokens
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=request_body
            )
            response.raise_for_status()
            return response.json()
    
    # ==================== 辅助方法 ====================
    
    @staticmethod
    def extract_content(response: Dict[str, Any]) -> str:
        """
        从 API 响应中提取文本内容
        
        Args:
            response: API 原始响应
            
        Returns:
            文本内容
        """
        if "choices" in response and len(response["choices"]) > 0:
            return response["choices"][0]["message"]["content"] or ""
        return ""
    
    @staticmethod
    def extract_thinking_content(response: Dict[str, Any]) -> tuple:
        """
        提取 Thinking 模式的内容（适用于智谱等支持 thinking 的模型）
        
        Args:
            response: API 原始响应
            
        Returns:
            (reasoning_content, content) 元组
        """
        reasoning = ""
        content = ""
        if "choices" in response and len(response["choices"]) > 0:
            message = response["choices"][0].get("message", {})
            reasoning = message.get("reasoning_content", "") or ""
            content = message.get("content", "") or ""
        return reasoning, content

deepseek_math = LLMClient(
    api_key = settings.CANOPY_WAVE_API_KEY,
    base_url = "https://api.canopywave.io/v1/chat/completions",
    model = "deepseek-ai/DeepSeek-Math-V2",
    timeout = 600.0
)

gpt4o = LLMClient(
    api_key = settings.OPENAI_API_KEY,
    base_url = "https://api.openai.com/v1/chat/completions",
    model = "gpt-4o",
    timeout = 1000.0
)

doubao = LLMClient(
    api_key=settings.DOUBAO_API_KEY,
    base_url="https://ark.cn-beijing.volces.com/api/v3/chat/completions",
    model="doubao-seed-1-6-thinking-250715",
    timeout = 1000.0
)


# ==================== 带默认参数的模型实例 ====================

# 智谱 GLM-4.6 Thinking 模式（默认开启 thinking）
glm46_thinking = LLMClient(
    api_key=settings.ZHIPU_API_KEY,
    base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
    model="glm-4.6",
    timeout=300.0,
    default_extra_params={"thinking": {"type": "enabled"}, "max_tokens": 65536}
)

# 智谱 GLM-4.7 Thinking 模式（默认开启 thinking）
glm47_thinking = LLMClient(
    api_key=settings.ZHIPU_API_KEY,
    base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
    model="glm-4.7",
    timeout=300.0,
    default_extra_params={"thinking": {"type": "enabled"}, "max_tokens": 65536}
)

# GPT-5.2 带推理控制（Chat Completions API + reasoning_effort 参数）
gpt52_with_reasoning = LLMClient(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-5.2",
    timeout=1000.0,
    default_extra_params={"reasoning_effort": "low"}
)

# GPT-4o 通用模型（用于答案对比等简单任务）
gpt4o = LLMClient(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-4o",
    timeout=300.0,
    default_extra_params={}
)

# GPT-4o-mini 快速模型（用于生成选项等简单任务）
gpt4o_mini = LLMClient(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-4o-mini",
    timeout=60.0,
    default_extra_params={}
)


# ==================== Responses API 客户端（支持 web_search 等工具） ====================

class ResponsesAPIClient:
    """
    OpenAI Responses API 客户端
    
    用于调用支持 web_search 等工具的 Responses API。
    这与 Chat Completions API 格式完全不同：
    - 使用 /v1/responses 而不是 /v1/chat/completions
    - 使用 input 而不是 messages
    - 支持 tools 参数（如 web_search）
    - 响应格式不同，使用 output_text
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1/responses",
        model: str = "gpt-5.2",
        timeout: float = 120.0,
        default_tools: List[Dict[str, Any]] = None
    ):
        """
        初始化 Responses API 客户端
        
        Args:
            api_key: OpenAI API 密钥
            base_url: API 地址（默认为 OpenAI 官方地址）
            model: 模型名称
            timeout: 超时时间（秒）
            default_tools: 默认工具列表，如 [{"type": "web_search"}]
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.default_tools = default_tools or []
    
    async def create(
        self,
        input_text: str,
        tools: List[Dict[str, Any]] = None,
        tool_choice: str = "auto",
        reasoning: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建 Responses API 请求
        
        Args:
            input_text: 输入文本（相当于 Chat Completions 的 messages）
            tools: 工具列表，如 [{"type": "web_search"}]
            tool_choice: 工具选择策略（"auto", "required", "none"）
            reasoning: 推理参数，如 {"effort": "medium"}
            **kwargs: 其他参数
            
        Returns:
            API 原始响应
        """
        # 合并默认工具和传入工具
        merged_tools = tools if tools is not None else self.default_tools
        
        # 构建请求体
        request_body = {
            "model": self.model,
            "input": input_text,
            **kwargs
        }
        
        # 添加工具（如果有）
        if merged_tools:
            request_body["tools"] = merged_tools
            request_body["tool_choice"] = tool_choice
        
        # 添加推理参数（如果有）
        if reasoning:
            request_body["reasoning"] = reasoning
        
        # 添加重试机制
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
                ) as client:
                    response = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json"
                        },
                        json=request_body
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.RemoteProtocolError as e:
                last_error = f"服务器断连: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))  # 递增延迟: 2s, 4s, 6s
                    continue
            except httpx.ConnectError as e:
                last_error = f"连接失败: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
            except httpx.TimeoutException as e:
                last_error = f"请求超时: {str(e)}"
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
            except httpx.HTTPStatusError as e:
                # HTTP 错误不重试
                raise Exception(f"HTTP错误 {e.response.status_code}: {e.response.text}")
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
        
        raise Exception(f"请求失败 ({max_retries}次): {last_error}")
    
    async def web_search(
        self,
        query: str,
        reasoning_effort: str = "medium",
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行联网搜索查询
        
        Args:
            query: 搜索查询文本
            reasoning_effort: 推理努力程度（"low", "medium", "high"）
            **kwargs: 其他参数
            
        Returns:
            包含搜索结果的响应
        """
        return await self.create(
            input_text=query,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            reasoning={"effort": reasoning_effort},
            **kwargs
        )
    
    @staticmethod
    def extract_output_text(response: Dict[str, Any]) -> str:
        """
        从 Responses API 响应中提取输出文本
        
        Args:
            response: API 原始响应
            
        Returns:
            输出文本
        """
        # 优先使用顶层的 output_text
        if "output_text" in response:
            return response["output_text"]
        
        # 否则从 output 数组中提取
        if "output" in response and isinstance(response["output"], list):
            for item in response["output"]:
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for c in content:
                        if c.get("type") == "output_text":
                            return c.get("text", "")
        
        return ""
    
    @staticmethod
    def extract_citations(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 Responses API 响应中提取引用信息
        
        Args:
            response: API 原始响应
            
        Returns:
            引用列表，每个引用包含 url, title 等信息
        """
        citations = []
        
        if "output" in response and isinstance(response["output"], list):
            for item in response["output"]:
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for c in content:
                        if c.get("type") == "output_text":
                            annotations = c.get("annotations", [])
                            for ann in annotations:
                                if ann.get("type") == "url_citation":
                                    citations.append({
                                        "url": ann.get("url"),
                                        "title": ann.get("title"),
                                        "start_index": ann.get("start_index"),
                                        "end_index": ann.get("end_index")
                                    })
        
        return citations


# ==================== Responses API 模型实例 ====================

# GPT-5.2 Research 模式（支持 web_search 联网搜索）
gpt52_research = ResponsesAPIClient(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.openai.com/v1/responses",
    model="gpt-5.2",
    timeout=120.0,
    default_tools=[{"type": "web_search"}]
)

# ==================== 直接访问的模型 ====================

# GPT-4o Vision（用于 OCR，直接访问 OpenAI）
gpt4o_vision = LLMClient(
    api_key=settings.OPENAI_API_KEY,
    base_url="https://api.openai.com/v1/chat/completions",
    model="gpt-4o",
    timeout=60.0
)

# Gemini 3 Pro（用于深度变形，直接访问 Google API）
gemini3_pro = LLMClient(
    api_key=settings.GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    model="gemini-3-pro-preview",
    timeout=None  # 无超时限制，允许长时间运行
)

# DeepSeek Chat（通用对话模型）
deepseek_chat = LLMClient(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1/chat/completions",
    model="deepseek-chat",
    timeout=600.0,
    default_extra_params={}
)

# DeepSeek Reasoner（推理模型）
deepseek_reasoner = LLMClient(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1/chat/completions",
    model="deepseek-reasoner",
    timeout=600.0,
    default_extra_params={}
)