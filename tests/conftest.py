import time

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.flags import flags
from app.main import create_app

H = {"X-Tool-Secret": settings.tool_secret}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    flags.overrides.clear()
    monkeypatch.setattr(settings, "get_status_wait_s", 3.0)
    monkeypatch.setattr(settings, "dashboard_token", "")
    yield
    flags.overrides.clear()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "t.db")


@pytest.fixture
def client(db_path):
    app = create_app(db_path=db_path, sim_speed=0)
    with TestClient(app) as c:
        yield c


def tool(c, name, **body):
    r = c.post(f"/tools/{name}", headers=H, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def poll_until(c, rid, pred, timeout=20):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = tool(c, "get_status", request_id=rid)
        if pred(last):
            return last
    raise AssertionError(f"condition not met; last status: {last}")


def new_request(c, **kw):
    body = {"blood_group": "B positive", "units": 4, "location": "City General", "deadline_hours": 3}
    body.update(kw)
    return tool(c, "find_leads", **body)
