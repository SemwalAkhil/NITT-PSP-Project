"""FastAPI web interface for browsing a local Herbal Almanac database.

Run with: uvicorn herbal_almanac.web_app:app --reload
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database_operator import AyurvedicAlmanac, default_database_path
from .schema_capability_gate import (
    FeatureUnavailableError,
    MigrationError,
    validate_schema_migration_ledger,
)
from .repository_api import (
    herb_dravyaguna_profile,
    reconcile_herb_virya,
)
from .illness_glossary import (
    ORDERED_LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    resolve_illness,
    search_glossary,
)
from .herb_view import (
    clean_family,
    format_retrieved,
    dedupe_properties,
    group_properties_by_domain,
    virya_consensus,
    dedupe_dosha_effects,
    group_attributes,
)


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
STYLESHEET_PATH = STATIC_DIR / "styles.css"
PAGE_SIZE = 12


def clean_language_param(language: str | None) -> str:
    """Validates language query parameter, falling back to 'en' if unknown."""
    if not language:
        return "en"
    clean = language.strip().lower()
    return clean if clean in SUPPORTED_LANGUAGES else "en"


def format_readable_illness(name: str | None) -> str:
    """Format ITRANS/Harvard-Kyoto transliterated illness names into readable text.

    Renders readable text (first letter uppercase, rest lowercase) without
    altering stored database records.
    Examples:
        'KAsa' -> 'Kasa'
        'AgnimAndya' -> 'Agnimandya'
        'khAlityam/khalati' -> 'Khalityam/Khalati'
    """
    if not name:
        return ""
    stripped = name.strip()
    if not stripped:
        return ""
    slash_parts = stripped.split("/")
    formatted_slash_parts = []
    for slash_part in slash_parts:
        words = slash_part.split()
        formatted_slash_parts.append(" ".join(w.capitalize() for w in words))
    return "/".join(formatted_slash_parts)


def get_database_capability(conn: sqlite3.Connection) -> dict[str, Any]:
    """Inspects schema_migrations ledger and determines Stage C feature availability."""
    try:
        version = validate_schema_migration_ledger(conn)
        return {
            "version": version,
            "stage_c_available": (version == 3),
            "is_corrupt_ledger": False,
            "error": None,
        }
    except MigrationError as e:
        return {
            "version": None,
            "stage_c_available": False,
            "is_corrupt_ledger": True,
            "error": str(e),
        }
    except Exception as e:
        return {
            "version": None,
            "stage_c_available": False,
            "is_corrupt_ledger": True,
            "error": str(e),
        }


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
    templates.env.filters["readable_illness"] = format_readable_illness
    templates.env.filters["clean_family"] = clean_family
    templates.env.filters["format_retrieved"] = format_retrieved
    templates.env.globals["resolve_illness"] = resolve_illness
    templates.env.filters["resolve_illness"] = resolve_illness
    templates.env.globals["supported_languages"] = SUPPORTED_LANGUAGES
    templates.env.globals["ordered_language_codes"] = ORDERED_LANGUAGE_CODES

    def get_database() -> AyurvedicAlmanac:
        return AyurvedicAlmanac(application.state.database_path)

    @application.get("/", response_class=HTMLResponse, name="dashboard")
    def dashboard(request: Request, language: str = Query(default="en")) -> Any:
        clean_lang = clean_language_param(language)
        summary = get_database().dashboard_summary()
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "summary": summary,
                "active_page": "dashboard",
                "current_language": clean_lang,
                "is_non_english": (clean_lang != "en"),
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    @application.get("/guide", response_class=HTMLResponse, name="guide")
    def guide(request: Request) -> Any:
        example_herb_id = None
        try:
            if application.state.database_path.is_file():
                db = get_database()
                with db._connection() as conn:
                    row = conn.execute("SELECT id FROM herbs ORDER BY id LIMIT 1").fetchone()
                    if row:
                        example_herb_id = row[0]
        except Exception:
            example_herb_id = None

        return templates.TemplateResponse(
            request=request,
            name="guide.html",
            context={
                "active_page": "guide",
                "example_herb_id": example_herb_id,
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    @application.get("/herbs", response_class=HTMLResponse, name="herb_list")
    def herb_list(
        request: Request,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
        language: str = Query(default="en"),
    ) -> Any:
        import urllib.parse
        from fastapi.responses import RedirectResponse

        clean_lang = clean_language_param(language)
        database = get_database()
        clean_q = q.strip()
        matching_herbs = database.search_herbs(clean_q)

        # Route illness queries from global/herb search box to /illnesses if 0 herbs match
        if clean_q and not matching_herbs:
            if search_glossary(clean_q) or resolve_illness(clean_q).matched or database.search_illnesses(clean_q):
                return RedirectResponse(
                    url=f"/illnesses?q={urllib.parse.quote(clean_q)}&language={clean_lang}",
                    status_code=303,
                )

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
                "page_size": PAGE_SIZE,
                "active_page": "herbs",
                "current_language": clean_lang,
                "is_non_english": (clean_lang != "en"),
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    @application.get("/herbs/{herb_id}", response_class=HTMLResponse, name="herb_detail")
    def herb_detail(
        request: Request,
        herb_id: int,
        language: str = Query(default="en"),
        include_disputed: bool = Query(default=False),
        include_provisional: bool = Query(default=False),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        conn = sqlite3.connect(application.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            capability = get_database_capability(conn)
            is_v3 = capability["stage_c_available"]

            semantic_profile: dict[str, Any] | None = None
            virya_recon: dict[str, Any] | None = None

            if is_v3:
                dravyaguna_lang = clean_lang if clean_lang in ("en", "hi", "sa") else "en"
                semantic_profile = herb_dravyaguna_profile(
                    conn,
                    herb_id,
                    language=dravyaguna_lang,
                    include_disputed=include_disputed,
                    include_provisional=include_provisional,
                )
                virya_recon = reconcile_herb_virya(conn, herb_id)

            attributes = database.herb_attributes(herb_id)
            doshas = database.herb_doshas(herb_id)

            if semantic_profile:
                raw_props = semantic_profile.get("properties", [])
                deduped_props = dedupe_properties(raw_props)
                grouped_props = group_properties_by_domain(raw_props)
                virya_summary = virya_consensus(raw_props)
                dosha_view = dedupe_dosha_effects(semantic_profile.get("dosha_effects", []))
            else:
                deduped_props = []
                grouped_props = group_properties_by_domain([])
                virya_summary = None
                dosha_view = dedupe_dosha_effects(doshas)

            grouped_attrs = group_attributes(attributes)

            return templates.TemplateResponse(
                request=request,
                name="herb_detail_semantic.html",
                context={
                    "herb": herb,
                    "attributes": attributes,
                    "doshas": doshas,
                    "treatments": database.treatment_details(herb_id),
                    "is_version_3": is_v3,
                    "semantic_profile": semantic_profile,
                    "virya_reconciliation": virya_recon,
                    "deduped_properties": deduped_props,
                    "grouped_properties": grouped_props,
                    "virya_summary": virya_summary,
                    "dosha_view": dosha_view,
                    "grouped_attributes": grouped_attrs,
                    "active_page": "herbs",
                    "current_language": clean_lang,
                    "is_non_english": (clean_lang != "en"),
                    "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
                },
            )
        finally:
            conn.close()

    @application.get("/stage-c/reconciliation/{herb_id}", response_class=HTMLResponse, name="virya_reconciliation_gui")
    def virya_reconciliation_dashboard(request: Request, herb_id: int) -> Any:
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        conn = sqlite3.connect(application.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            capability = get_database_capability(conn)
            if capability.get("is_corrupt_ledger"):
                raise HTTPException(
                    status_code=500,
                    detail=f"Database migration ledger error: {capability['error']}",
                )
            if not capability["stage_c_available"]:
                raise HTTPException(
                    status_code=501,
                    detail="Stage C normalized semantic features require schema version 3 (current database version is 2). Apply Migration 3 to enable Dravyaguna semantic profiles.",
                )

            report = reconcile_herb_virya(conn, herb_id)
            return templates.TemplateResponse(
                request=request,
                name="virya_reconciliation.html",
                context={
                    "herb": herb,
                    "report": report,
                    "active_page": "herbs",
                },
            )
        finally:
            conn.close()

    @application.get("/illnesses", response_class=HTMLResponse, name="illness_list")
    def illness_list(
        request: Request,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
        language: str = Query(default="en"),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        matching = database.illness_summaries(q.strip())
        total = len(matching)
        page_count = max(1, math.ceil(total / PAGE_SIZE))
        current_page = min(page, page_count)
        start = (current_page - 1) * PAGE_SIZE
        illnesses = matching[start : start + PAGE_SIZE]
        return templates.TemplateResponse(
            request=request,
            name="illnesses.html",
            context={
                "illnesses": illnesses,
                "query": q,
                "total": total,
                "page": current_page,
                "page_count": page_count,
                "page_size": PAGE_SIZE,
                "active_page": "illnesses",
                "current_language": clean_lang,
                "is_non_english": (clean_lang != "en"),
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    @application.get("/illnesses/{illness_id}", response_class=HTMLResponse, name="illness_detail")
    def illness_detail(
        request: Request,
        illness_id: int,
        language: str = Query(default="en"),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        illness = database.get_illness(illness_id)
        if illness is None:
            raise HTTPException(status_code=404, detail="Illness not found")
        herbs = database.herbs_for_illness(illness_id)
        return templates.TemplateResponse(
            request=request,
            name="illness_detail.html",
            context={
                "illness": illness,
                "herbs": herbs,
                "active_page": "illnesses",
                "current_language": clean_lang,
                "is_non_english": (clean_lang != "en"),
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    @application.get("/api/illnesses")
    def api_illness_list(
        q: str = Query(default="", max_length=100),
        language: str = Query(default="en"),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        matching = database.illness_summaries(q.strip())
        enriched: list[dict[str, Any]] = []
        for item in matching:
            res = resolve_illness(item.get("english_name"))
            enriched.append({
                **item,
                "english": res.english,
                "english_synonyms": res.english_synonyms,
                "hindi": res.get_label("hi"),
                "sanskrit": res.get_label("sa"),
                "label": res.get_label(clean_lang),
                "language": clean_lang,
                "kind": res.kind,
                "matched": res.matched,
                "origin": res.origin,
                "verification": res.verification,
            })
        return enriched

    @application.get("/api/illnesses/{illness_id}/herbs")
    def api_illness_herbs(
        illness_id: int,
        language: str = Query(default="en"),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        illness = database.get_illness(illness_id)
        if illness is None:
            raise HTTPException(status_code=404, detail=f"Illness with id {illness_id} not found")
        herbs = database.herbs_for_illness(illness_id)
        res = resolve_illness(illness.get("english_name"))
        enriched: list[dict[str, Any]] = []
        for h in herbs:
            enriched.append({
                **h,
                "english": res.english,
                "english_synonyms": res.english_synonyms,
                "hindi": res.get_label("hi"),
                "sanskrit": res.get_label("sa"),
                "label": res.get_label(clean_lang),
                "language": clean_lang,
                "origin": res.origin,
                "verification": res.verification,
                "kind": res.kind,
            })
        return enriched

    @application.get("/api/stage-c/status")
    def api_stage_c_status() -> Any:
        conn = sqlite3.connect(application.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            capability = get_database_capability(conn)
            try:
                ledger = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY rowid ASC").fetchall()]
            except Exception:
                ledger = []
            return {
                "schema_version": capability["version"],
                "stage_c_available": capability["stage_c_available"],
                "is_corrupt_ledger": capability["is_corrupt_ledger"],
                "ledger": ledger,
                "error": capability["error"],
            }
        finally:
            conn.close()

    @application.get("/api/stage-c/herbs/{herb_id}/profile")
    def api_herb_dravyaguna_profile(
        herb_id: int,
        language: str = Query(default="en", pattern="^(en|hi|sa)$"),
        include_disputed: bool = Query(default=False),
        include_provisional: bool = Query(default=False),
    ) -> Any:
        conn = sqlite3.connect(application.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            capability = get_database_capability(conn)
            if capability.get("is_corrupt_ledger"):
                raise HTTPException(
                    status_code=500,
                    detail=f"Database migration ledger error: {capability['error']}",
                )
            if not capability["stage_c_available"]:
                raise HTTPException(
                    status_code=501,
                    detail="Stage C normalized semantic features require schema version 3 (current database version is 2). Apply Migration 3 to enable Dravyaguna semantic profiles.",
                )
            return herb_dravyaguna_profile(
                conn,
                herb_id,
                language=language,
                include_disputed=include_disputed,
                include_provisional=include_provisional,
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Herb with id {herb_id} not found")
        finally:
            conn.close()

    @application.get("/api/stage-c/herbs/{herb_id}/reconciliation")
    def api_herb_virya_reconciliation(herb_id: int) -> Any:
        conn = sqlite3.connect(application.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            capability = get_database_capability(conn)
            if capability.get("is_corrupt_ledger"):
                raise HTTPException(
                    status_code=500,
                    detail=f"Database migration ledger error: {capability['error']}",
                )
            if not capability["stage_c_available"]:
                raise HTTPException(
                    status_code=501,
                    detail="Stage C normalized semantic features require schema version 3 (current database version is 2). Apply Migration 3 to enable Dravyaguna semantic profiles.",
                )
            return reconcile_herb_virya(conn, herb_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Herb with id {herb_id} not found")
        finally:
            conn.close()

    return application


app = create_app()


def run() -> None:
    """Start the local development server."""
    import uvicorn

    uvicorn.run("herbal_almanac.web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
