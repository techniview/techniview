import json
import logging
import time
import uuid

from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.observability import configure_logging, observe_request
from app.routers import (
    analytics,
    assignments,
    auth,
    authoring,
    courses,
    curriculum,
    health,
    join,
    metrics,
    problems,
    recommendations,
    submissions,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

configure_logging()
logger = logging.getLogger("techniview.http")

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


class RequestObservabilityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500
        request_id = uuid.uuid4().hex

        async def send_with_request_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = getattr(scope.get("route"), "path", "unmatched")
            duration = time.perf_counter() - started
            observe_request(scope["method"], route, status, duration)
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": route,
                        "status": status,
                        "duration_seconds": round(duration, 6),
                    },
                    separators=(",", ":"),
                )
            )


app.add_middleware(RequestObservabilityMiddleware)


# All API routes under /api
app.include_router(health.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(join.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(problems.router, prefix="/api")
app.include_router(authoring.router, prefix="/api")
app.include_router(curriculum.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
app.include_router(submissions.course_router, prefix="/api")
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
