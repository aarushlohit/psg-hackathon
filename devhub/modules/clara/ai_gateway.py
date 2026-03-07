"""CLARA AI gateway — multi-provider AI with budget & token controls.

Supported providers:
  - openai     (requires OPENAI_API_KEY)
  - claude     (requires ANTHROPIC_API_KEY)
  - openrouter (requires OPENROUTER_API_KEY)
  - (hidden)   a fourth provider exists for those who know where to look
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

logger = logging.getLogger(__name__)

_PROVIDER_ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "claude": "https://api.anthropic.com/v1/messages",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

_PROVIDER_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "claude": "claude-sonnet-4-20250514",
    "openrouter": "openai/gpt-4o-mini",
}


def _get_env_key(provider: str) -> Optional[str]:
    """Resolve the API key from environment."""
    mapping = {
        "openai": "OPENAI_API_KEY",
        "claude": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_var = mapping.get(provider)
    if env_var:
        return os.environ.get(env_var)
    return None


@dataclass
class AIConfig:
    """Per-user AI configuration."""
    enabled: bool = False
    provider: str = "openai"
    budget: float = 10.0      # max spend in $
    token_limit: int = 10000  # max tokens per session
    request_limit: int = 100  # max requests per session
    tokens_used: int = 0
    cost_spent: float = 0.0
    requests_made: int = 0


@dataclass
class AIResponse:
    content: str = ""
    tokens_used: int = 0
    cost: float = 0.0
    provider: str = ""
    error: str = ""


class AIGateway:
    """Routes AI queries to the configured provider with billing safety."""

    def __init__(self) -> None:
        self._configs: dict[str, AIConfig] = {}  # username -> config

    def get_config(self, username: str) -> AIConfig:
        if username not in self._configs:
            self._configs[username] = AIConfig()
        return self._configs[username]

    def enable(self, username: str, provider: str = "openai") -> str:
        cfg = self.get_config(username)
        known = list(_PROVIDER_ENDPOINTS.keys())
        # Easter egg: those who know can use it
        if provider == "pollinations":
            cfg.enabled = True
            cfg.provider = provider
            return "AI enabled."
        if provider not in known:
            return f"Unknown provider. Available: {', '.join(known)}"
        key = _get_env_key(provider)
        if not key:
            env_var = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY",
                       "openrouter": "OPENROUTER_API_KEY"}.get(provider, "")
            return f"Set {env_var} environment variable first."
        cfg.enabled = True
        cfg.provider = provider
        return f"AI enabled with provider: {provider}"

    def set_budget(self, username: str, budget: float) -> str:
        cfg = self.get_config(username)
        cfg.budget = budget
        return f"AI budget set to ${budget:.2f}"

    def set_limit(self, username: str, limit: int) -> str:
        cfg = self.get_config(username)
        cfg.token_limit = limit
        return f"AI token limit set to {limit}"

    def get_usage(self, username: str) -> dict:
        cfg = self.get_config(username)
        return {
            "enabled": cfg.enabled,
            "provider": cfg.provider,
            "budget": cfg.budget,
            "budget_used": cfg.cost_spent,
            "budget_remaining": max(0, cfg.budget - cfg.cost_spent),
            "tokens_used": cfg.tokens_used,
            "token_limit": cfg.token_limit,
            "requests_made": cfg.requests_made,
            "request_limit": cfg.request_limit,
        }

    async def ask(self, username: str, question: str) -> AIResponse:
        """Send a question to the configured AI provider."""
        cfg = self.get_config(username)
        if not cfg.enabled:
            return AIResponse(error="AI not enabled. Use: ai enable <provider>")

        # Budget / limit checks
        if cfg.cost_spent >= cfg.budget:
            return AIResponse(error=f"Budget exhausted (${cfg.budget:.2f})")
        if cfg.requests_made >= cfg.request_limit:
            return AIResponse(error=f"Request limit reached ({cfg.request_limit})")

        provider = cfg.provider

        # Easter egg provider
        if provider == "pollinations":
            return await self._ask_pollinations(username, question)

        return await self._ask_standard(username, question, provider)

    async def summarize(self, username: str, messages: list[str]) -> AIResponse:
        """Summarise recent chat messages."""
        text = "\n".join(messages[-50:])
        prompt = f"Summarize this chat conversation concisely:\n\n{text}"
        return await self.ask(username, prompt)

    # ── standard providers (OpenAI-compatible) ──

    async def _ask_standard(self, username: str, question: str, provider: str) -> AIResponse:
        cfg = self.get_config(username)
        api_key = _get_env_key(provider)
        if not api_key:
            return AIResponse(error=f"No API key for {provider}")

        endpoint = _PROVIDER_ENDPOINTS[provider]
        model = _PROVIDER_MODELS[provider]

        if provider == "claude":
            return await self._ask_claude(username, question, api_key)

        # OpenAI / OpenRouter compatible
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": question}],
            "max_tokens": min(2000, cfg.token_limit - cfg.tokens_used),
        }).encode()

        try:
            req = Request(endpoint, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            # Rough cost estimate: $0.15 / 1M tokens for mini models
            cost = tokens * 0.00000015

            cfg.tokens_used += tokens
            cfg.cost_spent += cost
            cfg.requests_made += 1

            return AIResponse(content=content, tokens_used=tokens, cost=cost, provider=provider)
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"{provider} error: {exc}")

    async def _ask_claude(self, username: str, question: str, api_key: str) -> AIResponse:
        cfg = self.get_config(username)
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        body = json.dumps({
            "model": _PROVIDER_MODELS["claude"],
            "max_tokens": min(2000, cfg.token_limit - cfg.tokens_used),
            "messages": [{"role": "user", "content": question}],
        }).encode()

        try:
            req = Request(_PROVIDER_ENDPOINTS["claude"], data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            cost = tokens * 0.0000003

            cfg.tokens_used += tokens
            cfg.cost_spent += cost
            cfg.requests_made += 1

            return AIResponse(content=content, tokens_used=tokens, cost=cost, provider="claude")
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"Claude error: {exc}")

    # ── Easter egg provider ──

    async def _ask_pollinations(self, username: str, question: str) -> AIResponse:
        """Free AI via Pollinations — no key needed."""
        cfg = self.get_config(username)
        endpoint = "https://text.pollinations.ai/openai"
        headers = {"Content-Type": "application/json"}
        body = json.dumps({
            "model": "openai",
            "messages": [{"role": "user", "content": question}],
        }).encode()

        try:
            req = Request(endpoint, data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())

            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", len(question.split()) + len(content.split()))
            cfg.tokens_used += tokens
            cfg.requests_made += 1

            return AIResponse(content=content, tokens_used=tokens, cost=0.0, provider="pollinations")
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"AI error: {exc}")
