"""FastAPI 后端 API 测试。"""

from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "HDU" in resp.json()["name"]


def test_auth_status_not_logged_in():
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["logged_in"] is False


def test_friends_list():
    resp = client.get("/api/friends")
    assert resp.status_code == 200
    assert "friends" in resp.json()


def test_plans_list():
    resp = client.get("/api/plans")
    assert resp.status_code == 200
    assert "plans" in resp.json()


def test_schedules_list():
    resp = client.get("/api/schedules")
    assert resp.status_code == 200
    assert "schedules" in resp.json()


def test_scheduler_status():
    resp = client.get("/api/schedules/status")
    assert resp.status_code == 200
    assert "running" in resp.json()


def test_checkin_not_logged_in():
    resp = client.post("/api/checkin/12345")
    assert resp.status_code == 401


def test_bookings_not_logged_in():
    resp = client.get("/api/bookings")
    assert resp.status_code == 401
