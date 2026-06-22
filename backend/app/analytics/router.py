import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth.deps import get_farm_id, require_permission
from app.auth.models import User
from app.analytics.schemas import ProfitLossInput, ProfitLossResult, CostBreakdown
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _fetch_health_context(farm_id: str | None = None) -> tuple[float | None, int | None]:
    try:
        from app.health.queries import query_health_summary
        from app.detection.queries import query_detected_chickens

        health = await query_health_summary(start="-7d", end="now()", farm_id=farm_id)
        active = await query_detected_chickens(start="-5m", end="now()", farm_id=farm_id)
        avg_health = health.get("avg_health_score") if health else None
        current_hc = len(active) if active else None
        return avg_health, current_hc
    except Exception:
        logger.warning("Failed to fetch health context for P&L, using defaults")
        return None, None


@router.post("/profit-loss", response_model=ProfitLossResult)
@limiter.limit("20/minute")
async def calculate_profit_loss(
    request: Request,
    body: ProfitLossInput,
    farm_id: str | None = Depends(get_farm_id),
    user: User = Depends(require_permission("dashboard:read")),
):
    avg_health, current_hc = await _fetch_health_context(farm_id=farm_id)

    # Estimate mortality rate from health score (0-1 scale, lower = sicker)
    # Default mortality: 5% per month for healthy flock, up to 20% for unhealthy
    base_monthly_mortality = 0.05
    if avg_health is not None:
        if avg_health < 0.3:
            base_monthly_mortality = 0.20
        elif avg_health < 0.5:
            base_monthly_mortality = 0.12
        elif avg_health < 0.7:
            base_monthly_mortality = 0.08

    duration_months = body.duration_days / 30.0
    mortality_rate = 1 - (1 - base_monthly_mortality) ** duration_months
    projected_headcount = max(1, round(body.num_chickens * (1 - mortality_rate)))

    chick_purchase_cost = body.purchase_price_per_chick * body.num_chickens
    feed_days = body.duration_days
    average_headcount = (body.num_chickens + projected_headcount) / 2.0
    total_feed_cost = body.feed_cost_per_chicken_per_day * average_headcount * feed_days
    total_labour_cost = body.num_labourers * body.labour_rate_per_day * body.duration_days
    total_other_costs = body.other_costs * duration_months

    revenue = projected_headcount * body.price_per_chicken
    total_costs = chick_purchase_cost + total_feed_cost + total_labour_cost + total_other_costs
    net_profit = revenue - total_costs
    profit_margin = (net_profit / revenue * 100) if revenue > 0 else 0.0

    return ProfitLossResult(
        input_chickens=body.num_chickens,
        projected_headcount=projected_headcount,
        estimated_mortality_rate=round(mortality_rate, 4),
        price_per_chicken=body.price_per_chicken,
        duration_days=body.duration_days,
        revenue=round(revenue, 2),
        costs=CostBreakdown(
            chick_purchase_cost=round(chick_purchase_cost, 2),
            feed_cost=round(total_feed_cost, 2),
            labour_cost=round(total_labour_cost, 2),
            other_costs=round(total_other_costs, 2),
            total_costs=round(total_costs, 2),
        ),
        net_profit=round(net_profit, 2),
        profit_margin_percent=round(profit_margin, 1),
        is_profitable=net_profit >= 0,
        avg_health_score=avg_health,
        current_headcount=current_hc,
    )
