from __future__ import annotations

from supabase import Client, create_client

from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL


def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_KEY missing")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
