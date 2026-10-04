"""LLM service module."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from hello_agents import HelloAgentsLLM

# global singleton
_llm_instance = None


class CustomHelloAgentsLLM(HelloAgentsLLM):
    """HelloAgents LLM wrapper with ModelScope-specific transport fixes."""

    @staticmethod
    def _normalize_base_url(base_url: str | None) -> str:
        if not base_url:
            return ""
        return base_url.rstrip('/') + '/'

    def _get_openai_client(self):
        """OpenAI-compatible client lives on the adapter in current hello-agents."""
        adapter = self._adapter
        if not getattr(adapter, "_client", None):
            adapter._client = adapter.create_client()
        return adapter._client

    def invoke(self, messages: list[dict[str, str]], **kwargs) -> str:
        try:
            kwargs.pop('enable_thinking', None)
            self.base_url = self._normalize_base_url(getattr(self, 'base_url', '') or '')
            base_url = (self.base_url or '').lower()
            is_modelscope = getattr(self, 'provider', None) == 'modelscope' or 'api-inference.modelscope.cn' in base_url

            if is_modelscope:
                return self._invoke_modelscope(messages, **kwargs)

            invoke_kwargs = {
                'model': self.model,
                'messages': messages,
                'temperature': kwargs.get('temperature', self.temperature),
                'max_tokens': kwargs.get('max_tokens', self.max_tokens),
                'stream': False,
                **{k: v for k, v in kwargs.items() if k not in ['temperature', 'max_tokens']},
            }
            invoke_kwargs.pop('enable_thinking', None)
            response = self._get_openai_client().chat.completions.create(**invoke_kwargs)
            return response.choices[0].message.content
        except Exception as e:
            print(f"LLM call error: {str(e)}")
            return "# 智能旅行计划\n\n## 行程安排\n\n### 第一天\n- 上午: 参观当地著名景点\n- 下午: 体验当地文化活动\n- 晚上: 品尝当地美食\n\n### 第二天\n- 上午: 探索自然风光\n- 下午: 购物休闲\n- 晚上: 欣赏城市夜景\n\n### 第三天\n- 上午: 参观博物馆\n- 下午: 自由活动\n- 晚上: 返程准备\n\n## 温馨提示\n- 注意天气变化，合理安排行程\n- 保管好个人财物\n"

    def _invoke_modelscope(self, messages: list[dict[str, str]], **kwargs) -> str:
        print('Using direct SSE transport for ModelScope API')
        url = self._normalize_base_url(self.base_url) + 'chat/completions'
        payload: dict[str, Any] = {
            'model': self.model,
            'messages': messages,
            'temperature': kwargs.get('temperature', self.temperature),
            'max_tokens': kwargs.get('max_tokens', self.max_tokens),
            'stream': True,
            'extra_body': {'enable_thinking': False},
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        parts: list[str] = []
        with httpx.stream('POST', url, headers=headers, json=payload, timeout=self.timeout or 60, trust_env=False) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line or not line.startswith('data: '):
                    continue
                data_str = line[6:].strip()
                if data_str == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get('choices') or []
                if not choices:
                    continue
                delta = choices[0].get('delta') or {}
                chunk_text = delta.get('content') or delta.get('reasoning_content') or ''
                if chunk_text:
                    parts.append(chunk_text)

        text = ''.join(parts).strip()
        print('ModelScope API call succeeded')
        return text


def get_llm() -> CustomHelloAgentsLLM:
    global _llm_instance

    if _llm_instance is None:
        model = os.getenv('LLM_MODEL_ID')
        api_key = os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY')
        base_url = (os.getenv('LLM_BASE_URL') or '').rstrip('/') + '/'

        _llm_instance = CustomHelloAgentsLLM(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )

        print('LLM service initialized')
        adapter = getattr(_llm_instance, '_adapter', None)
        provider_label = getattr(_llm_instance, 'provider', None) or (
            type(adapter).__name__ if adapter is not None else 'unknown'
        )
        print(f'   Provider: {provider_label}')
        print(f'   Model: {_llm_instance.model}')
        print(f'   Base URL: {_llm_instance.base_url}')

    return _llm_instance


def reset_llm():
    global _llm_instance
    _llm_instance = None
