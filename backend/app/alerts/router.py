import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.alerts.models import Alert, AlertRule
from app.alerts.schemas import AlertAcknowledge, AlertCreate, AlertOut, AlertRuleOut, AlertRuleUpdate
from app.alerts.service import acknowledge_alert, create_alert, get_alerts, get_unacknowledged_count
from app.auth.deps import get_current_user, get_farm_id, require_permission
from app.auth.models import User
from app.database import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    return await get_alerts(db, limit=limit, offset=offset, farm_id=farm_id)


@router.post("", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_alert_endpoint(
    request: Request,
    data: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    return await create_alert(db, data, farm_id=farm_id)


@router.put("/{alert_id}/acknowledge", response_model=AlertOut)
@limiter.limit("20/minute")
async def acknowledge_alert_endpoint(
    alert_id: str,
    request: Request,
    data: AlertAcknowledge,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("cameras:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if farm_id and (alert.farm_id is None or str(alert.farm_id) != farm_id) and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    passed_farm_id = None if user.role.name == "super_admin" else farm_id
    alert = await acknowledge_alert(db, alert, farm_id=passed_farm_id)
    return alert


@router.get("/unacknowledged-count")
async def unacknowledged_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    farm_id: str | None = Depends(get_farm_id),
):
    count = await get_unacknowledged_count(db, farm_id=farm_id)
    return {"count": count}


@router.get("/rules", response_model=list[AlertRuleOut])
async def list_alert_rules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("dashboard:read")),
    farm_id: str | None = Depends(get_farm_id),
):
    query = select(AlertRule).order_by(AlertRule.name)
    if farm_id:
        query = query.where(AlertRule.farm_id == farm_id)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.put("/rules/{rule_id}", response_model=AlertRuleOut)
@limiter.limit("20/minute")
async def update_alert_rule(
    rule_id: str,
    request: Request,
    data: AlertRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("settings:write")),
    farm_id: str | None = Depends(get_farm_id),
):
    result = await db.execute(select(AlertRule).where(AlertRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    if farm_id and (rule.farm_id is None or str(rule.farm_id) != farm_id) and user.role.name != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)
    await db.commit()
    await db.refresh(rule)
    return rule
