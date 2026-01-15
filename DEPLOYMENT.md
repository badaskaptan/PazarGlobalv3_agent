# PazarGlobal Agent Backend - Deployment Guide

## Railway Deployment

### 1. Prerequisites
- Railway account
- GitHub repository connected
- Environment variables configured

### 2. Environment Variables

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key

# OpenAI (Optional - for keyword enhancement)
OPENAI_API_KEY=sk-...

# CORS
CORS_ALLOW_ORIGINS=https://your-frontend.vercel.app,http://localhost:5173
CORS_ALLOW_CREDENTIALS=true
CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,OPTIONS
CORS_ALLOW_HEADERS=*
```

### 3. Start Command

Railway automatically detects Python and runs:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Or specify in `railway.json`:
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 4. Health Check

After deployment, verify:
```bash
curl https://your-agent.railway.app/healthz

# Expected response:
{
  "ok": true,
  "service": "PazarGlobal Agent Backend",
  "time": "2026-01-15T10:30:00Z"
}
```

### 5. API Documentation

Visit: `https://your-agent.railway.app/docs`

FastAPI auto-generates Swagger UI with all endpoints.

### 6. Monitoring

- **Railway Dashboard:** Logs, metrics, deployment history
- **Health Endpoint:** `/healthz` (uptime monitoring)
- **Supabase Audit Logs:** `audit_logs` table tracks all operations

---

## Local Development

### 1. Setup

```bash
cd agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create `.env`:
```bash
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_KEY=your-local-key
OPENAI_API_KEY=sk-...
CORS_ALLOW_ORIGINS=http://localhost:5173
```

### 3. Run

```bash
uvicorn main:app --reload --port 8000
```

Visit: `http://localhost:8000/docs`

### 4. Testing

```bash
# Syntax check
python -m compileall app

# Import test
python -c "from main import app; print('✅ OK')"

# Manual endpoint test
curl -X POST http://localhost:8000/webchat/message \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "uuid",
    "message": "iPhone satıyorum",
    "session_id": "uuid"
  }'
```

---

## Troubleshooting

### Railway Build Fails
- Check `requirements.txt` has all dependencies
- Verify Python version compatibility (3.11+)
- Check Railway logs for specific error

### CORS Errors
- Verify `CORS_ALLOW_ORIGINS` includes frontend URL
- Check frontend is using correct agent URL
- Ensure `CORS_ALLOW_CREDENTIALS=true` if using cookies

### Supabase Connection Fails
- Verify `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- Check Supabase project is not paused
- Test connection: `curl $SUPABASE_URL/rest/v1/`

### Import Errors
- Run `python -m compileall app` locally first
- Check all `__init__.py` files exist in folders
- Verify relative imports use `from app.xxx import`

---

## Performance Optimization

### 1. Response Caching
- Draft reads are cached per user session
- Category library is static (no DB calls)

### 2. Database Indexes
```sql
-- Already created in migrations
CREATE INDEX idx_listings_metadata_keywords 
ON listings USING GIN ((metadata->'keywords_text'));

CREATE INDEX idx_active_drafts_user 
ON active_drafts(user_id);
```

### 3. Connection Pooling
Supabase client automatically handles connection pooling.

---

## Security Checklist

- [x] Use `SUPABASE_SERVICE_KEY` (not anon key)
- [x] Enable CORS only for trusted origins
- [x] Never log sensitive data (passwords, API keys)
- [x] Validate all user inputs (Pydantic models)
- [x] Rate limit endpoints (10 req/sec)
- [x] Use HTTPS in production
- [x] Keep dependencies updated (`pip list --outdated`)

---

**Last Updated:** 15 January 2026
