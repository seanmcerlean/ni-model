def test_health_endpoint_is_a_cheap_liveness_probe(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mcp_endpoint_is_mounted(client):
    response = client.get(
        "/mcp/",
        headers={"Accept": "application/json, text/event-stream"},
    )

    assert response.status_code != 404
