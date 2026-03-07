"""CLARA server — AI gateway (OpenAI, Claude, OpenRouter, + secret Pollinations)."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from clara.config.settings import settings
from clara.database.db import ClaraDB
from clara.server.protocol import Action, Packet

logger = logging.getLogger("clara.messages")

_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "claude": "https://api.anthropic.com/v1/messages",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
_MODELS = {
    "openai": "gpt-4o-mini",
    "claude": "claude-sonnet-4-20250514",
    "openrouter": "openai/gpt-4o-mini",
}


def _api_key(provider: str) -> Optional[str]:
    mapping = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY",
               "openrouter": "OPENROUTER_API_KEY"}
    return os.environ.get(mapping.get(provider, ""))


@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = "openai"
    budget: float = settings.ai.default_budget
    token_limit: int = settings.ai.default_token_limit
    request_limit: int = settings.ai.default_request_limit
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
    """Routes AI queries to configured provider with budget safety."""

    def __init__(self, db: ClaraDB) -> None:
        self.db = db
        self._configs: dict[str, AIConfig] = {}

    def _cfg(self, username: str) -> AIConfig:
        if username not in self._configs:
            self._configs[username] = AIConfig()
        return self._configs[username]

    # ── handlers ──

    async def handle_enable(self, client, pkt: Packet) -> None:
        provider = pkt.content.strip() or "openai"
        cfg = self._cfg(client.username)
        known = list(_ENDPOINTS.keys())

        if provider == "pollinations":
            cfg.enabled = True
            cfg.provider = provider
            await client.send(Packet.system(
                "⚠ AI queries may incur API costs. Control with 'ai budget' and 'ai limit'."
            ))
            await asyncio.sleep(2)
            await client.send(Packet.ok("AI enabled."))
            return

        if provider not in known:
            await client.send(Packet.error(f"Unknown provider. Available: {', '.join(known)}"))
            return
        if not _api_key(provider):
            env_var = {"openai": "OPENAI_API_KEY", "claude": "ANTHROPIC_API_KEY",
                       "openrouter": "OPENROUTER_API_KEY"}.get(provider, "")
            await client.send(Packet.error(f"Set {env_var} environment variable first."))
            return

        cfg.enabled = True
        cfg.provider = provider
        await client.send(Packet.system(
            "⚠ AI queries may incur API costs. Control with 'ai budget' and 'ai limit'."
        ))
        await asyncio.sleep(2)
        await client.send(Packet.ok(f"AI enabled with provider: {provider}"))

    async def handle_ask(self, client, pkt: Packet) -> None:
        question = pkt.content.strip()
        if not question:
            await client.send(Packet.error("Usage: ai ask <question>"))
            return
        resp = await self._query(client.username, question)
        if resp.error:
            await client.send(Packet.error(resp.error))
        else:
            self.db.log_ai_usage(client.username, resp.provider, resp.tokens_used, resp.cost)
            await client.send(Packet(
                action=Action.AI_RESPONSE, content=resp.content,
                data={"tokens": resp.tokens_used, "cost": f"${resp.cost:.6f}",
                       "provider": resp.provider},
            ))

    async def handle_summarize(self, client, pkt: Packet) -> None:
        if not client.room:
            await client.send(Packet.error("Join a room first."))
            return
        msgs = self.db.get_recent_messages(client.room, limit=50)
        text = "\n".join(f"{m.sender}: {m.content}" for m in msgs)
        resp = await self._query(client.username, f"Summarize this chat:\n\n{text}")
        if resp.error:
            await client.send(Packet.error(resp.error))
        else:
            self.db.log_ai_usage(client.username, resp.provider, resp.tokens_used, resp.cost)
            await client.send(Packet(action=Action.AI_RESPONSE, content=resp.content))

    async def handle_usage(self, client, pkt: Packet) -> None:
        cfg = self._cfg(client.username)
        usage = {
            "enabled": cfg.enabled, "provider": cfg.provider,
            "budget": cfg.budget, "budget_used": cfg.cost_spent,
            "budget_remaining": max(0, cfg.budget - cfg.cost_spent),
            "tokens_used": cfg.tokens_used, "token_limit": cfg.token_limit,
            "requests_made": cfg.requests_made, "request_limit": cfg.request_limit,
        }
        await client.send(Packet.ok(json.dumps(usage), **usage))

    async def handle_budget(self, client, pkt: Packet) -> None:
        try:
            amount = float(pkt.content.strip().replace("$", ""))
        except (ValueError, TypeError):
            await client.send(Packet.error("Usage: ai budget <amount>"))
            return
        self._cfg(client.username).budget = amount
        await client.send(Packet.ok(f"AI budget set to ${amount:.2f}"))

    async def handle_limit(self, client, pkt: Packet) -> None:
        try:
            limit = int(pkt.content.strip())
        except (ValueError, TypeError):
            await client.send(Packet.error("Usage: ai limit <number>"))
            return
        self._cfg(client.username).token_limit = limit
        await client.send(Packet.ok(f"AI token limit set to {limit}"))

    # ── core query ──

    async def _query(self, username: str, question: str) -> AIResponse:
        cfg = self._cfg(username)
        if not cfg.enabled:
            return AIResponse(error="AI not enabled. Use: ai enable <provider>")
        if cfg.cost_spent >= cfg.budget:
            return AIResponse(error=f"Budget exhausted (${cfg.budget:.2f})")
        if cfg.requests_made >= cfg.request_limit:
            return AIResponse(error=f"Request limit reached ({cfg.request_limit})")

        if cfg.provider == "pollinations":
            return await self._ask_pollinations(username, question)
        if cfg.provider == "claude":
            return await self._ask_claude(username, question)
        return await self._ask_openai_compat(username, question, cfg.provider)

    async def _ask_openai_compat(self, username: str, question: str, provider: str) -> AIResponse:
        cfg = self._cfg(username)
        api_key = _api_key(provider)
        if not api_key:
            return AIResponse(error=f"No API key for {provider}")
        body = json.dumps({
            "model": _MODELS[provider],
            "messages": [{"role": "user", "content": question}],
            "max_tokens": min(2000, cfg.token_limit - cfg.tokens_used),
        }).encode()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        try:
            req = Request(_ENDPOINTS[provider], data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)
            cost = tokens * 0.00000015
            cfg.tokens_used += tokens
            cfg.cost_spent += cost
            cfg.requests_made += 1
            return AIResponse(content=content, tokens_used=tokens, cost=cost, provider=provider)
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"{provider} error: {exc}")

    async def _ask_claude(self, username: str, question: str) -> AIResponse:
        cfg = self._cfg(username)
        api_key = _api_key("claude")
        if not api_key:
            return AIResponse(error="No API key for claude")
        body = json.dumps({
            "model": _MODELS["claude"],
            "max_tokens": min(2000, cfg.token_limit - cfg.tokens_used),
            "messages": [{"role": "user", "content": question}],
        }).encode()
        headers = {"Content-Type": "application/json", "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"}
        try:
            req = Request(_ENDPOINTS["claude"], data=body, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            content = data["content"][0]["text"]
            tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
            cost = tokens * 0.0000003
            cfg.tokens_used += tokens
            cfg.cost_spent += cost
            cfg.requests_made += 1
            return AIResponse(content=content, tokens_used=tokens, cost=cost, provider="claude")
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"Claude error: {exc}")

    async def _ask_pollinations(self, username: str, question: str) -> AIResponse:
        """Free AI — no key needed. Easter egg provider."""
        cfg = self._cfg(username)
        body = json.dumps({
            "model": "openai",
            "messages": [{"role": "user", "content": question}],
        }).encode()
        headers = {"Content-Type": "application/json"}
        try:
            req = Request("https://text.pollinations.ai/openai", data=body,
                          headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens",
                                                len(question.split()) + len(content.split()))
            cfg.tokens_used += tokens
            cfg.requests_made += 1
            return AIResponse(content=content, tokens_used=tokens, cost=0.0, provider="pollinations")
        except (URLError, KeyError, json.JSONDecodeError) as exc:
            return AIResponse(error=f"AI error: {exc}")
