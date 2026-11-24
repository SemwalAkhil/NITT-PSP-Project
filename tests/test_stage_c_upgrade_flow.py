from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from herbal_almanac.cli import app as cli_app
from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.schema_capability_gate import get_schema_version
from herbal_almanac.web_app import create_app


def test_stage_c_banner_visibility_v2_vs_v3(tmp_path: Path) -> None:
    # 1. On v2 database
    db_v2 = tmp_path / "v2.db"
    almanac_v2 = AyurvedicAlmanac(db_v2)
    almanac_v2.create_database()
    herb_id = almanac_v2.add_herb("Tulsi", source="manual")

    app_v2 = create_app(db_v2)
    client_v2 = TestClient(app_v2)

    # Check herb detail has banner and upgrade form
    res_detail_v2 = client_v2.get(f"/herbs/{herb_id}")
    assert res_detail_v2.status_code == 200
    assert "STAGE C CAPABILITY STATUS" in res_detail_v2.text
    assert 'action="/stage-c/upgrade"' in res_detail_v2.text
    assert "Upgrade database to Stage C" in res_detail_v2.text

    # Check herb form has banner and upgrade form
    res_form_v2 = client_v2.get("/herbs/add")
    assert res_form_v2.status_code == 200
    assert "STAGE C CAPABILITY STATUS" in res_form_v2.text
    assert 'action="/stage-c/upgrade"' in res_form_v2.text

    # 2. On v3 database
    almanac_v2.upgrade_to_stage_c()
    almanac_v2.run_stage_c_backfill()

    res_detail_v3 = client_v2.get(f"/herbs/{herb_id}")
    assert res_detail_v3.status_code == 200
    assert "STAGE C CAPABILITY STATUS" not in res_detail_v3.text
    assert 'action="/stage-c/upgrade"' not in res_detail_v3.text

    res_form_v3 = client_v2.get("/herbs/add")
    assert res_form_v3.status_code == 200
    assert "STAGE C CAPABILITY STATUS" not in res_form_v3.text


def test_stage_c_upgrade_route_execution_and_idempotency(tmp_path: Path) -> None:
    db_file = tmp_path / "upgrade_web.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()
    herb_id = almanac.add_herb("Ashwagandha", source="manual")

    app = create_app(db_file)
    client = TestClient(app)

    # Initial version is 2
    with almanac.connect() as conn:
        assert get_schema_version(conn) == 2

    # Call POST /stage-c/upgrade
    res = client.post(
        "/stage-c/upgrade",
        data={"next": f"/herbs/{herb_id}"},
        headers={"Host": "testserver", "Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    loc = res.headers["location"]
    assert loc.startswith(f"/herbs/{herb_id}?msg=")
    assert "successfully" in loc

    # Version is now 3
    with almanac.connect() as conn:
        assert get_schema_version(conn) == 3

    # Idempotent second call
    res_idempotent = client.post(
        "/stage-c/upgrade",
        data={"next": f"/herbs/{herb_id}"},
        headers={"Host": "testserver", "Origin": "http://testserver"},
        follow_redirects=False,
    )
    assert res_idempotent.status_code == 303
    loc2 = res_idempotent.headers["location"]
    assert "already" in loc2


def test_stage_c_upgrade_open_redirect_defense(tmp_path: Path) -> None:
    db_file = tmp_path / "redirect_defense.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()

    app = create_app(db_file)
    client = TestClient(app)

    malicious_targets = [
        "https://evil.com/phish",
        "http://evil.com",
        "//evil.com",
        "/\\evil.com",
        "javascript:alert(1)",
        "data:text/html,<script>evil</script>",
        "",
    ]
    for bad_target in malicious_targets:
        res = client.post(
            "/stage-c/upgrade",
            data={"next": bad_target},
            headers={"Host": "testserver", "Origin": "http://testserver"},
            follow_redirects=False,
        )
        assert res.status_code == 303
        loc = res.headers["location"]
        # Must redirect to "/" (with query string) and NOT external host
        assert loc.startswith("/?") or loc == "/", f"Failed for {bad_target}: got {loc}"


def test_stage_c_upgrade_csrf_protection(tmp_path: Path) -> None:
    db_file = tmp_path / "csrf_defense.db"
    almanac = AyurvedicAlmanac(db_file)
    almanac.create_database()

    app = create_app(db_file)
    client = TestClient(app)

    res = client.post(
        "/stage-c/upgrade",
        data={"next": "/herbs"},
        headers={"Host": "testserver", "Origin": "http://evil.com"},
    )
    assert res.status_code == 403


def test_cli_setup_defaults_to_v3(tmp_path: Path) -> None:
    db_file = tmp_path / "cli_v3_default.db"
    runner = CliRunner()

    result = runner.invoke(cli_app, ["setup", "--database", str(db_file)])
    assert result.exit_code == 0
    assert "Database ready (Stage C / schema v3):" in result.output

    almanac = AyurvedicAlmanac(db_file)
    with almanac.connect() as conn:
        assert get_schema_version(conn) == 3


def test_cli_setup_no_stage_c_creates_v2(tmp_path: Path) -> None:
    db_file = tmp_path / "cli_v2_explicit.db"
    runner = CliRunner()

    result = runner.invoke(cli_app, ["setup", "--database", str(db_file), "--no-stage-c"])
    assert result.exit_code == 0
    assert "Database ready:" in result.output
    assert "Stage C" not in result.output

    almanac = AyurvedicAlmanac(db_file)
    with almanac.connect() as conn:
        assert get_schema_version(conn) == 2
