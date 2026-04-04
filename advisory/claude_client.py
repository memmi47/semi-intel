from __future__ import annotations
"""
Claude API Client
==================
Anthropic Claude API 래퍼
- 동기/스트리밍 호출
- 재시도 로직
- 토큰 사용량 추적
- 대화 히스토리 관리
"""

import os
import time
from dataclasses import dataclass, field
from typing import Generator

from loguru import logger

try:
    import anthropic
except ImportError:
    anthropic = None
    logger.warning("anthropic SDK not installed. Run: pip install anthropic")


@dataclass
class TokenUsage:
    """토큰 사용량 추적"""
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
    """대화 메시지"""
    role: str       # "user" or "assistant"
    content: str


class ClaudeClient:
    """
    Claude API 클라이언트

    사용법:
        client = ClaudeClient(api_key="sk-ant-...")
        response = client.chat("반도체 사이클 분석해줘", system="You are...")
        # 또는 스트리밍
        for chunk in client.stream("분석해줘", system="..."):
            print(chunk, end="", flush=True)
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    def __init__(self, api_key: str | None = None,
                 model: str | None = None,
                 max_tokens: int = 4096):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model or os.getenv("CLAUDE_MODEL", self.DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.usage = TokenUsage()
        self.history: list[Message] = []
        self._client = None

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set")

    def _get_client(self):
        """Lazy init — SDK 없을 때 임포트 에러 방지"""
        if self._client is None:
            if anthropic is None:
                raise ImportError("anthropic SDK required. Run: pip install anthropic")
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def chat(self, user_message: str,
             system: str = "",
             include_history: bool = True,
             temperature: float = 0.3) -> str:
        """
        동기 호출 — 전체 응답을 한번에 반환

        Args:
            user_message: 사용자 메시지
            system: 시스템 프롬프트
            include_history: 이전 대화 포함 여부
            temperature: 창의성 (0=결정적, 1=창의적)
        """
        client = self._get_client()

        # 메시지 구성
        messages = []
        if include_history:
            messages.extend([{"role": m.role, "content": m.content} for m in self.history])
        messages.append({"role": "user", "content": user_message})

        # 재시도 로직
        for attempt in range(self.MAX_RETRIES):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=messages,
                    temperature=temperature,
                )

                # 토큰 추적
                self.usage.add(
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )

                # 응답 추출
                text = response.content[0].text

                # 히스토리 추가
                self.history.append(Message("user", user_message))
                self.history.append(Message("assistant", text))

                logger.debug(f"Claude API: {response.usage.input_tokens}+{response.usage.output_tokens} tokens")
                return text

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    wait = self.RETRY_DELAY * (attempt + 1)
                    logger.warning(f"API call failed (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"API call failed after {self.MAX_RETRIES} attempts: {e}")
                    raise

    def stream(self, user_message: str,
               system: str = "",
               include_history: bool = True,
               temperature: float = 0.3) -> Generator[str, None, None]:
        """
        스트리밍 호출 — 토큰 단위로 yield

        사용법:
            for chunk in client.stream("질문"):
                print(chunk, end="", flush=True)
        """
        client = self._get_client()

        messages = []
        if include_history:
            messages.extend([{"role": m.role, "content": m.content} for m in self.history])
        messages.append({"role": "user", "content": user_message})

        full_response = []

        try:
            with client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,
                temperature=temperature,
            ) as stream:
                for text in stream.text_stream:
                    full_response.append(text)
                    yield text

                # 최종 메시지에서 usage 추출
                final = stream.get_final_message()
                self.usage.add(
                    final.usage.input_tokens,
                    final.usage.output_tokens,
                )

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield f"\n[Error: {e}]"
            return

        # 히스토리 추가
        complete = "".join(full_response)
        self.history.append(Message("user", user_message))
        self.history.append(Message("assistant", complete))

    def clear_history(self):
        """대화 히스토리 초기화"""
        self.history.clear()
        logger.debug("Conversation history cleared")

    def trim_history(self, max_messages: int = 20):
        """히스토리 길이 제한 (오래된 메시지부터 제거)"""
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]
            logger.debug(f"History trimmed to {max_messages} messages")

    def get_usage_summary(self) -> str:
        return self.usage.summary()
