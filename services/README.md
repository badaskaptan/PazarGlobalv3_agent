# Agent Service Library (Legacy)

**⚠️ DEPRECATED**: Bu dizindeki dosyalar eski referans kopyalarıdır.

## Yeni Modüler Yapı

Agent backend artık modüler hale getirilmiştir:

```
agent/
├── main.py                  # Entrypoint (FastAPI app init + routers)
├── app/
│   ├── config.py           # Env vars, CORS config
│   ├── schemas.py          # Pydantic request/response models
│   ├── clients/
│   │   ├── supabase.py     # Supabase client factory
│   │   └── openai.py       # OpenAI chat wrapper
│   ├── core/
│   │   └── helpers.py      # Intent detection, UUID, phone normalization, time helpers
│   ├── services/
│   │   ├── category_library.py     # Kategori eşleme (deterministik)
│   │   ├── metadata_keywords.py    # Keyword üretimi (deterministik + LLM)
│   │   ├── drafts.py              # Draft CRUD
│   │   ├── search.py              # Listing arama
│   │   ├── publish.py             # Draft → Listing yayınlama
│   │   ├── parsing.py             # Mesaj → field extraction
│   │   └── audit.py               # Audit log helper
│   └── routers/
│       ├── webchat.py             # /webchat/* endpoints
│       └── agent_run.py           # /agent/run endpoint
└── services/                      # (bu klasör - ESKİ/DEPRECATED)
```

## Kategori & Keyword Mantığı

- **Kategori**: `app/services/category_library.py` içinde deterministik eşleme (synonym/brand heuristic).
- **Keywords**: `app/services/metadata_keywords.py` içinde deterministik baseline + opsiyonel LLM zenginleştirme.

Tüm importlar artık `from app.services.*` şeklinde yapılmalıdır.

---

**Not**: Gelecekte bu `services/` klasörü silinebilir; şu an referans amaçlı bırakıldı.
