"""GET /health is the liveness probe: public, cheap, stable shape."""


def test_health_ok(anonymous_client):
    r = anonymous_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "signal-sports-backend"}
