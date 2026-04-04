from __future__ import annotations
"""
Multi-Provider LLM Client
===========================
Claude, OpenAI, Google Gemini 중 선택하여 사용 가능

.env 설정:
    LLM_PROVIDER=google        # google / anthropic / openai
    GOOGLE_API_KEY=AIza...
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-...
    LLM_MODEL=                 # 비워두면 각 프로바이더 기본 모델 사용
"""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator

from loguru import logger


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_t: int, output_t: int):
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_calls += 1

    def summary(self) -> str:
        return (f"Calls: {self.total_calls} | "
                f"In: {self.input_tokens:,} | Out: {self.output_tokens:,} | "
                f"Total: {self.total_tokens:,}")


@dataclass
class Message:
    role: str
    content: str


class BaseLLMClient(ABC):
    """LLM 클라이언트 추상 베이스"""

    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.usage = TokenUsage()
        self.history: list[Message] = []

    @abstractmethod
    def _call(self, messages: list[dict], system: str, temperature: float) -> tuple[str, int, int]:
        """프로바이더별 API 호출 구현. Returns (text, input_tokens, output_tokens)"""
        pass

    @abstractmethod
    def _stream(self, messages: list[dict], system: str, temperature: float) -> Generator[str, None, None]:
        """프로바이더별 스트리밍 구현"""
        pass

    def chat(self, user_message: str, system: str = "",
             include_history: bool = True, temperature: float = 0.3) -> str:
        messages = []
        if include_history:
            messages.extend([{"role": m.role, "content": m.content} for m in self.history])
        messages.append({"role": "user", "content": user_message})

        for attempt in range(self.MAX_RETRIES):
            try:
                text, in_t, out_t = self._call(messages, system, temperature)
                self.usage.add(in_t, out_t)
                self.history.append(Message("user", user_message))
                self.history.append(Message("assistant", text))
                return text
            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_DELAY * (attempt + 1)
                    logger.warning(f"API call failed (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"API call failed after {self.MAX_RETRIES} attempts: {e}")
                    raise

    def stream(self, user_message: str, system: str = "",
               include_history: bool = True, temperature: float = 0.3) -> Generator[str, None, None]:
        messages = []
        if include_history:
            messages.extend([{"role": m.role, "content": m.content} for m in self.history])
        messages.append({"role": "user", "content": user_message})

        full_response = []
        try:
            for chunk in self._stream(messages, system, temperature):
                full_response.append(chunk)
                yield chunk
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield f"\n[Error: {e}]"
            return

        complete = "".join(full_response)
        self.history.append(Message("user", user_message))
        self.history.append(Message("assistant", complete))

    def clear_history(self):
        self.history.clear()

    def trim_history(self, max_messages: int = 20):
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def get_usage_summary(self) -> str:
        return self.usage.summary()


# ============================================================
# Anthropic Claude
# ============================================================

class AnthropicClient(BaseLLMClient):
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, api_key: str, model: str | None = None, max_tokens: int = 4096):
        super().__init__(api_key, model or self.DEFAULT_MODEL, max_tokens)
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic SDK 필요. 실행: pip install anthropic")

    def _call(self, messages, system, temperature):
        response = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            system=system, messages=messages, temperature=temperature,
        )
        text = response.content[0].text
        return text, response.usage.input_tokens, response.usage.output_tokens

    def _stream(self, messages, system, temperature):
        with self._client.messages.stream(
            model=self.model, max_tokens=self.max_tokens,
            system=system, messages=messages, temperature=temperature,
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
            self.usage.add(final.usage.input_tokens, final.usage.output_tokens)


# ============================================================
# OpenAI (GPT-4o, GPT-4-turbo, etc.)
# ============================================================

class OpenAIClient(BaseLLMClient):
    DEFAULT_MODEL = "gpt-4o"

    def __init__(self, api_key: str, model: str | None = None, max_tokens: int = 4096):
        super().__init__(api_key, model or self.DEFAULT_MODEL, max_tokens)
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai SDK 필요. 실행: pip install openai")

    def _call(self, messages, system, temperature):
        # OpenAI는 system을 messages 안에 포함
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        response = self._client.chat.completions.create(
            model=self.model, max_tokens=self.max_tokens,
            messages=all_messages, temperature=temperature,
        )
        text = response.choices[0].message.content
        in_t = response.usage.prompt_tokens if response.usage else 0
        out_t = response.usage.completion_tokens if response.usage else 0
        return text, in_t, out_t

    def _stream(self, messages, system, temperature):
        all_messages = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        stream = self._client.chat.completions.create(
            model=self.model, max_tokens=self.max_tokens,
            messages=all_messages, temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ============================================================
# Google Gemini
# ============================================================

class GoogleClient(BaseLLMClient):
    DEFAULT_MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str, model: str | None = None, max_tokens: int = 4096):
        super().__init__(api_key, model or self.DEFAULT_MODEL, max_tokens)
        try:
            from google import genai
            self._genai_client = genai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("google-genai SDK 필요. 실행: pip install google-genai")

    def _call(self, messages, system, temperature):
        from google.genai import types

        # Gemini 메시지 형식 변환
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            temperature=temperature,
            max_output_tokens=self.max_tokens,
        )

        response = self._genai_client.models.generate_content(
            model=self.model, contents=contents, config=config,
        )
        text = response.text or ""
        # Gemini usage 추적
        in_t = getattr(response.usage_metadata, 'prompt_token_count', 0) if response.usage_metadata else 0
        out_t = getattr(response.usage_metadata, 'candidates_token_count', 0) if response.usage_metadata else 0
        return text, in_t, out_t

    def _stream(self, messages, system, temperature):
        from google.genai import types

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            temperature=temperature,
            max_output_tokens=self.max_tokens,
        )

        for chunk in self._genai_client.models.generate_content_stream(
            model=self.model, contents=contents, config=config,
        ):
            if chunk.text:
                yield chunk.text


