def test_system_state_endpoint_returns_stubbed_values(api_client):
    client, stub = api_client

    response = client.get("/system/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tunnel_level_m"] == stub.system_state.tunnel_level_m
    assert payload["pumps"][0]["pump_id"] == "P1"


def test_system_forecasts_endpoint_returns_bundle(api_client):
    client, stub = api_client

    response = client.get("/system/forecasts")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list) and len(payload) == len(stub.forecasts)
    assert payload[0]["metric"] == "inflow"
    assert len(payload[0]["points"]) == 3


def test_system_schedule_endpoint_returns_recommendation(api_client):
    client, stub = api_client

    response = client.get("/system/schedule")

    assert response.status_code == 200
    payload = response.json()
    assert payload["horizon_minutes"] == stub.schedule.horizon_minutes
    assert payload["entries"][0]["pump_id"] == "P1"


def test_weather_forecast_endpoint_passes_body_to_agents(api_client):
    client, stub = api_client

    response = client.post(
        "/weather/forecast",
        json={"lookahead_hours": 6, "location": "Espoo"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 6
    assert stub.last_weather_request == {"lookahead_hours": 6, "location": "Espoo"}


def test_alerts_endpoint_returns_static_payload(api_client):
    client, _ = api_client

    response = client.get("/alerts/")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["level"] == "warning"
    assert payload[0]["id"] == "alert-1"
