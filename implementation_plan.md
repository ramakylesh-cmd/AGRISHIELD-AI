# AgriShield AI — Render → Vercel + Supabase Migration

## Background

AgriShield AI is a Flask-based PWA for AI-powered crop disease detection. It was originally hosted on **Render** (a PaaS that runs Python servers directly). The goal is to migrate the deployment configuration to **Vercel** (a serverless edge platform) and replace **SQLite** with **Supabase** (managed PostgreSQL).

This is primarily a **deployment infrastructure change** — not a full rewrite. The Flask app logic, routes, and templates stay intact. What changes:

1. How the app is packaged and served on Vercel (serverless functions via WSGI adapter)
2. The database layer: SQLite → Supabase PostgreSQL
3. Session handling (serverless-safe)
4. Cleaned-up environment variables
5. Removed Render-specific configs (port binding, gunicorn start command)

---

## What Was Found — Render-Specific Code

| Location | Render-Specific Pattern | Fix Needed |
|---|---|---|
| `app.py` line 1062 | `port = int(os.environ.get("PORT", 10000))` — Render injects `PORT` | Remove (Vercel handles routing) |
| `app.py` line 36 | `ALLOWED_ORIGINS` defaults to `http://localhost:10000` | Update to production Vercel URL |
| `app.py` line 43 | `GOOGLE_REDIRECT` defaults to `http://localhost:10000/...` | Update to Vercel URL |
| `app.py` lines 90–177 | **SQLite** (`agrishield.db`) — ephemeral on serverless, won't persist | Replace with **Supabase PostgreSQL** |
| `requirements.txt` | Has `gunicorn==25.3.0` (Render's process manager) | Keep but also add `psycopg2-binary` for Postgres |
| `.env` | `GOOGLE_REDIRECT_URI=http://localhost:10000/...` | Update to Vercel URL |
| No `vercel.json` | Missing — Vercel doesn't know how to run Flask | **Create** |
| No `api/index.py` | Vercel needs an entrypoint in `/api/` | **Create** |

---

## Open Questions

> [!IMPORTANT]
> **Supabase connection string** — After you create a Supabase project, you'll get a `DATABASE_URL` (PostgreSQL connection string). I need you to paste this in your Vercel environment variables. I'll wire the code to use it automatically.

> [!IMPORTANT]
> **Vercel domain** — What is your Vercel deployment URL? (e.g. `https://agrishield-ai.vercel.app`). I'll use this to pre-fill `ALLOWED_ORIGINS` and `GOOGLE_REDIRECT_URI` defaults.

> [!WARNING]
> **Session persistence**: Flask's default server-side sessions won't work across serverless invocations. I'll switch to **signed cookie sessions** (stateless, JWT-style) which work perfectly on Vercel. No external session store needed.

---

## Proposed Changes

### 1. Vercel Configuration

#### [NEW] `vercel.json`
Tells Vercel to route all traffic to a Python serverless function.

```json
{
  "version": 2,
  "builds": [{ "src": "api/index.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "api/index.py" }]
}
```

#### [NEW] `api/index.py`
Vercel's Python runtime expects a WSGI `app` object at this path.

```python
from app import app  # re-exports Flask app as WSGI handler
```

---

### 2. Database Layer — SQLite → Supabase (PostgreSQL)

#### [MODIFY] `app.py` — Database section

Replace `sqlite3` with `psycopg2` (PostgreSQL driver). The changes are:

- `import sqlite3` → `import psycopg2` + `psycopg2.extras`
- `DATABASE = "agrishield.db"` → `DATABASE_URL = os.environ.get("DATABASE_URL")`
- `get_db()` → connects to PostgreSQL using `DATABASE_URL`
- SQL queries: replace `?` placeholders with `%s` (PostgreSQL syntax)
- `datetime('now')` → `NOW()` in SQL
- `PRAGMA table_info()` → `information_schema.columns` for migrations
- Auto-migration logic stays the same in structure

---

### 3. Flask App Configuration

#### [MODIFY] `app.py` — Startup section

```python
# OLD (Render)
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:10000").split(",")

# NEW (Vercel)
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "https://your-app.vercel.app").split(",")
```

```python
# OLD (Render)
GOOGLE_REDIRECT = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:10000/auth/google/callback")

# NEW (Vercel)
GOOGLE_REDIRECT = os.environ.get("GOOGLE_REDIRECT_URI", "https://your-app.vercel.app/auth/google/callback")
```

Remove the `if __name__ == "__main__"` block at the bottom (not used in serverless).

---

### 4. Environment Variables

#### [MODIFY] `.env` (local dev only)
Update redirect URI for local testing. `.env` is already gitignored.

#### [NEW] `.env.example`
Document all required env vars for Vercel dashboard setup.

```env
# Supabase
DATABASE_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres

# Flask
SECRET_KEY=your-strong-secret-key

# Groq AI
GROQ_API_KEY=gsk_...

# OpenWeatherMap
WEATHER_API_KEY=your-key

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-app.vercel.app/auth/google/callback

# CORS
ALLOWED_ORIGINS=https://your-app.vercel.app
```

---

### 5. Requirements

#### [MODIFY] `requirements.txt`
Add `psycopg2-binary` for PostgreSQL. Remove pinned versions of unused packages if desired (optional cleanup).

```diff
+ psycopg2-binary==2.9.10
```

---

### 6. Updated `.gitignore`

#### [MODIFY] `.gitignore`
Ensure `agrishield.db` (SQLite) and `venv/` are ignored.

```gitignore
venv/
__pycache__/
*.pyc
.env
agrishield.db
*.db
```

---

## Verification Plan

### Automated / CLI
- Run `vercel dev` locally to confirm serverless routing works
- Test `/api/me`, `/predict`, `/voice-diagnose` endpoints

### Manual (After Deploy)
1. Deploy to Vercel with `vercel --prod`
2. Set all env vars in Vercel Dashboard → Settings → Environment Variables
3. Test login/register flow
4. Upload a crop image and verify AI diagnosis + DB save to Supabase
5. Check Supabase Table Editor to confirm rows are being written

---

## Summary of Files Changed

| File | Action |
|---|---|
| `vercel.json` | **CREATE** — Vercel build + routing config |
| `api/index.py` | **CREATE** — Vercel Python entrypoint |
| `app.py` | **MODIFY** — SQLite→PostgreSQL, URLs, remove PORT binding |
| `requirements.txt` | **MODIFY** — Add `psycopg2-binary` |
| `.env` | **MODIFY** — Update redirect URI |
| `.env.example` | **CREATE** — Env var documentation |
| `.gitignore` | **MODIFY** — Add `.db` to ignored files |