# ============================================================
# Factory: .env 설정 기반 자동 생성
# ============================================================

def create_llm_client(
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
) -> BaseLLMClient:
    """
    .env 설정 또는 인자 기반으로 LLM 클라이언트 생성

    Usage:
        client = create_llm_client()  # .env 자동 감지
        client = create_llm_client(provider="openai", api_key="sk-...")
    """
    provider = provider or os.getenv("LLM_PROVIDER", "google").lower()
    model = model or os.getenv("LLM_MODEL", "") or None

    if provider == "anthropic":
        key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        logger.info(f"LLM Provider: Anthropic Claude ({model or AnthropicClient.DEFAULT_MODEL})")
        return AnthropicClient(key, model, max_tokens)

    elif provider == "openai":
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("OPENAI_API_KEY not set")
        logger.info(f"LLM Provider: OpenAI ({model or OpenAIClient.DEFAULT_MODEL})")
        return OpenAIClient(key, model, max_tokens)

    elif provider == "google":
        key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            raise ValueError("GOOGLE_API_KEY not set")
        logger.info(f"LLM Provider: Google Gemini ({model or GoogleClient.DEFAULT_MODEL})")
        return GoogleClient(key, model, max_tokens)

    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Use: anthropic, openai, google")


# ============================================================
# Provider 정보 (매뉴얼/도움말용)
# ============================================================

PROVIDER_INFO = {
    "anthropic": {
        "name": "Anthropic Claude",
        "signup_url": "https://console.anthropic.com/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_prefix": "sk-ant-",
        "pip_package": "anthropic",
        "default_model": "claude-sonnet-4-20250514",
        "pricing": "입력 $3/M tokens, 출력 $15/M tokens (Sonnet)",
        "free_tier": "가입 시 $5 크레딧 제공 (변동 가능)",
    },
    "openai": {
        "name": "OpenAI GPT",
        "signup_url": "https://platform.openai.com/",
        "api_key_env": "OPENAI_API_KEY",
        "key_prefix": "sk-",
        "pip_package": "openai",
        "default_model": "gpt-4o",
        "pricing": "입력 $2.5/M tokens, 출력 $10/M tokens (GPT-4o)",
        "free_tier": "가입 시 $5 크레딧 제공 (변동 가능)",
    },
    "google": {
        "name": "Google Gemini",
        "signup_url": "https://aistudio.google.com/apikey",
        "api_key_env": "GOOGLE_API_KEY",
        "key_prefix": "AIza",
        "pip_package": "google-genai",
        "default_model": "gemini-2.0-flash",
        "pricing": "Flash: 무료 티어 포함. Pro: 입력 $1.25/M, 출력 $5/M",
        "free_tier": "Gemini Flash 무료 티어 (분당 15회, 일 1,500회)",
    },
}
