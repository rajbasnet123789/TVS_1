import pytest
import uuid
from unittest.mock import AsyncMock
from app.auth.service import seed_roles, seed_super_admin
from app.config import settings


@pytest.fixture
async def auth_headers(db_session):
    await seed_roles(db_session)
    await seed_super_admin(db_session)
    await db_session.commit()

    from app.auth.service import create_access_token
    from sqlalchemy import select
    from app.auth.models import User

    res = await db_session.execute(select(User).where(User.email == "admin@poultry.farm"))
    user = res.scalar_one()

    token = create_access_token(str(user.id), "super_admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_profit_loss_auth_required(client):
    response = await client.post("/v1/analytics/profit-loss", json={
        "purchase_price_per_chick": 30.0,
        "num_chickens": 100,
        "price_per_chicken": 120.0,
        "duration_days": 30,
        "feed_cost_per_chicken_per_day": 0.15,
        "num_labourers": 2,
        "labour_rate_per_day": 300.0,
        "other_costs": 50.0,
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profit_loss_defaults(client, auth_headers, monkeypatch):
    # Mock health context to return no active detections/health score
    async def mock_health_summary(start, end, farm_id=None):
        return None
    async def mock_detected_chickens(start, end, farm_id=None):
        return []

    monkeypatch.setattr("app.health.queries.query_health_summary", mock_health_summary)
    monkeypatch.setattr("app.detection.queries.query_detected_chickens", mock_detected_chickens)

    payload = {
        "purchase_price_per_chick": 30.0,
        "num_chickens": 100,
        "price_per_chicken": 120.0,
        "duration_days": 30,
        "feed_cost_per_chicken_per_day": 0.15,
        "num_labourers": 2,
        "labour_rate_per_day": 300.0,
        "other_costs": 50.0,
    }

    response = await client.post("/v1/analytics/profit-loss", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Chick purchase: 30 * 100 = 3000
    # Labour: 2 * 300 * 30 = 18000
    # Feed: 0.15 * ((100 + 95)/2) * 30 = 438.75
    # Other: 50 * (30/30.0) = 50
    # Total costs: 3000 + 18000 + 438.75 + 50 = 21488.75
    # Revenue: 95 * 120 = 11400
    # Net profit: 11400 - 21488.75 = -10088.75

    assert data["input_chickens"] == 100
    assert data["projected_headcount"] == 95  # 5% monthly mortality
    assert data["estimated_mortality_rate"] == 0.05
    assert data["price_per_chicken"] == 120.0
    assert data["duration_days"] == 30
    assert data["revenue"] == 11400.0
    assert data["costs"]["chick_purchase_cost"] == 3000.0
    assert data["costs"]["feed_cost"] == 438.75
    assert data["costs"]["labour_cost"] == 18000.0
    assert data["costs"]["other_costs"] == 50.0
    assert data["costs"]["total_costs"] == 21488.75
    assert data["net_profit"] == -10088.75
    assert data["profit_margin_percent"] == -88.5
    assert data["is_profitable"] is False
    assert data["avg_health_score"] is None
    assert data["current_headcount"] is None


@pytest.mark.asyncio
async def test_profit_loss_critical_health(client, auth_headers, monkeypatch):
    # Mock health context to return poor health score
    async def mock_health_summary(start, end, farm_id=None):
        return {"avg_health_score": 0.25}
    async def mock_detected_chickens(start, end, farm_id=None):
        return [1, 2, 3] # list of length 3 -> headcount = 3

    monkeypatch.setattr("app.health.queries.query_health_summary", mock_health_summary)
    monkeypatch.setattr("app.detection.queries.query_detected_chickens", mock_detected_chickens)

    payload = {
        "purchase_price_per_chick": 30.0,
        "num_chickens": 100,
        "price_per_chicken": 120.0,
        "duration_days": 30,
        "feed_cost_per_chicken_per_day": 0.15,
        "num_labourers": 2,
        "labour_rate_per_day": 300.0,
        "other_costs": 50.0,
    }

    response = await client.post("/v1/analytics/profit-loss", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # For health < 0.3, monthly mortality = 20%
    # Projected headcount = round(100 * (1 - 0.2)) = 80
    # Average headcount = (100 + 80) / 2 = 90
    # Feed cost: 0.15 * 90 * 30 = 405.0
    # Total costs: 3000 + 18000 + 405.0 + 50 = 21455.0
    # Revenue: 80 * 120 = 9600
    # Net profit: 9600 - 21455 = -11855

    assert data["projected_headcount"] == 80
    assert data["estimated_mortality_rate"] == 0.20
    assert data["costs"]["feed_cost"] == 405.0
    assert data["costs"]["total_costs"] == 21455.0
    assert data["net_profit"] == -11855.0
    assert data["avg_health_score"] == 0.25
    assert data["current_headcount"] == 3
