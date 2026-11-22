"""FastAPI web interface for browsing a local Herbal Almanac database.

Run with: uvicorn herbal_almanac.web_app:app --reload
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any

import shutil
import urllib.request

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
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
    herb_image_url,
    herb_vernacular_table,
    herb_name,
    qs,
)
from .herb_glossary import (
    resolve_herb,
    search_herb_glossary,
)


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
STYLESHEET_PATH = STATIC_DIR / "styles.css"
PAGE_SIZE = 12

# Max upload size: 5 MB
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Allowed image MIME types (detected via magic bytes)
_ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _detect_image_type(data: bytes) -> str | None:
    """Return MIME type string for recognised image magic bytes, or None."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _upload_dir(database_path: Path) -> Path:
    """Return (and create) the upload directory next to the database file."""
    env_dir = os.environ.get("HERBAL_ALMANAC_UPLOAD_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = database_path.parent / "uploads" / "herbs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_dir(database_path: Path) -> Path:
    """Return (and create) the image cache directory."""
    env_dir = os.environ.get("HERBAL_ALMANAC_CACHE_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = database_path.parent / "herbal_almanac_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _find_upload(upload_dir: Path, herb_id: int) -> Path | None:
    """Return the uploaded photo for herb_id if present, else None."""
    for ext in (".jpg", ".png", ".webp"):
        candidate = upload_dir / f"{herb_id}{ext}"
        if candidate.is_file():
            return candidate
    return None

CSV_FIELDS = {
    "herbs": (
        "id", "english_name", "original_name", "source", "source_record_id",
        "source_url", "retrieved_at", "botanical_name", "family",
    ),
    "illnesses": ("id", "english_name", "machine_generated", "verification_status"),
    "treatments": ("herb_id", "herb_name", "illness_id", "illness_name"),
    "attributes": (
        "herb_id", "herb_name", "field_name", "value", "source_text",
        "source_language", "machine_generated", "verification_status",
    ),
    "doshas": (
        "herb_id", "herb_name", "dosha", "effect", "source_expression", "source",
    ),
}


def sanitize_csv_cell(value: Any) -> str:
    """Sanitize cell value against CSV formula injection (DDE/spreadsheet execution).

    If the value starts with '=', '+', '-', or '@', prepend a single quote (').
    """
    if value is None:
        return ""
    val_str = str(value)
    if val_str and val_str[0] in ("=", "+", "-", "@"):
        return "'" + val_str
    return val_str


def generate_csv_response(rows: list[dict[str, Any]], fieldnames: list[str], filename: str) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        sanitized = {k: sanitize_csv_cell(row.get(k, "")) for k in fieldnames}
        writer.writerow(sanitized)
    bom_content = "\ufeff" + output.getvalue()
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return Response(content=bom_content.encode("utf-8"), media_type="text/csv", headers=headers)


def generate_json_response(data: Any, filename: str) -> Response:
    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "application/json; charset=utf-8",
    }
    return Response(content=json_bytes, media_type="application/json", headers=headers)


def verify_same_origin(request: Request) -> bool:
    """Validate that mutating form POST requests come from the same origin."""
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host:
        origin_host = origin.split("://")[-1].rstrip("/")
        if origin_host != host:
            return False
    referer = request.headers.get("referer")
    if referer and host:
        ref_host = referer.split("://")[-1].split("/")[0]
        if ref_host != host:
            return False
    return True


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
    templates.env.globals["herb_image_url"] = herb_image_url
    templates.env.filters["herb_image_url"] = herb_image_url
    templates.env.globals["herb_vernacular_table"] = herb_vernacular_table
    templates.env.filters["herb_vernacular_table"] = herb_vernacular_table
    templates.env.globals["resolve_herb"] = resolve_herb
    templates.env.filters["resolve_herb"] = resolve_herb
    templates.env.globals["search_herb_glossary"] = search_herb_glossary
    templates.env.filters["search_herb_glossary"] = search_herb_glossary
    templates.env.globals["herb_name"] = herb_name
    templates.env.filters["herb_name"] = herb_name
    templates.env.globals["qs"] = qs
    templates.env.filters["qs"] = qs

    def _css_version() -> str:
        try:
            return str(int(STYLESHEET_PATH.stat().st_mtime))
        except Exception:
            return "1"

    templates.env.globals["css_version"] = _css_version

    def get_database() -> AyurvedicAlmanac:
        return AyurvedicAlmanac(application.state.database_path)

    @application.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        favicon_path = STATIC_DIR / "favicon.svg"
        if favicon_path.is_file():
            return Response(
                content=favicon_path.read_bytes(),
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=86400"},
            )
        return Response(status_code=204)

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
        example_herbs: list[dict[str, Any]] = []
        example_conditions: list[dict[str, Any]] = []
        try:
            if application.state.database_path.is_file():
                db = get_database()
                with db._connection() as conn:
                    rows = conn.execute(
                        "SELECT id, original_name, english_name, botanical_name FROM herbs ORDER BY id LIMIT 3"
                    ).fetchall()
                    if rows:
                        example_herb_id = rows[0]["id"]
                        example_herbs = [
                            {
                                "id": r["id"],
                                "name": r["original_name"] or r["english_name"] or f"Herb {r['id']}",
                                "botanical": r["botanical_name"],
                            }
                            for r in rows
                        ]
                    cond_rows = conn.execute(
                        """
                        SELECT i.id, i.english_name, COUNT(t.herb_id) as herb_count
                        FROM illness i
                        JOIN treatment t ON i.id = t.illness_id
                        GROUP BY i.id
                        ORDER BY herb_count DESC
                        LIMIT 3
                        """
                    ).fetchall()
                    if cond_rows:
                        example_conditions = [
                            {
                                "id": cr["id"],
                                "name": cr["english_name"],
                                "herb_count": cr["herb_count"],
                            }
                            for cr in cond_rows
                        ]
        except Exception:
            example_herbs = []
            example_conditions = []
            example_herb_id = None

        return templates.TemplateResponse(
            request=request,
            name="guide.html",
            context={
                "active_page": "guide",
                "example_herb_id": example_herb_id,
                "example_herbs": example_herbs,
                "example_conditions": example_conditions,
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

    @application.get("/herbs/add", response_class=HTMLResponse, name="add_herb_form")
    def add_herb_form(request: Request) -> Any:
        return templates.TemplateResponse(
            request=request,
            name="herb_form.html",
            context={
                "active_page": "herbs",
                "error": None,
                "form_data": None,
            },
        )

    @application.post("/herbs/add", response_class=HTMLResponse, name="add_herb_post")
    async def add_herb_post(
        request: Request,
        english_name: str = Form(...),
        botanical_name: str | None = Form(None),
        family: str | None = Form(None),
        source: str | None = Form(None),
        source_record_id: int | None = Form(None),
        source_url: str | None = Form(None),
        photo: UploadFile | None = File(None),
    ) -> Any:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")

        form_data = {
            "english_name": english_name,
            "botanical_name": botanical_name,
            "family": family,
            "source": source,
            "source_record_id": source_record_id,
            "source_url": source_url,
        }

        photo_bytes: bytes | None = None
        photo_ext: str | None = None
        if photo is not None and getattr(photo, "filename", None):
            raw = await photo.read(_MAX_UPLOAD_BYTES + 1)
            if len(raw) > 0:
                if len(raw) > _MAX_UPLOAD_BYTES:
                    return templates.TemplateResponse(
                        request=request,
                        name="herb_form.html",
                        context={
                            "active_page": "herbs",
                            "error": "Image file exceeds 5 MB limit",
                            "form_data": form_data,
                        },
                        status_code=400,
                    )
                mime = _detect_image_type(raw[:12])
                if mime is None:
                    return templates.TemplateResponse(
                        request=request,
                        name="herb_form.html",
                        context={
                            "active_page": "herbs",
                            "error": "Unsupported image format; please upload JPEG, PNG, or WebP",
                            "form_data": form_data,
                        },
                        status_code=400,
                    )
                photo_bytes = raw
                photo_ext = _ALLOWED_IMAGE_TYPES[mime]

        database = get_database()
        try:
            herb_id = database.add_herb(
                english_name=english_name,
                source=source or None,
                source_record_id=source_record_id or None,
                source_url=source_url or None,
                botanical_name=botanical_name or None,
                family=family or None,
            )
            if photo_bytes and photo_ext:
                up_dir = _upload_dir(application.state.database_path)
                (up_dir / f"{herb_id}{photo_ext}").write_bytes(photo_bytes)
            return RedirectResponse(url=f"/herbs/{herb_id}", status_code=303)
        except (ValueError, sqlite3.Error) as err:
            return templates.TemplateResponse(
                request=request,
                name="herb_form.html",
                context={
                    "active_page": "herbs",
                    "error": str(err),
                    "form_data": form_data,
                },
                status_code=400,
            )

    # -------------------------------------------------------------------------
    # Herb Image Proxy / Cache  (Task 2)
    # -------------------------------------------------------------------------
    @application.get("/herbs/{herb_id}/image", name="herb_image")
    def herb_image_proxy(herb_id: int) -> Response:
        """Serve herb photo: uploaded > cached CCRAS > placeholder SVG. Never raises 500."""
        up_dir = _upload_dir(application.state.database_path)
        # 1. User-uploaded photo takes priority
        upload_path = _find_upload(up_dir, herb_id)
        if upload_path is not None:
            mime = _detect_image_type(upload_path.read_bytes()[:12]) or "image/jpeg"
            return Response(
                content=upload_path.read_bytes(),
                media_type=mime,
                headers={"Cache-Control": "public, max-age=86400"},
            )

        # 2. Disk-cached CCRAS image
        c_dir = _cache_dir(application.state.database_path)
        cached = c_dir / f"{herb_id}.jpg"
        if cached.is_file():
            return Response(
                content=cached.read_bytes(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600"},
            )

        # 3. Fetch from CCRAS
        try:
            database = get_database()
            herb = database.get_herb(herb_id)
            source_rid = herb["source_record_id"] if herb else None
            if source_rid is not None:
                url = f"https://dravya.ccras.org.in/resources/views/admin/required/upload/{source_rid}.jpg"
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Herbal Almanac; research use)"},
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > _MAX_UPLOAD_BYTES:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                mime = _detect_image_type(raw[:12])
                if mime and total <= _MAX_UPLOAD_BYTES:
                    cached.write_bytes(raw)
                    return Response(
                        content=raw,
                        media_type=mime,
                        headers={"Cache-Control": "public, max-age=3600"},
                    )
        except Exception:
            pass

        # 4. Fallback placeholder
        placeholder = STATIC_DIR / "placeholder-herb.svg"
        if placeholder.is_file():
            return Response(
                content=placeholder.read_bytes(),
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=60"},
            )
        raise HTTPException(status_code=404, detail="Image not available")

    # -------------------------------------------------------------------------
    # Photo Upload / Delete  (Task 4)
    # -------------------------------------------------------------------------
    @application.post("/herbs/{herb_id}/photo", name="herb_photo_upload")
    async def herb_photo_upload(
        request: Request,
        herb_id: int,
        photo: UploadFile = File(...),
    ) -> Response:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")
        database = get_database()
        if database.get_herb(herb_id) is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        raw = await photo.read(_MAX_UPLOAD_BYTES + 1)
        if len(raw) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image file exceeds 5 MB limit")
        mime = _detect_image_type(raw[:12])
        if mime is None:
            raise HTTPException(status_code=415, detail="Unsupported image format; upload JPEG, PNG, or WebP")

        ext = _ALLOWED_IMAGE_TYPES[mime]
        up_dir = _upload_dir(application.state.database_path)
        # Remove any existing uploads for this herb
        for old_ext in (".jpg", ".png", ".webp"):
            old = up_dir / f"{herb_id}{old_ext}"
            if old.is_file():
                old.unlink()
        dest = up_dir / f"{herb_id}{ext}"
        dest.write_bytes(raw)
        return RedirectResponse(url=f"/herbs/{herb_id}", status_code=303)

    @application.post("/herbs/{herb_id}/photo/delete", name="herb_photo_delete")
    def herb_photo_delete(request: Request, herb_id: int) -> Response:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")
        database = get_database()
        if database.get_herb(herb_id) is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        up_dir = _upload_dir(application.state.database_path)
        deleted = False
        for ext in (".jpg", ".png", ".webp"):
            p = up_dir / f"{herb_id}{ext}"
            if p.is_file():
                p.unlink()
                deleted = True
        if not deleted:
            raise HTTPException(status_code=404, detail="No uploaded photo found")
        return RedirectResponse(url=f"/herbs/{herb_id}", status_code=303)

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
                    "has_user_photo": _find_upload(_upload_dir(application.state.database_path), herb_id) is not None,
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

    @application.get("/illnesses/add", response_class=HTMLResponse, name="add_illness_form")
    def add_illness_form(request: Request) -> Any:
        return templates.TemplateResponse(
            request=request,
            name="illness_form.html",
            context={
                "active_page": "illnesses",
                "error": None,
                "form_data": None,
            },
        )

    @application.post("/illnesses/add", response_class=HTMLResponse, name="add_illness_post")
    def add_illness_post(
        request: Request,
        english_name: str = Form(...),
    ) -> Any:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")

        database = get_database()
        try:
            illness_id = database.add_illness(english_name)
            return RedirectResponse(url=f"/illnesses/{illness_id}", status_code=303)
        except (ValueError, sqlite3.Error) as err:
            return templates.TemplateResponse(
                request=request,
                name="illness_form.html",
                context={
                    "active_page": "illnesses",
                    "error": str(err),
                    "form_data": {"english_name": english_name},
                },
                status_code=400,
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

    # -------------------------------------------------------------------------
    # Treatments Management & Explorer
    # -------------------------------------------------------------------------
    @application.get("/treatments/add", response_class=HTMLResponse, name="add_treatment_form")
    def add_treatment_form(
        request: Request,
        herb_id: int | None = Query(default=None),
        illness_id: int | None = Query(default=None),
    ) -> Any:
        database = get_database()
        with database._connection() as conn:
            herbs = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, english_name, original_name, botanical_name FROM herbs ORDER BY id"
                ).fetchall()
            ]
            illnesses = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, english_name FROM illness ORDER BY english_name"
                ).fetchall()
            ]

        return templates.TemplateResponse(
            request=request,
            name="treatment_form.html",
            context={
                "active_page": "treatments",
                "herbs": herbs,
                "illnesses": illnesses,
                "selected_herb_id": herb_id,
                "selected_illness_id": illness_id,
                "error": None,
            },
        )

    @application.post("/treatments/add", response_class=HTMLResponse, name="add_treatment_post")
    def add_treatment_post(
        request: Request,
        herb_id: int = Form(...),
        illness_id: int = Form(...),
    ) -> Any:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")

        database = get_database()
        try:
            database.add_treatment(herb_id, illness_id)
            return RedirectResponse(url="/treatments", status_code=303)
        except (ValueError, sqlite3.Error) as err:
            with database._connection() as conn:
                herbs = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id, english_name, original_name, botanical_name FROM herbs ORDER BY id"
                    ).fetchall()
                ]
                illnesses = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT id, english_name FROM illness ORDER BY english_name"
                    ).fetchall()
                ]
            return templates.TemplateResponse(
                request=request,
                name="treatment_form.html",
                context={
                    "active_page": "treatments",
                    "herbs": herbs,
                    "illnesses": illnesses,
                    "selected_herb_id": herb_id,
                    "selected_illness_id": illness_id,
                    "error": str(err),
                },
                status_code=400,
            )

    # -------------------------------------------------------------------------
    # Treatments Explorer
    # -------------------------------------------------------------------------
    @application.get("/treatments", response_class=HTMLResponse, name="treatment_list")
    def treatment_list(
        request: Request,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
        language: str = Query(default="en"),
    ) -> Any:
        clean_lang = clean_language_param(language)
        database = get_database()
        all_treatments = database.all_records().get("treatments", [])
        clean_q = q.strip().lower()
        if clean_q:
            filtered = [
                t for t in all_treatments
                if clean_q in str(t.get("herb_name", "")).lower()
                or clean_q in str(t.get("illness_name", "")).lower()
                or clean_q == str(t.get("herb_id", ""))
                or clean_q == str(t.get("illness_id", ""))
            ]
        else:
            filtered = all_treatments

        treatment_page_size = 20
        total = len(filtered)
        page_count = max(1, math.ceil(total / treatment_page_size))
        current_page = min(page, page_count)
        start = (current_page - 1) * treatment_page_size
        items = filtered[start : start + treatment_page_size]

        return templates.TemplateResponse(
            request=request,
            name="treatments.html",
            context={
                "treatments": items,
                "query": q,
                "total": total,
                "page": current_page,
                "page_count": page_count,
                "active_page": "treatments",
                "current_language": clean_lang,
                "is_non_english": (clean_lang != "en"),
                "languages": [SUPPORTED_LANGUAGES[c] for c in ORDERED_LANGUAGE_CODES],
            },
        )

    # -------------------------------------------------------------------------
    # Attributes Explorer
    # -------------------------------------------------------------------------
    @application.get("/attributes", response_class=HTMLResponse, name="attributes_list")
    def attributes_list(
        request: Request,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
    ) -> Any:
        database = get_database()
        all_attrs = database.all_records().get("attributes", [])
        clean_q = q.strip().lower()
        if clean_q:
            filtered = [
                a for a in all_attrs
                if clean_q in str(a.get("field_name", "")).lower()
                or clean_q in str(a.get("value", "")).lower()
                or clean_q in str(a.get("herb_name", "")).lower()
                or clean_q in str(a.get("source_text", "")).lower()
            ]
        else:
            filtered = all_attrs

        attr_page_size = 30
        total = len(filtered)
        page_count = max(1, math.ceil(total / attr_page_size))
        current_page = min(page, page_count)
        start = (current_page - 1) * attr_page_size
        items = filtered[start : start + attr_page_size]

        return templates.TemplateResponse(
            request=request,
            name="attributes.html",
            context={
                "attributes": items,
                "query": q,
                "total": total,
                "page": current_page,
                "page_count": page_count,
                "herb": None,
                "active_page": "attributes",
            },
        )

    @application.get("/herbs/{herb_id}/attributes", response_class=HTMLResponse, name="herb_attributes_list")
    def herb_attributes_list(
        request: Request,
        herb_id: int,
        q: str = Query(default="", max_length=100),
        page: int = Query(default=1, ge=1),
    ) -> Any:
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        all_attrs = database.herb_attributes(herb_id)
        clean_q = q.strip().lower()
        if clean_q:
            filtered = [
                a for a in all_attrs
                if clean_q in str(a.get("field_name", "")).lower()
                or clean_q in str(a.get("value", "")).lower()
                or clean_q in str(a.get("source_text", "")).lower()
            ]
        else:
            filtered = all_attrs

        attr_page_size = 30
        total = len(filtered)
        page_count = max(1, math.ceil(total / attr_page_size))
        current_page = min(page, page_count)
        start = (current_page - 1) * attr_page_size
        items = filtered[start : start + attr_page_size]

        return templates.TemplateResponse(
            request=request,
            name="attributes.html",
            context={
                "attributes": items,
                "query": q,
                "total": total,
                "page": current_page,
                "page_count": page_count,
                "herb": herb,
                "active_page": "herbs",
            },
        )

    # -------------------------------------------------------------------------
    # Records Hub & Overview
    # -------------------------------------------------------------------------
    @application.get("/records", response_class=HTMLResponse, name="records_view")
    def records_view(
        request: Request,
        group: str = Query(default="herbs", pattern="^(herbs|illnesses|treatments|attributes|doshas)$"),
    ) -> Any:
        database = get_database()
        records = database.all_records()
        rows = records.get(group, [])
        columns = list(CSV_FIELDS.get(group, ()))
        if rows and not columns:
            columns = list(rows[0].keys())

        return templates.TemplateResponse(
            request=request,
            name="records.html",
            context={
                "records": records,
                "active_group": group,
                "group_rows": rows,
                "group_columns": columns,
                "active_page": "records",
            },
        )

    # -------------------------------------------------------------------------
    # Stage C GUI Migration Trigger
    # -------------------------------------------------------------------------
    @application.post("/stage-c/upgrade", response_class=RedirectResponse, name="stage_c_upgrade_post")
    def stage_c_upgrade_post(request: Request) -> Any:
        if not verify_same_origin(request):
            raise HTTPException(status_code=403, detail="Cross-site origin verification failed")

        database = get_database()
        try:
            database.upgrade_to_stage_c()
            return RedirectResponse(url="/", status_code=303)
        except Exception as err:
            raise HTTPException(status_code=500, detail=str(err))

    # -------------------------------------------------------------------------
    # JSON and CSV Exports
    # -------------------------------------------------------------------------
    @application.get("/export/herbs.csv", name="export_herbs_csv")
    def export_herbs_csv(q: str = Query(default=""), language: str = Query(default="en")) -> Response:
        database = get_database()
        herbs = database.search_herbs(q.strip())
        fieldnames = list(CSV_FIELDS["herbs"])
        return generate_csv_response(herbs, fieldnames, "herbs.csv")

    @application.get("/export/herbs.json", name="export_herbs_json")
    def export_herbs_json(q: str = Query(default=""), language: str = Query(default="en")) -> Response:
        database = get_database()
        herbs = database.search_herbs(q.strip())
        return generate_json_response(herbs, "herbs.json")

    @application.get("/export/illnesses.csv", name="export_illnesses_csv")
    def export_illnesses_csv(q: str = Query(default="")) -> Response:
        database = get_database()
        illnesses = database.search_illnesses(q.strip())
        fieldnames = list(CSV_FIELDS["illnesses"])
        return generate_csv_response(illnesses, fieldnames, "illnesses.csv")

    @application.get("/export/illnesses.json", name="export_illnesses_json")
    def export_illnesses_json(q: str = Query(default="")) -> Response:
        database = get_database()
        illnesses = database.search_illnesses(q.strip())
        return generate_json_response(illnesses, "illnesses.json")

    @application.get("/export/treatments.csv", name="export_treatments_csv")
    def export_treatments_csv(q: str = Query(default="")) -> Response:
        database = get_database()
        all_treatments = database.all_records().get("treatments", [])
        clean_q = q.strip().lower()
        if clean_q:
            filtered = [
                t for t in all_treatments
                if clean_q in str(t.get("herb_name", "")).lower()
                or clean_q in str(t.get("illness_name", "")).lower()
            ]
        else:
            filtered = all_treatments
        fieldnames = list(CSV_FIELDS["treatments"])
        return generate_csv_response(filtered, fieldnames, "treatments.csv")

    @application.get("/export/treatments.json", name="export_treatments_json")
    def export_treatments_json(q: str = Query(default="")) -> Response:
        database = get_database()
        all_treatments = database.all_records().get("treatments", [])
        clean_q = q.strip().lower()
        if clean_q:
            filtered = [
                t for t in all_treatments
                if clean_q in str(t.get("herb_name", "")).lower()
                or clean_q in str(t.get("illness_name", "")).lower()
            ]
        else:
            filtered = all_treatments
        return generate_json_response(filtered, "treatments.json")

    @application.get("/herbs/{herb_id}/export.csv", name="export_herb_detail_csv")
    def export_herb_detail_csv(herb_id: int) -> Response:
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        attributes = database.herb_attributes(herb_id)
        fieldnames = list(CSV_FIELDS["attributes"])
        return generate_csv_response(attributes, fieldnames, f"herb_{herb_id}_attributes.csv")

    @application.get("/herbs/{herb_id}/export.json", name="export_herb_detail_json")
    def export_herb_detail_json(herb_id: int) -> Response:
        database = get_database()
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        attributes = database.herb_attributes(herb_id)
        treatments = database.treatment_details(herb_id)
        doshas = database.herb_doshas(herb_id)

        data = {
            "herb": herb,
            "attributes": attributes,
            "treatments": treatments,
            "doshas": doshas,
        }
        return generate_json_response(data, f"herb_{herb_id}.json")

    return application


app = create_app()


def run() -> None:
    """Start the local development server."""
    import uvicorn

    uvicorn.run("herbal_almanac.web_app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    run()
