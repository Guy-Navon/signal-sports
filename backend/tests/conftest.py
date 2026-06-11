import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture(scope="session")
def client():
    application = create_app()
    with TestClient(application) as c:
        yield c
