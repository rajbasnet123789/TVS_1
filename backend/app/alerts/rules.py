import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.models import AlertRule
from app.alerts.schemas import AlertCreate
from app.alerts.service import create_alert
from app.config import settings
from app.database import async_session
from app.websocket.manager import manager

logger = logging.getLogger(__name__)


async def evaluate_alert_rules():
    try:
        async with async_session() as db:
            result = await db.execute(select(AlertRule).where(AlertRule.enabled))
            rules = list(result.scalars().all())

        for rule in rules:
            try:
                if rule.metric == "inactivity":
                    await _check_inactivity(rule)
                elif rule.metric == "health_critical":
                    await _check_health_critical(rule)
                elif rule.metric == "health_drop":
                    await _check_health_drop(rule)
                elif rule.metric == "missing_chicken":
                    await _check_missing_chicken(rule)
                elif rule.metric == "camera_offline":
                    await _check_camera_offline(rule)
            except Exception as e:
                logger.warning(f"Alert rule '{rule.name}' evaluation failed: {e}")

    except Exception as e:
        logger.warning(f"Alert rule evaluation cycle failed: {e}")


_influx_client = None


def _get_client():
    global _influx_client
    if _influx_client is None:
        from influxdb_client import InfluxDBClient
        _influx_client = InfluxDBClient(
            url=settings.influx_url,
            token=settings.influx_token,
            org=settings.influx_org,
        )
    return _influx_client


