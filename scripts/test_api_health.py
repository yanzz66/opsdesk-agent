
"""Test OpsDesk FastAPI health endpoints."""

from fastapi.testclient import TestClient

from api.app import app


client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Welcome to OpsDesk Agent API"
    assert data["docs"] == "/docs"

    print("PASS: Root endpoint")


def test_health():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "OpsDesk Agent API"
    assert data["version"] == "1.0.0"

    print("PASS: Health endpoint")


def test_openapi():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    data = response.json()

    assert data["info"]["title"] == "OpsDesk Agent API"

    print("PASS: OpenAPI endpoint")


if __name__ == "__main__":
    test_root()
    test_health()
    test_openapi()

    print("\nAll API health tests passed!")