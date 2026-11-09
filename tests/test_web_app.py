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
