# Pathly — Job Application Tracker

A full-stack application for organizing job applications, tracking hiring stages, and keeping up with personal job-search goals.

**Python · FastAPI · JavaScript · HTML/CSS · SQL · PostgreSQL · Google OAuth**

[Open the live app](https://job-search-tracker-nabf.onrender.com/start) · [Screenshot guide](docs/SHOWCASE.md)

Google sign-in is required to use the tracker. If the deployment is unavailable, the source and local setup instructions below remain available.

## Why I built it

I built Pathly while searching for software engineering internships. I wanted a simple place to record applications, see where each one stood, and track my progress without maintaining a spreadsheet. Building it also gave me experience taking a Python application from local development to a deployed service with authentication and a hosted database.

## Features

- Add applications and track Applied, Online Assessment, Interview In Progress, Offer, and Rejected stages
- Search by company, filter by stage, and sort by last update
- Edit company and role details, save job links and notes, and delete applications with confirmation
- View application counts, daily and weekly activity, and streaks
- Create and complete personal goals
- Sign in with Google to access account-scoped applications and goals
- Update status badges immediately, with rollback if saving fails

## Architecture

The browser calls a FastAPI backend. The backend checks the signed-in user's session, validates inputs, and executes account-scoped SQL queries. PostgreSQL on Supabase stores deployed data; a fresh local checkout can use SQLite.

| Layer | Implementation |
| --- | --- |
| Interface | HTML/CSS and vanilla JavaScript; no frontend build step |
| API | Python, FastAPI, and Pydantic request models |
| Authentication | Google OAuth through Authlib; signed session cookies |
| Persistence | SQLite locally or PostgreSQL through Psycopg |
| Deployment | Render web service and Supabase PostgreSQL |
| Tests | Python unittest/FastAPI TestClient and Node's built-in test runner |

Supabase is the database provider, not the authentication provider. Backend queries access a `tracker_private` schema; browsers do not connect directly to the database.

## Engineering decisions and lessons

**Account isolation.** Reads and mutations include the signed-in user's ID. Tests exercise attempts to read or modify another account's applications and goals.

**Handling network latency.** After deployment, a pending save could allow a second submission to create a duplicate application. An in-flight guard now blocks repeated submission until the request finishes. Regression tests cover repeated submissions and retry after failure.

**Optimistic status updates.** Badges change before the save response arrives. Pending changes are separate from server data, repeat edits to the same record are blocked, and failed saves restore the previous state. A background refresh failure does not undo an already-saved edit.

**Persistent hosted storage.** Deployed records live in PostgreSQL rather than the web server's local filesystem. A migration script supports owned legacy SQLite records.

## Run locally

### Prerequisites

- Python 3.12 (the deployment configuration's target version)
- A Google OAuth **Web application** client for sign-in
- Node.js 18 or newer only for frontend regression tests

### 1. Install

```sh
git clone https://github.com/RichieVuong/job-search-tracker.git
cd job-search-tracker
python -m venv .venv
```

Activate in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or macOS/Linux:

```sh
source .venv/bin/activate
```

Then:

```sh
python -m pip install -r requirements.txt
```

### 2. Configure Google sign-in

Register this exact authorized redirect URI in your Google OAuth client:

```text
http://127.0.0.1:8035/auth/callback
```

Set variables in the same terminal that will start the server. Replace placeholders privately.

PowerShell:

```powershell
$env:GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
$env:GOOGLE_CLIENT_SECRET="your-client-secret"
$env:GOOGLE_REDIRECT_URI="http://127.0.0.1:8035/auth/callback"
```

macOS/Linux:

```sh
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
export GOOGLE_REDIRECT_URI="http://127.0.0.1:8035/auth/callback"
```

If Google's consent screen is in testing mode, add the intended account as a test user. A stable local session secret is generated automatically when `SESSION_SECRET` is not set.

`.env.example` is a configuration reference; the app **does not automatically load .env files**. Set variables in your shell or hosting environment.

### 3. Choose storage and start

A fresh checkout uses SQLite when neither `DATABASE_URL` nor the ignored `.database-config.json` is present. Tables are initialized at startup.

For PostgreSQL, set `DATABASE_URL` to your own connection string. The database account currently needs permission to create the private schema and tables. Never commit passwords.

```sh
python -m uvicorn app:app --host 127.0.0.1 --port 8035 --reload
```

Open [the landing page](http://127.0.0.1:8035/start). [Local API docs](http://127.0.0.1:8035/docs) are also available; protected endpoints require a signed-in session.

## Tests

```sh
python -m unittest test_accounts -v
node --test test_frontend.cjs
```

Backend tests use disposable SQLite databases, not Supabase. Run in a development environment without `APP_ENV=production`.

Coverage includes unauthenticated access, cross-site requests, account isolation, goals, persisted edits, input validation, legacy unassigned records, duplicate submissions, and optimistic-update failure handling.

Frontend tests run handlers with mocks: they are not full browser end-to-end tests or PostgreSQL integration tests.

## Deploy on Render

Connect the repository as a Python Web Service, or use `render.yaml` as a Blueprint.

Build command:

```sh
pip install -r requirements.txt
```

Start command:

```sh
uvicorn app:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

Set `APP_ENV=production`, `DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and `SESSION_SECRET`. Use a randomly generated session secret of at least 32 characters. The Blueprint generates one; manual setup requires supplying it privately.

Set the Google redirect URI to `https://YOUR-SERVICE.onrender.com/auth/callback` and register the exact same URL with Google. Store credentials in Render's environment settings, not Git. The health-check path is `/health`.

## Current limitations and next steps

- Daily statistics use the server's date rather than each user's timezone
- The daily application target is fixed at five
- The recent list returns 20 applications; company search can find older records
- Google OAuth configuration is required for local sign-in
- Frontend guards prevent overlapping submissions, but the create endpoint does not yet support server-side idempotency keys
- A restricted database runtime role, PostgreSQL integration tests, and browser end-to-end tests would strengthen the production setup

## Repository guide

- `app.py`: routes, validation, authentication, and sessions
- `database.py`: account-scoped queries and table initialization
- `frontend/`: landing page and tracker interface
- `test_accounts.py`: backend regression tests
- `test_frontend.cjs`: submission and optimistic-update tests
- `migrate_database.py`: migration of owned legacy SQLite data
- `render.yaml`: deployment configuration

Before publishing, check both current files and Git history for credentials. Do not publish local databases, private configuration, or screenshots containing real account details.
