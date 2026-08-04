import pytest


def test_population_summary_total(client):
    response = client.get("/api/population/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_population"] == 100


def test_population_summary_schema(client):
    data = client.get("/api/population/summary").json()
    assert "age_stats" in data
    assert "religious_breakdown" in data
    assert "probable_community_breakdown" in data
    assert "gender_breakdown" in data
    assert data["age_stats"]["average"] > 0


def test_population_summary_religious_breakdown(client):
    data = client.get("/api/population/summary").json()
    rb = data["religious_breakdown"]
    assert rb["catholic"] == 50
    assert rb["protestant"] == 30
    assert rb["other"] == 20


def test_population_by_location_returns_list(client):
    response = client.get("/api/population/by-location")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3


def test_population_by_location_totals(client):
    data = client.get("/api/population/by-location").json()
    totals = {item["location"]: item["total"] for item in data}
    assert totals["belfast"] == 50
    assert totals["derry_strabane"] == 30
    assert totals["antrim_and_newtownabbey"] == 20


def test_population_by_location_religious_breakdown(client):
    data = client.get("/api/population/by-location").json()
    belfast = next(d for d in data if d["location"] == "belfast")
    assert belfast["religious_breakdown"]["catholic"] == 50


def test_location_detail_valid(client):
    response = client.get("/api/population/location/belfast")
    assert response.status_code == 200
    data = response.json()
    assert data["location"] == "belfast"
    assert data["total"] == 50


def test_location_detail_schema(client):
    data = client.get("/api/population/location/derry_strabane").json()
    assert "religious_breakdown" in data
    assert "gender_breakdown" in data
    assert "origin_breakdown" in data
    assert "age_bands" in data


def test_location_detail_age_bands(client):
    data = client.get("/api/population/location/belfast").json()
    bands = data["age_bands"]
    assert "18-35" in bands
    assert "36-50" in bands
    assert sum(bands.values()) == 50


def test_location_detail_origin_breakdown(client):
    data = client.get("/api/population/location/antrim_and_newtownabbey").json()
    assert data["origin_breakdown"]["gb"] == 20


def test_location_detail_invalid(client):
    response = client.get("/api/population/location/NOWHERE")
    assert response.status_code == 404


def test_location_detail_case_insensitive(client):
    upper = client.get("/api/population/location/DERRY_STRABANE")
    lower = client.get("/api/population/location/derry_strabane")
    assert upper.status_code == 200
    assert lower.status_code == 200
    assert upper.json()["total"] == lower.json()["total"]


def test_voting_prediction_status(client):
    response = client.get("/api/population/voting-prediction")
    assert response.status_code == 200


def test_voting_prediction_supports_probable_community_basis(client):
    response = client.get("/api/population/voting-prediction?community_basis=probable")
    assert response.status_code == 200
    assert response.json()["source"]["community_basis"] == "probable"
    assert response.json()["source"]["community_basis_estimated"] is True


def test_voting_prediction_schema(client):
    data = client.get("/api/population/voting-prediction").json()
    assert "total_population" in data
    assert "unite" in data
    assert "remain" in data
    assert "undecided" in data
    assert "unite_share" in data
    assert "remain_share" in data
    assert "undecided_share" in data
    assert "by_location" in data
    assert "eligible_population" in data
    assert "projected_turnout" in data
    assert "intervals" in data
    assert len(data["scenarios"]) == 3
    assert data["source"]["id"] == "lucidtalk_winter_2025"
    assert data["source"]["sample_size"] == 1051


def test_voting_prediction_supports_nilt_alternative(client):
    data = client.get("/api/population/voting-prediction?calibration=nilt_2024").json()
    assert data["source"]["id"] == "nilt_2024"
    assert data["source"]["sample_size"] == 1199


def test_voting_prediction_rejects_unknown_calibration(client):
    response = client.get("/api/population/voting-prediction?calibration=unknown")
    assert response.status_code == 422


def test_voting_prediction_accepts_custom_lucidtalk_baseline(client):
    response = client.get(
        "/api/population/voting-prediction"
        "?custom_unite=50&custom_remain=40&custom_undecided=10"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["source"]["id"] == "custom_lucidtalk"
    assert data["unite_share"] == pytest.approx(0.50, abs=0.001)
    assert data["by_location"]["derry_strabane"]["unite_share"] != pytest.approx(
        data["by_location"]["belfast"]["unite_share"]
    )


@pytest.mark.parametrize(
    "query",
    [
        "custom_unite=50&custom_remain=40",
        "custom_unite=50&custom_remain=50&custom_undecided=10",
    ],
)
def test_voting_prediction_rejects_incomplete_or_unbalanced_custom_baseline(
    client, query
):
    assert client.get(f"/api/population/voting-prediction?{query}").status_code == 422


def test_voting_prediction_total_matches_population(client):
    data = client.get("/api/population/voting-prediction").json()
    assert data["total_population"] == 100


def test_voting_prediction_shares_sum_to_one(client):
    data = client.get("/api/population/voting-prediction").json()
    total = data["unite_share"] + data["remain_share"] + data["undecided_share"]
    assert total == pytest.approx(1.0, abs=0.01)


def test_voting_prediction_reproduces_published_lucidtalk_baseline(client):
    data = client.get("/api/population/voting-prediction").json()
    assert data["unite_share"] == pytest.approx(0.41 / 0.99, abs=0.001)
    assert data["remain_share"] == pytest.approx(0.48 / 0.99, abs=0.001)
    assert data["undecided_share"] == pytest.approx(0.10 / 0.99, abs=0.001)


@pytest.mark.parametrize(
    "calibration,expected_unite",
    [
        ("lucidtalk_summer_2021_high", 0.42),
        ("lucidtalk_winter_2024_low", 0.39 / 0.99),
    ],
)
def test_voting_prediction_supports_lucidtalk_five_year_extremes(
    client, calibration, expected_unite
):
    data = client.get(
        f"/api/population/voting-prediction?calibration={calibration}"
    ).json()
    assert data["source"]["id"] == calibration
    assert data["unite_share"] == pytest.approx(expected_unite, abs=0.001)


def test_voting_prediction_by_location_has_all_locations(client):
    data = client.get("/api/population/voting-prediction").json()
    assert "belfast" in data["by_location"]
    assert "derry_strabane" in data["by_location"]
    assert "antrim_and_newtownabbey" in data["by_location"]


def test_voting_prediction_can_skip_unused_location_breakdown(client):
    data = client.get(
        "/api/population/voting-prediction?include_locations=false"
    ).json()
    assert data["by_location"] == {}
