"""Pollinations AI integration for CLARA — optional, works without API key."""

import os

import requests

BASE_URL = "https://gen.pollinations.ai"

API_KEY = os.getenv("POLLINATIONS_API_KEY")


def ask_ai(prompt: str) -> str:
    """Send a prompt to Pollinations AI and return the response text."""
    headers: dict[str, str] = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "model": "openai",
        "messages": [{"role": "user", "content": prompt}],
    }

    r = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
