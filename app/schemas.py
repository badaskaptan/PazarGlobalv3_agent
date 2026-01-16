from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    user_id: str
    phone: str | None = None
    message: str
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    media_paths: list[str] | None = None
    media_type: str | None = None
    draft_listing_id: str | None = None
    session_token: str | None = None
    user_context: dict[str, Any] | None = None


class WebchatMessageRequest(BaseModel):
    session_id: str | None = None
    user_id: str
    message: str
    media_url: str | None = None
    media_urls: list[str] | None = None
    user_context: dict[str, Any] | None = None


class WebchatMediaAnalyzeRequest(BaseModel):
    session_id: str | None = None
    user_id: str
    media_urls: list[str] = Field(min_length=1)
