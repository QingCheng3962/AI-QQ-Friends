"""OpenAI-compatible / Anthropic chat client (retry on failure)."""
from __future__ import annotations

import json
from typing import List, Optional, Tuple

import httpx

from .config import DEFAULT_BASE_URLS

DEFAULT_TIMEOUT = 30.0


class LLMError(Exception):
    pass


def normalize_base_url(base_url: str) -> str:
    s = (base_url or '').strip()
    while s.endswith('/'):
        s = s[:-1]
    return s + '/'


def clean_api_key(key) -> str:
    cleaned = ''.join(ch for ch in str(key or '')
                      if 0x21 <= ord(ch) <= 0x7E).strip()
    if not cleaned:
        raise LLMError('API 密钥为空或只包含无效字符，请重新粘贴。')
    return cleaned


def _message_pairs(messages: List[dict]) -> List[Tuple[str, str]]:
    out = []
    for m in messages:
        role = m.get('role') or 'user'
        content = m.get('content')
        out.append((role, str(content if content is not None else '')))
    return out


class _BaseProvider:
    def __init__(self, cfg, api_key: str):
        self.cfg = cfg
        raw = api_key if api_key is not None and str(api_key).strip() else cfg.apiKey
        self.api_key = clean_api_key(raw)
        self.model = cfg.model or 'gpt-4o-mini'
        self.temperature = cfg.temperature
        self.max_tokens = cfg.maxTokens
        self.timeout = max(cfg.timeoutSeconds or DEFAULT_TIMEOUT, 5)
        self.retry_count = cfg.retryCount or 0
        self._client = httpx.Client(timeout=self.timeout)

    def _post(self, endpoint: str, headers: dict, body: dict) -> str:
        headers = dict(headers)
        headers.setdefault('Content-Type', 'application/json; charset=utf-8')
        json_bytes = json.dumps(body, ensure_ascii=False).encode('utf-8', errors='replace')
        last_err: Optional[Exception] = None
        for _ in range(self.retry_count + 1):
            try:
                resp = self._client.post(endpoint, headers=headers, content=json_bytes)
                if 200 <= resp.status_code < 300:
                    return resp.text
                last_err = LLMError(f'HTTP {resp.status_code}: {resp.text[:500]}')
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise last_err if last_err else LLMError('unknown failure')

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass


class OpenAIProvider(_BaseProvider):
    def __init__(self, cfg, base_url: str, api_key: str):
        super().__init__(cfg, api_key)
        self.endpoint = normalize_base_url(base_url) + 'chat/completions'

    def send(self, system_prompt: str, messages: List[dict]) -> str:
        body = {'model': self.model, 'temperature': self.temperature,
                'max_tokens': self.max_tokens, 'messages': []}
        if system_prompt:
            body['messages'].append({'role': 'system', 'content': system_prompt})
        for role, content in _message_pairs(messages):
            body['messages'].append({'role': role, 'content': content})
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + self.api_key}
        text = self._post(self.endpoint, headers, body)
        try:
            data = json.loads(text)
            choices = data.get('choices') or []
            if not choices:
                raise LLMError('No choices in response: ' + text[:300])
            return (choices[0].get('message') or {}).get('content') or ''
        except json.JSONDecodeError:
            raise LLMError('Invalid JSON response: ' + text[:300])


class AnthropicProvider(_BaseProvider):
    def __init__(self, cfg, base_url: str, api_key: str):
        super().__init__(cfg, api_key)
        self.endpoint = normalize_base_url(base_url) + 'v1/messages'

    def send(self, system_prompt: str, messages: List[dict]) -> str:
        body = {'model': self.model, 'max_tokens': self.max_tokens,
                'temperature': self.temperature, 'messages': []}
        if system_prompt:
            body['system'] = system_prompt
        for role, content in _message_pairs(messages):
            body['messages'].append({'role': 'assistant' if role == 'assistant' else 'user',
                                     'content': content})
        headers = {'Content-Type': 'application/json', 'x-api-key': self.api_key,
                   'anthropic-version': '2023-06-01'}
        text = self._post(self.endpoint, headers, body)
        try:
            data = json.loads(text)
            content = data.get('content') or []
            if not content:
                raise LLMError('No content in Anthropic response: ' + text[:300])
            return content[0].get('text') or ''
        except json.JSONDecodeError:
            raise LLMError('Invalid JSON response: ' + text[:300])


def create_provider(cfg, api_key_override: Optional[str] = None):
    provider = (cfg.provider or 'openai').lower()
    base_url = (cfg.baseUrl or '').strip() or DEFAULT_BASE_URLS.get(provider, '')
    if not base_url:
        raise LLMError('聊天 AI 需要 baseUrl，请在「AI 配置」里填写 provider 或 baseUrl。')
    key = api_key_override if api_key_override is not None else cfg.apiKey
    if provider == 'anthropic':
        return AnthropicProvider(cfg, base_url, key or '')
    return OpenAIProvider(cfg, base_url, key or '')
