# PazarGlobal Agent Backend (Modular)

Bu servis WhatsApp (Supabase Edge `whatsapp-traffic-controller` üzerinden) ve WebChat (Vite frontend) isteklerini karşılar.

## 📁 Proje Yapısı

```
agent/
├── main.py                      # 🚀 Entrypoint
├── app/
│   ├── config.py               # Env, CORS
│   ├── schemas.py              # Pydantic models
│   ├── clients/                # Supabase, OpenAI
│   ├── core/helpers.py         # Intent, helpers
│   ├── services/               # Business logic
│   │   ├── category_library.py
│   │   ├── metadata_keywords.py
│   │   ├── drafts.py, search.py, publish.py
│   │   ├── parsing.py, audit.py
│   └── routers/
│       ├── webchat.py, agent_run.py
└── services/                    # ⚠️ DEPRECATED
```

## Endpoints

- `GET /healthz`
- `POST /agent/run` (Edge Function forward)
- `GET /webchat/categories`
- `POST /webchat/message`
- `POST /webchat/media/analyze`

## ENV

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY` (opsiyonel)
- `OPENAI_MODEL` (opsiyonel)
- `PORT` (Railway)

## Local Run

```powershell
cd agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env dosyasını doldur
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Railway Deploy

`railway.json`: `uvicorn main:app --host 0.0.0.0 --port $PORT`
