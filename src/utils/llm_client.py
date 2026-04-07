# coding=utf-8
"""
AI 客户端模块

基于 LangChain OpenAI 的统一 AI 模型接口
支持 OpenAI、DeepSeek、Azure 等兼容 ChatML 的模型
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

# 加载 .env 文件（项目根目录）
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class AIClient:
    """统一的 AI 客户端（基于 LangChain OpenAI）"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 AI 客户端

        Args:
            config: AI 配置字典
                - MODEL: 模型标识（格式: provider/model_name 或模型名称）
                   支持: gpt-4, gpt-3.5-turbo, deepseek-chat, etc.
                - API_KEY: API 密钥
                - API_BASE: API 基础 URL（可选，用于代理或兼容 API）
                - TEMPERATURE: 采样温度 (0.0-2.0)
                - MAX_TOKENS: 最大生成 token 数
                - TIMEOUT: 请求超时时间（秒）
                - MAX_RETRIES: 最大重试次数
        """
        self.model_name = config.get("MODEL") or os.environ.get("MODEL", "gpt-3.5-turbo")
        self.api_key = config.get("API_KEY") or os.environ.get("API_KEY", "")
        self.api_base = config.get("API_BASE") or os.environ.get("AI_API_BASE", "")
        self.temperature = config.get("TEMPERATURE", 0.7)
        self.max_tokens = config.get("MAX_TOKENS", 4096)
        self.timeout = config.get("TIMEOUT", 120)
        self.max_retries = config.get("MAX_RETRIES", 3)

        # 初始化 LangChain ChatOpenAI 客户端
        self._init_llm()

    def _init_llm(self):
        """初始化 LangChain LLM 实例"""
        llm_params: Dict[str, Any] = {
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens if self.max_tokens > 0 else None,
            "max_retries": self.max_retries,
            "request_timeout": self.timeout,
        }

        # 添加 API Key（如果有）
        if self.api_key:
            llm_params["api_key"] = self.api_key

        # 添加 API Base（如果有，用于代理或兼容 API）
        if self.api_base:
            llm_params["base_url"] = self.api_base

        self.llm = ChatOpenAI(**llm_params)

    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        调用 AI 模型进行对话

        Args:
            messages: 消息列表，格式: [{"role": "system/user/assistant", "content": "..."}]
            **kwargs: 额外参数，会覆盖默认配置
                - temperature: 采样温度
                - max_tokens: 最大 token 数
                - stop: 停止词列表

        Returns:
            str: AI 响应内容

        Raises:
            Exception: API 调用失败时抛出异常
        """
        # 将字典格式的消息转换为 LangChain 消息对象
        langchain_messages = self._convert_messages(messages)

        # 构建调用参数
        call_params: Dict[str, Any] = {}
        if "temperature" in kwargs:
            call_params["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            call_params["max_tokens"] = kwargs["max_tokens"]
        if "stop" in kwargs:
            call_params["stop"] = kwargs["stop"]

        # 调用 LangChain LLM
        response: ChatResult = self.llm.invoke(langchain_messages, **call_params)

        # 提取响应内容
        if isinstance(response, ChatResult):
            content = response.generations[0].message.content
        else:
            content = response.content if hasattr(response, 'content') else str(response)

        return content or ""

    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[BaseMessage]:
        """
        将字典格式消息转换为 LangChain 消息对象

        Args:
            messages: [{"role": "system/user/assistant", "content": "..."}]

        Returns:
            List[BaseMessage]: LangChain 消息对象列表
        """
        langchain_messages: List[BaseMessage] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))
            else:
                # 未知角色默认为用户消息
                langchain_messages.append(HumanMessage(content=content))

        return langchain_messages

    def validate_config(self) -> tuple[bool, str]:
        """
        验证配置是否有效

        Returns:
            tuple: (是否有效, 错误信息)
        """
        if not self.model_name:
            return False, "未配置 AI 模型（model）"

        if not self.api_key and not self.api_base:
            return False, "未配置 AI API Key，请在环境变量 API_KEY 或 AI_API_BASE 中设置"

        return True, ""

    def get_model_name(self) -> str:
        """获取当前配置的模型名称"""
        return self.model_name
    
if __name__ == "__main__":
    # 创建 AI 模型实例
    ai_client = AIClient({
        "TEMPERATURE": 0.7,
        "MAX_TOKENS": 4096,
        "TIMEOUT": 120,
        "MAX_RETRIES": 3
    })
    res = ai_client.chat([
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你好"}
    ])
    print(res)
