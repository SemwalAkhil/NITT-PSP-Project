"""Herbal Almanac — Stage C.2 Work Package 6: Web Application Integration & GUI Routing

Provides version-aware web presentation services:
- Inspects schema_migrations capability status before rendering Stage C semantic models
- Renders enhanced Dravyaguna profile & Virya reconciliation views on Schema Version 3
- Gracefully degrades to standard legacy views with an informative capability banner on Version 2
- Exposes version-gated JSON API endpoints for programmatic clients
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Import existing application factory and database operator
from herbal_almanac.database_operator import AyurvedicAlmanac, default_database_path
from herbal_almanac.web_app import create_app as create_base_app

try:
    from .schema_capability_gate import (
        FeatureUnavailableError,
        MigrationError,
        get_schema_version,
        validate_schema_migration_ledger,
    )
    from .repository_api import (
        herb_dravyaguna_profile,
        reconcile_herb_virya,
    )
except ImportError:
    from schema_capability_gate import (
        FeatureUnavailableError,
        MigrationError,
        get_schema_version,
        validate_schema_migration_ledger,
    )
    from repository_api import (
        herb_dravyaguna_profile,
        reconcile_herb_virya,
    )

STAGE_C_DIR = Path(__file__).resolve().parent
STAGE_C_TEMPLATE_DIR = STAGE_C_DIR / "templates"
PACKAGE_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "src" / "herbal_almanac" / "templates"


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


def create_stage_c_app(database_path: str | Path | None = None) -> FastAPI:
    """Creates a version-aware FastAPI application integrating Stage C semantic features."""
    app = create_base_app(database_path)

    # Initialize Jinja2 templates searching Stage C templates first, then package templates
    templates = Jinja2Templates(directory=[str(STAGE_C_TEMPLATE_DIR), str(PACKAGE_TEMPLATE_DIR)])

    def get_db_connection() -> sqlite3.Connection:
        conn = sqlite3.connect(app.state.database_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    # ------------------------------------------------------------------------
    # 1. Version-Aware Herb Detail Route (Overrides legacy herb_detail)
    # ------------------------------------------------------------------------
    # Remove existing legacy herb_detail route so the version-aware handler takes precedence
    app.router.routes = [r for r in app.router.routes if getattr(r, "name", None) != "herb_detail"]

    @app.get("/herbs/{herb_id}", response_class=HTMLResponse, name="herb_detail")
    def version_aware_herb_detail(
        request: Request,
        herb_id: int,
        language: str = Query(default="en", pattern="^(en|hi|sa)$"),
        include_disputed: bool = Query(default=False),
        include_provisional: bool = Query(default=False),
    ) -> Any:
        database = AyurvedicAlmanac(app.state.database_path)
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        conn = get_db_connection()
        try:
            capability = get_database_capability(conn)
            is_v3 = capability["stage_c_available"]

            semantic_profile: dict[str, Any] | None = None
            virya_recon: dict[str, Any] | None = None

            if is_v3:
                semantic_profile = herb_dravyaguna_profile(
                    conn,
                    herb_id,
                    language=language,
                    include_disputed=include_disputed,
                    include_provisional=include_provisional,
                )
                virya_recon = reconcile_herb_virya(conn, herb_id)

            return templates.TemplateResponse(
                request=request,
                name="herb_detail_semantic.html",
                context={
                    "herb": herb,
                    "attributes": database.herb_attributes(herb_id),
                    "doshas": database.herb_doshas(herb_id),
                    "treatments": database.treatment_details(herb_id),
                    "is_version_3": is_v3,
                    "semantic_profile": semantic_profile,
                    "virya_reconciliation": virya_recon,
                    "active_page": "herbs",
                },
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------------
    # 2. Virya Reconciliation GUI Dashboard Route
    # ------------------------------------------------------------------------
    @app.get("/stage-c/reconciliation/{herb_id}", response_class=HTMLResponse, name="virya_reconciliation_gui")
    def virya_reconciliation_dashboard(request: Request, herb_id: int) -> Any:
        database = AyurvedicAlmanac(app.state.database_path)
        herb = database.get_herb(herb_id)
        if herb is None:
            raise HTTPException(status_code=404, detail="Herb not found")

        conn = get_db_connection()
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

    # ------------------------------------------------------------------------
    # 3. Dedicated Stage C JSON API Endpoints
    # ------------------------------------------------------------------------
    @app.get("/api/stage-c/status")
    def api_stage_c_status() -> Any:
        conn = get_db_connection()
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

    @app.get("/api/stage-c/herbs/{herb_id}/profile")
    def api_herb_dravyaguna_profile(
        herb_id: int,
        language: str = Query(default="en", pattern="^(en|hi|sa)$"),
        include_disputed: bool = Query(default=False),
        include_provisional: bool = Query(default=False),
    ) -> Any:
        conn = get_db_connection()
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

    @app.get("/api/stage-c/herbs/{herb_id}/reconciliation")
    def api_herb_virya_reconciliation(herb_id: int) -> Any:
        conn = get_db_connection()
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

    return app
