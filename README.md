# MEMORA — 3D Museum starter (Vercel + FastAPI + Google Drive + PostgreSQL + LiveKit)

This is a full integration starter, not a finished audited production service. It includes:
- React + Three.js 3D gallery, local photo placement, wall color customization and movement
- Google OAuth and automatic per-user `MEMORA` Drive folder
- FastAPI API for photo upload/list/content/delete, museums, memberships and room presence
- PostgreSQL schema via SQLAlchemy
- LiveKit token endpoint for voice-room access
- Vercel frontend and Python Function routing

## Requirements
- Node.js 22 LTS
- Python 3.12 recommended
- PostgreSQL with TLS (Neon/Supabase/managed Postgres)
- Google Cloud project with Drive API enabled and OAuth Web client
- LiveKit Cloud project for voice
- Vercel account

## Google OAuth setup
1. In Google Cloud Console, enable Google Drive API.
2. Configure OAuth consent screen and add test users while in Testing.
3. Create OAuth client ID → Web application.
4. Add redirect URI exactly:
   `https://YOUR-VERCEL-DOMAIN.vercel.app/api/auth/google/callback`
5. Use `openid`, `email`, `profile`, and `drive.file` scopes. `drive.file` is intentionally limited to files created/managed by the app or explicitly selected by the user.
6. Configure Google OAuth verification before public rollout as required by Google.

## LiveKit setup
Create a LiveKit Cloud project and copy its URL, API key, and API secret. Keep the secret server-side only. Voice is provided through LiveKit/WebRTC. The starter has a room token endpoint and the frontend voice join UI; validate production permissions and usage limits before launch.

## Environment variables
Configure these in Vercel project settings; for local development, copy `.env.example` to `.env`.

- `DATABASE_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `APP_ORIGIN`
- `SESSION_SECRET` (long random value)
- `TOKEN_ENCRYPTION_KEY` (Fernet key)
- `COOKIE_SECURE=true` in production, `false` for local HTTP
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `MAX_UPLOAD_MB=8`

Generate secrets:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Local run
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env
python -m api.init_db
uvicorn api.index:app --reload --port 8000
```
In another terminal:
```bash
npm run dev
```
Vite proxies `/api` to localhost:8000. For local OAuth use:
`GOOGLE_REDIRECT_URI=http://localhost:8000/api/auth/google/callback`
`APP_ORIGIN=http://localhost:5173`
Note: API cookie is set by localhost:8000 while the frontend is localhost:5173; for local development use same-site localhost and configure `COOKIE_SECURE=false`. If browser cookie behavior is troublesome, test frontend via same origin reverse proxy or use the deployed preview URL.

## Vercel deploy
- Import project into Vercel.
- Framework: Vite
- Build: `npm run build`
- Output: `dist`
- Add all environment variables.
- Set exact Google redirect URI to deployed URL.
- Apply `api/schema.sql` to the database, or run `python -m api.init_db` once in a trusted environment.
- Test `/api/health`, Google OAuth, photo upload, museum creation and voice token endpoint.
- Do not run schema creation on every serverless invocation.

## Implemented endpoints
- `GET /api/health`
- `GET /api/auth/google`, `GET /api/auth/google/callback`
- `GET /api/me`, `POST /api/auth/logout`
- `POST /api/photos/upload`, `GET /api/photos`, `GET /api/photos/{id}/content`, `DELETE /api/photos/{id}`
- `POST /api/museums`, `GET /api/museums`, `GET /api/museums/{id}`
- `POST /api/museums/{id}/invite`, `POST /api/museums/join`
- `POST /api/rooms/{id}/presence` (short-lived position update)
- `POST /api/rooms/{id}/voice-token` (LiveKit JWT)

## Important boundaries
- Voice is a working integration path only after valid LiveKit credentials and browser microphone permissions are configured. It is not a custom voice server.
- Presence endpoint and polling demonstrate the data contract. For smooth multi-user movement, use a realtime service or WebSocket provider; Vercel Functions cannot keep persistent in-memory socket sessions.
- Shared-museum permissions are enforced by membership checks for museum photo access. Do not make Drive files public.
- The 3D frontend is a starter; native mobile app is not included as a separate installable Android/iOS package. It is responsive in mobile browsers. The React Native app can share the API and needs its own native 3D rendering integration.
- Production launch still needs load testing, security review, abuse controls, rate limits, retention/deletion workflows and Google OAuth verification as applicable.
# memora
# memora
