from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "pazarglobal-agent"

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_SERVICE_KEY = (os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "").strip() or "gpt-4o-mini"

# CORS can be customized later; keep permissive for now.
CORS_ALLOW_ORIGINS = ["*"]
CORS_ALLOW_METHODS = ["*"]
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_CREDENTIALS = True
