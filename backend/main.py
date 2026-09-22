from app.core.config import settings
from app.core.errors import install_error_handlers
from app.routers import (
    analytics,
    assignments,
    auth,
    courses,
    curriculum,
    health,
    problems,
    submissions,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="TechniView",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url="/api/redoc",
)

# CORS open for local dev, lock down for prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes under /api
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(problems.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
install_error_handlers(app)


@app.get("/api")
def api_root():
    return {
        "service": "api",
        "python": "3.14",
        "docs": "/api/docs",
        "health": "/api/health",
        "problems": "/api/problems",
        "submissions": "/api/submissions",
    }


@app.get("/api/ping")
def ping():
    return {"pong": True}


# Old root pointer, everything lives under /api
@app.get("/")
def root():
    return {"service": "api", "api": "/api"}
