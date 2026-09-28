from datetime import date, datetime, timedelta
import os
import secrets
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel, Field, HttpUrl
from database import (
    list_goals, add_goal, set_goal_completed,
    create_application,
    update_application_details,
    delete_application,
    get_application_count,
    get_activity_dates,
    get_applications_by_statuses,
    get_status_counts,
    get_recent_applications as db_get_recent_applications,
    initialize_database,
    search_applications as db_search_applications,
    update_application_status,
)


# A stable random local secret invalidates old development cookies safely.
secret_path = Path(__file__).with_name(".session-secret")
session_secret = os.getenv("SESSION_SECRET", "").strip()
if os.getenv("APP_ENV") == "production":
    required = ("DATABASE_URL", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI", "SESSION_SECRET")
    missing = [key for key in required if not os.getenv(key, '').strip()]
    if missing:
        raise RuntimeError('Missing production configuration: ' + ', '.join(missing))
    if len(session_secret) < 32:
        raise RuntimeError('SESSION_SECRET must contain at least 32 characters in production')
if not session_secret:
    if not secret_path.exists():
        with secret_path.open("x") as secret_file:
            secret_file.write(secrets.token_urlsafe(48))
    session_secret = secret_path.read_text().strip()

@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield


app = FastAPI(title="Job Application Tracker", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax",
    https_only=os.getenv("APP_ENV") == "production",
)

oauth = OAuth()
if os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"):
    oauth.register(
        name="google",
        client_id=os.environ["GOOGLE_CLIENT_ID"].strip(),
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"].strip(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


ALLOWED_STATUSES = {
    "Applied",
    "Online Assessment",
    "Rejected",
    "Interview In Progress",
    "Offer",
}


class Application(BaseModel):
    company: str
    role: str
    status: str


class StatusUpdate(BaseModel):
    status: str


class GoalInput(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class GoalCompletion(BaseModel):
    completed: bool


class ApplicationDetails(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    job_url: HttpUrl | None = None
    notes: str = Field(default="", max_length=10000)


@app.middleware('http')
async def response_headers(request: Request, call_next):
    # Browser mutations must originate from this site, not another origin.
    if request.method in {'POST', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-site request rejected'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    return response


def require_user(request: Request):
    user = request.session.get("user")
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Please sign in with Google")
    return user["id"]


@app.get("/goals")
def goals(user_id: str = Depends(require_user)):
    return list_goals(user_id)


@app.post("/goals")
def create_goal_entry(goal: GoalInput, user_id: str = Depends(require_user)):
    if not goal.text.strip():
        raise HTTPException(status_code=400, detail="Write a goal first")
    return add_goal(user_id, goal.text.strip())


@app.patch("/goals/{goal_id}")
def complete_goal(goal_id: int, goal: GoalCompletion, user_id: str = Depends(require_user)):
    if not set_goal_completed(user_id, goal_id, goal.completed):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"completed":goal.completed}


@app.get("/app")
def frontend(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/start", status_code=303)
    return FileResponse(str(Path(__file__).parent / "frontend/index.html"))


@app.get("/start")
def start_page():
    return FileResponse(str(Path(__file__).parent / "frontend/start.html"))


@app.get("/auth/me")
async def current_user(request: Request):
    return request.session.get("user")


@app.get("/")
def home():
    return RedirectResponse('/start', status_code=303)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get("/auth/google")
async def google_login(request: Request):
    if request.session.get("user", {}).get("id"):
        return RedirectResponse(url="/app", status_code=303)
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        raise HTTPException(status_code=503, detail="Google login is not configured yet")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI") or request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback", name="google_callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")
    if not user:
        raise HTTPException(status_code=400, detail="Google did not return user information")
    request.session.clear()
    request.session["user"] = {
        "id": user["sub"],
        "name": user.get("name", "Google user"),
        "email": user.get("email", ""),
    }
    return RedirectResponse(url="/app")


@app.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Logged out"}

@app.post("/applications")
def add_application(application: Application, user_id: str = Depends(require_user)):
    if not application.company.strip():
        raise HTTPException(status_code=400, detail="Company cannot be empty")

    if not application.role.strip():
        raise HTTPException(status_code=400, detail="Role cannot be empty")

    if application.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    return create_application(
        user_id,
        application.company,
        application.role,
        application.status,
    )


@app.get("/applications/recent")
def get_recent_applications(user_id: str = Depends(require_user)):
    return db_get_recent_applications(user_id)


@app.patch("/applications/{application_id}")
def update_status(application_id: int, update: StatusUpdate, user_id: str = Depends(require_user)):
    if update.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")

    updated_application = update_application_status(user_id, application_id, update.status)
    if updated_application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    return updated_application


@app.patch("/applications/{application_id}/details")
def edit_details(application_id: int, details: ApplicationDetails, user_id: str = Depends(require_user)):
    if not details.company.strip() or not details.role.strip():
        raise HTTPException(status_code=400, detail="Company and role cannot be empty")
    updated = update_application_details(user_id, application_id, details.company.strip(), details.role.strip(), str(details.job_url) if details.job_url else "", details.notes)
    if updated is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return updated


@app.delete("/applications/{application_id}")
def remove_application(application_id: int, user_id: str = Depends(require_user)):
    if not delete_application(user_id, application_id):
        raise HTTPException(status_code=404, detail="Application not found")

    return {"message": "Application deleted"}


@app.get("/applications/count")
def get_count(user_id: str = Depends(require_user)):
    return {"count": get_application_count(user_id)}


@app.get("/applications/sections")
def get_application_sections(user_id: str = Depends(require_user)):
    return {
        "offers": get_applications_by_statuses(user_id, ["Offer"]),
        "in_progress": get_applications_by_statuses(
            user_id,
            ["Online Assessment", "Interview In Progress"]
        ),
    }


@app.get("/applications/stats")
def get_application_stats(user_id: str = Depends(require_user)):
    counts = get_status_counts(user_id)
    activity_dates = [datetime.fromisoformat(value).date() for value in get_activity_dates(user_id)]
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_activity = [sum(day == (week_start + timedelta(days=index)) for day in activity_dates) for index in range(7)]
    active_days = set(activity_dates)
    streak = 0
    streak_day = today if today in active_days else today - timedelta(days=1)
    while streak_day in active_days:
        streak += 1
        streak_day -= timedelta(days=1)

    longest = run = 0
    previous = None
    for day in sorted(active_days):
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    return {
        "longest_streak": longest,
        "total": sum(counts.values()),
        "active": counts.get("Applied", 0) + counts.get("Online Assessment", 0) + counts.get("Interview In Progress", 0),
        "interviews": counts.get("Interview In Progress", 0),
        "offers": counts.get("Offer", 0),
        "streak": streak,
        "today_count": week_activity[today.weekday()],
        "week_total": sum(week_activity),
        "week_activity": week_activity,
    }


@app.get("/applications/search")
def search_applications(company: str, user_id: str = Depends(require_user)):
    return db_search_applications(user_id, company)
