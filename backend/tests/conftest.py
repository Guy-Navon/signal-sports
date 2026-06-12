import os
import tempfile
import pytest
from fastapi.testclient import TestClient

# Set an isolated SQLite DB path BEFORE any app module is imported.
# This must run at module level so that when app.db.database is first imported
# (inside the fixture below), it picks up the test URL.
_tmp_dir = tempfile.mkdtemp(prefix="signal_sports_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"


@pytest.fixture(scope="session")
def client():
    # Import app modules AFTER the DATABASE_URL env var is set above.
    from app.main import create_app
    application = create_app()
    # TestClient enters the lifespan: creates tables and seeds the test DB.
    with TestClient(application) as c:
        yield c
