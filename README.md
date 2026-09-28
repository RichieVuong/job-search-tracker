# Job Search Tracker

FastAPI application with Google sign-in, private application records, editable job links and notes, status tracking, personal goals, and activity statistics.

## Local development

Use Python 3.12. Install `requirements.txt`, set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then run:

```sh
uvicorn app:app --host 127.0.0.1 --port 8035
```

Register `http://127.0.0.1:8035/auth/callback` with your Google OAuth web client. Open `/start`. Without `DATABASE_URL` or private local database configuration, SQLite is used. Never commit credentials or database files.

## Tests

```sh
python -m unittest test_accounts -v
```

Tests use temporary SQLite databases, not the connected Supabase project.

## Render deployment

Connect this repository as a Render Web Service or Blueprint using `render.yaml`. Select the Free instance. Configure `DATABASE_URL` with the Supabase session-pooler PostgreSQL URL, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` (random, at least 32 characters), `APP_ENV=production`, and `GOOGLE_REDIRECT_URI=https://YOUR-SERVICE.onrender.com/auth/callback`.

Add that exact callback to the existing Google OAuth client's authorized redirect URIs. Keep the localhost callback for development. The Blueprint generates a session secret; when creating a service manually, generate one privately and store it in Render.

The `/health` endpoint is used for service health checks. Free services can sleep when idle. Data is stored in Supabase's `tracker_private` schema, not Render's filesystem. This schema is not exposed through Supabase's public Data API; all app access goes through account-scoped backend queries.

## Before sharing publicly

- Complete the SQLite migration and confirm your account owns the intended legacy records
- Verify sign-in, sign-out, application edits, deletion, goals, and account isolation on the live deployment
- Confirm Google OAuth audience/test-user settings permit your intended users
- Restart the service and verify saved data remains available

Current limitations: UTC-based daily statistics, a fixed daily target of five applications, and a recent-applications table limited to 20 records. Company search can find older records. Database credentials currently require schema-creation rights; a dedicated restricted runtime role is a future improvement.
