from app.routers import health, problems, stats, submissions
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes under /api
app.include_router(health.router, prefix="/api")
app.include_router(problems.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


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
