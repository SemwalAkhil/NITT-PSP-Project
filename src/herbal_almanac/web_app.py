"""FastAPI web interface for browsing a local Herbal Almanac database.

Run with: uvicorn herbal_almanac.web_app:app --reload
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database_operator import AyurvedicAlmanac, default_database_path


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
STYLESHEET_PATH = STATIC_DIR / "styles.css"
PAGE_SIZE = 12


def create_app(database_path: str | Path | None = None) -> FastAPI:
    """Create the web application, optionally bound to a specific SQLite file."""
    configured_path = (
        Path(database_path)
        if database_path is not None
        else Path(os.environ.get("HERBAL_ALMANAC_DATABASE", default_database_path()))
    )
    application = FastAPI(
        title="Herbal Almanac",
        description="A local research interface for Ayurvedic plant records.",
        version="0.1.0",
    )
    application.state.database_path = configured_path
    if not STYLESHEET_PATH.is_file():
        raise RuntimeError(f"Packaged stylesheet is missing: {STYLESHEET_PATH}")

    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATE_DIR)

    def get_database() -> AyurvedicAlmanac:
        return AyurvedicAlmanac(application.state.database_path)

    @application.get("/", response_class=HTMLResponse, name="dashboard")
    def dashboard(request: Request) -> Any:
        summary = get_database().dashboard_summary()
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"summary": summary, "active_page": "dashboard"},
        )

    @application.get("/herbs", response_class=HTMLResponse, name="herb_list")
    def herb_list(
        request: Request,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
    ) -> Any:
        database = get_database()
        matching_herbs = database.search_herbs(q.strip())
        total = len(matching_herbs)
        page_count = max(1, math.ceil(total / PAGE_SIZE))
        current_page = min(page, page_count)
        start = (current_page - 1) * PAGE_SIZE
        herbs = matching_herbs[start : start + PAGE_SIZE]
        return templates.TemplateResponse(
            request=request,
            name="herbs.html",
            context={
                "herbs": herbs,
                "query": q,
                "total": total,
                "page": current_page,
                "page_count": page_count,
                "active_page": "herbs",
            },
        )

    @application.get("/herbs/{herb_id}", response_class=HTMLResponse, name="herb_detail")
    def herb_detail(request: Request, herb_id: int) -> Any:
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")
        return templates.TemplateResponse(
            request=request,
            name="herb_detail.html",
            context={
                "herb": herb,
                "attributes": database.herb_attributes(herb_id),
                "doshas": database.herb_doshas(herb_id),
                "treatments": database.treatment_details(herb_id),
                "active_page": "herbs",
            },
        )

    return application


app = create_app()


def run() -> None:
    """Start the local development server."""
    import uvicorn

    uvicorn.run("herbal_almanac.web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
