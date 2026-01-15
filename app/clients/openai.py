from __future__ import annotations

import httpx
import orjson

from app.config import OPENAI_API_KEY, OPENAI_MODEL


def _safe_json(obj) -> str:
    return orjson.dumps(obj).decode("utf-8")


async def openai_chat(system: str, user: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")

    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
    }

    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            content=_safe_json(payload),
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"OpenAI error {resp.status_code}: {resp.text}")
        data = resp.json()
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
