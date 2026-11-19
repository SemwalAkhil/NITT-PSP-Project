from fastapi.testclient import TestClient

from herbal_almanac.database_operator import AyurvedicAlmanac
from herbal_almanac.web_app import create_app


def make_client(tmp_path):
    database_path = tmp_path / "web-gui.db"
    database = AyurvedicAlmanac(database_path)
    database.create_database()
    return TestClient(create_app(database_path)), database


def test_dashboard_shows_database_counts_and_recent_herbs(tmp_path):
    client, database = make_client(tmp_path)
    database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    illness_id = database.add_illness("Cough")
    database.add_treatment(1, illness_id)

    response = client.get("/")

    assert response.status_code == 200
    assert "Herbal Almanac" in response.text
    assert "Ocimum tenuiflorum" in response.text
    assert ">1<" in response.text


def test_herb_explorer_lists_and_searches_records(tmp_path):
    client, database = make_client(tmp_path)
    database.add_herb("Tulsi", botanical_name="Ocimum tenuiflorum")
    database.add_herb("Neem", botanical_name="Azadirachta indica")

    response = client.get("/herbs")
    assert response.status_code == 200
    assert "Tulsi" in response.text
    assert "Neem" in response.text

    search_response = client.get("/herbs", params={"q": "tulsi"})
    assert search_response.status_code == 200
    assert "Tulsi" in search_response.text
    assert "Neem" not in search_response.text


def test_herb_detail_shows_identity_attributes_doshas_and_treatments(tmp_path):
    client, database = make_client(tmp_path)
    herb_id = database.add_herb(
        "Tulsi", botanical_name="Ocimum tenuiflorum", family="Lamiaceae"
    )
    illness_id = database.add_illness("Cough")
    database.add_treatment(herb_id, illness_id)

    response = client.get(f"/herbs/{herb_id}")

    assert response.status_code == 200
    assert "Ocimum tenuiflorum" in response.text
    assert "Lamiaceae" in response.text
    assert "Cough" in response.text
    assert "Plant characteristics" in response.text
    assert "Dosha effects" in response.text


def test_missing_herb_returns_not_found(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/herbs/999")

    assert response.status_code == 404


def test_herb_search_rejects_unreasonably_long_query(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/herbs", params={"q": "x" * 101})

    assert response.status_code == 422


def test_dashboard_handles_empty_database(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert "Your library is ready to grow" in response.text

def test_stylesheet_is_served_with_css_content_type(tmp_path):
    client, _ = make_client(tmp_path)

    page = client.get("/")
    stylesheet_url = "/static/styles.css"

    assert page.status_code == 200
    assert stylesheet_url in page.text

    response = client.get(stylesheet_url)

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert ":root" in response.text
    assert "--paper:" in response.text
    assert ".sidebar" in response.text


def test_herb_pagination_with_many_records(tmp_path):
    client, database = make_client(tmp_path)
    # Seed 35 herbs so we span 3 pages (PAGE_SIZE=12: 12, 12, 11)
    for i in range(1, 36):
        name = f"Tulsi Specimen {i:02d}" if i <= 25 else f"Neem Specimen {i:02d}"
        database.add_herb(name, botanical_name=f"Botanical {i:02d}")

    # 1. Page 1 (/herbs)
    r1 = client.get("/herbs")
    assert r1.status_code == 200
    assert "Showing 1–12 of 35" in r1.text
    assert "page=2" in r1.text
    assert "Page 1 of 3" in r1.text

    # 2. Page 2 (/herbs?page=2)
    r2 = client.get("/herbs?page=2")
    assert r2.status_code == 200
    assert "Showing 13–24 of 35" in r2.text
    assert "page=1" in r2.text
    assert "page=3" in r2.text
    assert "Page 2 of 3" in r2.text

    # 3. Page 3 (/herbs?page=3)
    r3 = client.get("/herbs?page=3")
    assert r3.status_code == 200
    assert "Showing 25–35 of 35" in r3.text
    assert "page=2" in r3.text
    assert "Page 3 of 3" in r3.text

    # 4. Search query spanning multiple pages (/herbs?q=Tulsi)
    # 25 Tulsi herbs span 3 pages: 12, 12, 1
    rq1 = client.get("/herbs?q=Tulsi")
    assert rq1.status_code == 200
    assert "Showing 1–12 of 25" in rq1.text
    assert "q=Tulsi" in rq1.text
    assert "page=2" in rq1.text

    rq2 = client.get("/herbs?q=Tulsi&page=2")
    assert rq2.status_code == 200
    assert "Showing 13–24 of 25" in rq2.text
    assert "q=Tulsi" in rq2.text
    assert "page=1" in rq2.text
    assert "page=3" in rq2.text

    # 5. Out-of-range page clamps safely and returns 200
    r_out = client.get("/herbs?page=999")
    assert r_out.status_code == 200
    assert "Showing 25–35 of 35" in r_out.text
    assert "Page 3 of 3" in r_out.text

