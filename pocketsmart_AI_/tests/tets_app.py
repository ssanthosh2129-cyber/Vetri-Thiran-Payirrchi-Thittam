import os
from pathlib import Path


# ============================================================
# TEST CONFIGURATION
# ============================================================

TEST_DATABASE = "/tmp/pocketsmart_test.db"

os.environ["DATABASE_PATH"] = TEST_DATABASE
os.environ["SECRET_KEY"] = "test-secret-key"

# Do not call external Gemini during tests.
os.environ["GEMINI_API_KEY"] = ""


# ============================================================
# IMPORT APPLICATION
# ============================================================

from fastapi.testclient import TestClient

from app import app, init_db


# ============================================================
# PREPARE DATABASE
# ============================================================

Path(
    TEST_DATABASE
).unlink(
    missing_ok=True
)

init_db()

client = TestClient(app)


# ============================================================
# HEALTH TEST
# ============================================================

def test_health():

    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "ok"


# ============================================================
# REGISTER + LOGIN + HOME PLAN
# ============================================================

def test_register_login_and_home_plan():

    response = client.post(
        "/api/register",
        json={
            "username": "testuser123",
            "email": "testuser123@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200


    response = client.post(
        "/api/login",
        json={
            "username": "testuser123",
            "password": "secret123",
        },
    )

    assert response.status_code == 200

    assert "access_token" in response.cookies


    token = response.cookies.get(
        "access_token"
    )

    client.cookies.set(
        "access_token",
        token
    )


    response = client.post(
        "/home-budget",
        json={
            "total_budget": 50000,

            "num_lights": 4,

            "num_fans": 2,

            "num_furniture": 1,

            "num_dining_tables": 1,

            "rooms": [
                "Living Room"
            ],

            "special_requirements":
                "Simple",
        },
    )


    assert response.status_code == 200

    data = response.json()

    assert data["total_budget"] == 50000

    assert "budget_breakdown" in data

    assert "remaining_budget" in data


# ============================================================
# PARTY TEST
# ============================================================

def test_party_budget():

    response = client.post(
        "/party-budget",
        json={
            "total_budget": 30000,

            "party_type":
                "Birthday Party",

            "num_guests": 50,

            "venue_preference":
                "Hall",

            "food_preference":
                "Vegetarian",

            "entertainment":
                "Music",

            "special_requirements":
                "Simple decoration",
        },
    )


    assert response.status_code == 200

    data = response.json()

    assert data["total_budget"] == 30000

    assert len(
        data["budget_breakdown"]
    ) > 0


# ============================================================
# CURRENT USER TEST
# ============================================================

def test_current_user():

    response = client.get(
        "/api/me"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["username"] == "testuser123"

    assert (
        data["email"]
        == "testuser123@example.com"
    )


# ============================================================
# HISTORY TEST
# ============================================================

def test_history():

    response = client.get(
        "/recommendation-history"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(
        data,
        list
    )

    assert len(data) >= 1