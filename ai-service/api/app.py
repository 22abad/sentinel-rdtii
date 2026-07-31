from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import (
    activity,
    auth,
    evidence,
    canvas_files,
    discovery,
    excel,
    extraction,
    review,
    rlvr,
    system,
    validation,
    workbench_canvas,
    workflows,
)


def create_app() -> FastAPI:
    app = FastAPI(title="RDTII AI Mapper", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in os.getenv(
                "CORS_ALLOW_ORIGINS",
                "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(activity.router)
    app.include_router(evidence.router)
    app.include_router(extraction.router)
    app.include_router(discovery.router)
    app.include_router(auth.router)
    app.include_router(review.router)
    app.include_router(excel.router)
    app.include_router(validation.router)
    app.include_router(workbench_canvas.router)
    app.include_router(workflows.router)
    app.include_router(canvas_files.router)
    app.include_router(rlvr.router)
    return app