async def _check_inactivity(rule: AlertRule):
    client = _get_client()
    try:
        duration_minutes = int(rule.duration_minutes)
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: -{duration_minutes}m, stop: now())
                |> filter(fn: (r) => r["farm_id"] == "{str(rule.farm_id)}")
                |> filter(fn: (r) => r["track_id"] != "-1" and r["track_id"] != "None")
                |> group(columns: ["track_id"])
                |> last()
        '''
        params = {
            "bucket": settings.influx_bucket,
        }
        loop = asyncio.get_running_loop()
        tables = await loop.run_in_executor(None, lambda: client.query_api().query(query, params=params))
        active_tracks = set()
        for table in tables:
            for record in table.records:
                tid = record.values.get("track_id")
                if tid and tid not in ("-1", "None"):
                    active_tracks.add(tid)

        if len(active_tracks) == 0:
            async with async_session() as db:
                from app.cameras.models import Camera
                from app.alerts.models import Alert
                cam_result = await db.execute(select(Camera).where(Camera.enabled == True, Camera.farm_id == rule.farm_id))
                cameras = cam_result.scalars().all()
                for cam in cameras:
                    existing_result = await db.execute(
                        select(Alert).where(
                            Alert.camera_id == str(cam.id),
                            Alert.type == "inactivity",
                            Alert.acknowledged_at.is_(None),
                            Alert.farm_id == rule.farm_id
                        )
                    )
                    if existing_result.scalar_one_or_none():
                        continue

                    await create_alert(db, AlertCreate(
                        camera_id=str(cam.id),
                        type="inactivity",
                        severity=rule.severity,
                        message=f"No chickens detected on {cam.name} for {rule.duration_minutes} minutes",
                    ), farm_id=rule.farm_id)
    finally:
        pass


async def _check_health_critical(rule: AlertRule):
    client = _get_client()
    try:
        query = '''
            from(bucket: bucket)
                |> range(start: -5m)
                |> filter(fn: (r) => r["farm_id"] == farm_id)
                |> filter(fn: (r) => r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> filter(fn: (r) => r._value < threshold)
                |> group(columns: ["track_id", "camera_id"])
                |> last()
        '''
        params = {
            "bucket": settings.influx_bucket,
            "farm_id": str(rule.farm_id),
            "threshold": float(rule.threshold),
        }
        loop = asyncio.get_running_loop()
        tables = await loop.run_in_executor(None, lambda: client.query_api().query(query, params=params))
        for table in tables:
            for record in table.records:
                camera_id = record.values.get("camera_id")
                track_id = record.values.get("track_id")
                score = record.get_value()
                async with async_session() as db:
                    from app.alerts.models import Alert
                    existing_result = await db.execute(
                        select(Alert).where(
                            Alert.camera_id == camera_id,
                            Alert.type == "health_critical",
                            Alert.acknowledged_at.is_(None),
                            Alert.farm_id == rule.farm_id,
                            Alert.track_id == str(track_id)
                        )
                    )
                    if existing_result.scalar_one_or_none():
                        continue

                    await create_alert(db, AlertCreate(
                        camera_id=camera_id,
                        type="health_critical",
                        severity=rule.severity,
                        message=f"Chicken track {track_id} has critical health score: {score}/100",
                        track_id=str(track_id)
                    ), farm_id=rule.farm_id)
    finally:
        pass


async def _check_health_drop(rule: AlertRule):
    client = _get_client()
    try:
        now_mean_query = '''
            from(bucket: bucket)
                |> range(start: -5m)
                |> filter(fn: (r) => r["farm_id"] == farm_id)
                |> filter(fn: (r) => r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group(columns: ["track_id"])
                |> mean()
        '''
        params_now = {
            "bucket": settings.influx_bucket,
            "farm_id": str(rule.farm_id),
        }
        loop = asyncio.get_running_loop()
        now_tables = await loop.run_in_executor(None, lambda: client.query_api().query(now_mean_query, params=params_now))
        now_scores = {}
        for table in now_tables:
            for record in table.records:
                tid = record.values.get("track_id")
                if tid:
                    now_scores[tid] = record.get_value() or 0
 
        lookback = max(int(rule.duration_minutes), 60)
        past_mean_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: -{lookback}m, stop: -5m)
                |> filter(fn: (r) => r["farm_id"] == "{str(rule.farm_id)}")
                |> filter(fn: (r) => r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group(columns: ["track_id"])
                |> mean()
        '''
        params_past = {
            "bucket": settings.influx_bucket,
        }
        past_tables = await loop.run_in_executor(None, lambda: client.query_api().query(past_mean_query, params=params_past))
        past_scores = {}
        for table in past_tables:
            for record in table.records:
                tid = record.values.get("track_id")
                if tid:
                    past_scores[tid] = record.get_value() or 0

        for tid, now_val in now_scores.items():
            past_val = past_scores.get(tid)
            if past_val and past_val > 0:
                drop_pct = ((past_val - now_val) / past_val) * 100
                if drop_pct >= rule.threshold:
                    async with async_session() as db:
                        from app.alerts.models import Alert
                        existing_result = await db.execute(
                            select(Alert).where(
                                Alert.type == "health_drop",
                                Alert.acknowledged_at.is_(None),
                                Alert.farm_id == rule.farm_id,
                                Alert.track_id == str(tid)
                            )
                        )
                        if existing_result.scalar_one_or_none():
                            continue

                        await create_alert(db, AlertCreate(
                            type="health_drop",
                            severity=rule.severity,
                            message=f"Chicken track {tid} health dropped {drop_pct:.0f}% "
                                    f"(from {past_val:.0f} to {now_val:.0f})",
                            track_id=str(tid)
                        ), farm_id=rule.farm_id)
    finally:
        pass


async def _check_missing_chicken(rule: AlertRule):
    client = _get_client()
    try:
        duration_minutes = int(rule.duration_minutes)
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: -{duration_minutes}m, stop: now())
                |> filter(fn: (r) => r["farm_id"] == "{str(rule.farm_id)}")
                |> filter(fn: (r) => r["_measurement"] == "detections")
                |> group(columns: ["track_id"])
                |> last()
        '''
        params = {
            "bucket": settings.influx_bucket,
        }
        loop = asyncio.get_running_loop()
        tables = await loop.run_in_executor(None, lambda: client.query_api().query(query, params=params))
        now = datetime.now(timezone.utc)
        for table in tables:
            for record in table.records:
                tid = record.values.get("track_id")
                if tid and tid not in ("-1", "None"):
                    last_seen = record.get_time()
                    if last_seen:
                        minutes_ago = (now - last_seen.replace(tzinfo=timezone.utc)).total_seconds() / 60
                        if minutes_ago >= rule.duration_minutes:
                            async with async_session() as db:
                                from app.alerts.models import Alert
                                existing_result = await db.execute(
                                    select(Alert).where(
                                        Alert.type == "missing_chicken",
                                        Alert.acknowledged_at.is_(None),
                                        Alert.farm_id == rule.farm_id,
                                        Alert.track_id == str(tid)
                                    )
                                )
                                if existing_result.scalar_one_or_none():
                                    continue

                                await create_alert(db, AlertCreate(
                                    type="missing_chicken",
                                    severity=rule.severity,
                                    message=f"Chicken track {tid} not seen in {minutes_ago:.0f} minutes",
                                    track_id=str(tid)
                                ), farm_id=rule.farm_id)
    finally:
        pass


async def _check_camera_offline(rule: AlertRule):
    # Note: Camera offline status is also tracked and broadcast by the Frigate subscriber.
    # This rule-based check acts as a fallback/periodic sync to ensure unacknowledged offline
    # alerts exist in the DB for any camera that is currently offline.
    from app.cameras.models import Camera
    from app.alerts.models import Alert
    async with async_session() as db:
        result = await db.execute(
            select(Camera).where(Camera.status != "online", Camera.enabled, Camera.farm_id == rule.farm_id)
        )
        offline = list(result.scalars().all())
        for cam in offline:
            existing_result = await db.execute(
                select(Alert).where(
                    Alert.camera_id == str(cam.id),
                    Alert.type == "camera_offline",
                    Alert.acknowledged_at.is_(None),
                    Alert.farm_id == rule.farm_id
                )
            )
            if existing_result.scalar_one_or_none():
                continue

            await create_alert(db, AlertCreate(
                camera_id=str(cam.id),
                type="camera_offline",
                severity=rule.severity,
                message=f"Camera '{cam.name}' is offline",
            ), farm_id=rule.farm_id)


async def seed_default_alert_rules():
    import uuid
    async with async_session() as db:
        result = await db.execute(select(AlertRule).limit(1))
        if result.scalar_one_or_none():
            return

        default_farm_id = uuid.UUID('00000000-0000-0000-0000-000000000001')
        defaults = [
            AlertRule(name="Camera Offline", metric="camera_offline", operator=">", threshold=0, severity=1, duration_minutes=5, farm_id=default_farm_id),
            AlertRule(name="Health Critical", metric="health_critical", operator="<", threshold=30, severity=2, duration_minutes=5, farm_id=default_farm_id),
            AlertRule(name="Health Drop 30%", metric="health_drop", operator=">", threshold=30, severity=1, duration_minutes=1440, farm_id=default_farm_id),
            AlertRule(name="Missing Chicken", metric="missing_chicken", operator=">", threshold=6, severity=2, duration_minutes=360, farm_id=default_farm_id),
            AlertRule(name="Inactivity Warning", metric="inactivity", operator=">", threshold=0, severity=1, duration_minutes=30, farm_id=default_farm_id),
        ]
        for rule in defaults:
            db.add(rule)
        await db.commit()
        logger.info(f"Seeded {len(defaults)} default alert rules")


class AlertRuleEvaluator:
    def __init__(self):
        self._task: asyncio.Task | None = None

    async def start(self):
        if self._task is not None:
            return
        await seed_default_alert_rules()
        self._task = asyncio.create_task(self._run())
        logger.info("Alert rule evaluator started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Alert rule evaluator stopped")

    async def _run(self):
        while True:
            try:
                await asyncio.sleep(60)
                await evaluate_alert_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Alert evaluator error: {e}")


alert_evaluator = AlertRuleEvaluator()
