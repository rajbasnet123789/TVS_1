from pydantic import BaseModel, Field
from typing import Optional


class ProfitLossInput(BaseModel):
    purchase_price_per_chick: float = Field(..., gt=0, description="Purchase price per chick")
    num_chickens: int = Field(..., gt=0, description="Number of chickens")
    price_per_chicken: float = Field(..., gt=0, description="Selling price per chicken")
    duration_days: int = Field(30, ge=1, le=90, description="Projection duration in days")
    feed_cost_per_chicken_per_day: float = Field(0.0, ge=0, description="Daily feed cost per chicken")
    num_labourers: int = Field(0, ge=0, description="Number of labourers")
    labour_rate_per_day: float = Field(0.0, ge=0, description="Daily rate per labourer")
    other_costs: float = Field(0.0, ge=0, description="Other fixed costs (electricity, medicine, etc.)")


class CostBreakdown(BaseModel):
    chick_purchase_cost: float
    feed_cost: float
    labour_cost: float
    other_costs: float
    total_costs: float


class ProfitLossResult(BaseModel):
    input_chickens: int
    projected_headcount: int
    estimated_mortality_rate: float
    price_per_chicken: float
    duration_days: int

    revenue: float
    costs: CostBreakdown
    net_profit: float
    profit_margin_percent: float

    is_profitable: bool
    avg_health_score: Optional[float] = None
    current_headcount: Optional[int] = None
