# Shaggy Dog Web Application (MCO368 Final)

This project satisfies the requirements:
- Upload a headshot
- Identify closest dog breed
- Generate **2 transition images** + **final dog image** (3 generated images total)
- Show images in the UI, generated concurrently using **multithreading**
- User registration/login with **encrypted credentials (bcrypt hashes)**
- Store user credentials + generated images in a **database**
- Each user can only see their own images

## Local dev

1) Create a virtualenv and install deps:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Create `.env`:
```bash
cp .env.example .env
# then edit:
# OPENAI_API_KEY=...
# SECRET_KEY=...
```

3) Run:
```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

### Smoke test (optional)
```bash
python -m app.smoketest
```

## Deploy to Render

Create:
- A **Web Service** for this repo
- A **PostgreSQL** instance

Set env vars on the web service:
- `OPENAI_API_KEY`
- `SECRET_KEY` (any long random string)
- `DATABASE_URL` (Render provides this for Postgres)
- `VISION_MODEL` (optional, default: `gpt-4.1-mini`)
- `IMAGE_MODEL` (optional, default: `gpt-image-1.5`; fallback to `dall-e-2` on errors)

Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Custom domain (subdomain)
In Render service settings: add `shaggydog.<yourdomain>` as a custom domain.
Then add a **CNAME** DNS record for `shaggydog` pointing to your service’s `*.onrender.com` hostname.

> Render automatically provisions TLS (HTTPS) after verification.

## Notes on OpenAI image models
The app prefers GPT Image (`gpt-image-1.5`) for higher quality. Some orgs may need verification to use GPT Image models.
If the call fails, the app automatically falls back to `dall-e-2` edits (works but lower quality and requires square PNG input).

