import logging
from datetime import datetime, timezone

from app.config import settings
from app.detection.queries import validate_camera_id, validate_time_param, validate_window


def validate_farm_id(farm_id: str) -> str:
    import uuid
    uuid.UUID(farm_id)
    return farm_id

logger = logging.getLogger(__name__)

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


def _query_health_scores_sync(
    camera_id: str | None,
    start: str,
    end: str,
    limit: int,
    farm_id: str | None = None,
) -> list[dict]:
    client = _get_client()
    try:
        filter_parts = []
        if camera_id:
            filter_parts.append(f'r["camera_id"] == "{camera_id}"')
        if farm_id:
            filter_parts.append(f'r["farm_id"] == "{farm_id}"')
        filter_clause = ' and '.join(filter_parts) + ' and ' if filter_parts else ''

        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> sort(columns: ["_time"], desc: true)
                |> limit(n: {limit})
        '''
        results = []
        for table in client.query_api().query(query):
            for record in table.records:
                results.append({
                    "time": record.get_time(),
                    "camera_id": record.values.get("camera_id"),
                    "track_id": record.values.get("track_id"),
                    "health_class": record.values.get("health_class"),
                    "health_score": record.get_value(),
                })
        return results
    finally:
        pass


async def query_health_scores(
    camera_id: str | None = None,
    start: str = "-1h",
    end: str = "now()",
    limit: int = 100,
    farm_id: str | None = None,
) -> list[dict]:
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    if camera_id:
        validate_camera_id(camera_id)
    if farm_id:
        validate_farm_id(farm_id)

    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _query_health_scores_sync(camera_id, start, end, limit, farm_id)
    )


def _query_health_summary_sync(
    camera_id: str | None,
    start: str,
    end: str,
    farm_id: str | None = None,
) -> dict:
    client = _get_client()
    try:
        filter_parts = []
        if camera_id:
            filter_parts.append(f'r["camera_id"] == "{camera_id}"')
        if farm_id:
            filter_parts.append(f'r["farm_id"] == "{farm_id}"')
        filter_clause = ' and '.join(filter_parts) + ' and ' if filter_parts else ''

        stats_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group()
                |> mean()
        '''
        avg_score = 0.0
        for table in client.query_api().query(stats_query):
            for record in table.records:
                avg_score = record.get_value() or 0.0

        min_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group()
                |> min()
        '''
        min_score = None
        for table in client.query_api().query(min_query):
            for record in table.records:
                val = record.get_value()
                if val is not None:
                    min_score = min(min_score, val) if min_score is not None else val

        max_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group()
                |> max()
        '''
        max_score = None
        for table in client.query_api().query(max_query):
            for record in table.records:
                val = record.get_value()
                if val is not None:
                    max_score = max(max_score, val) if max_score is not None else val

        count_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> filter(fn: (r) => r["_field"] == "health_score")
                |> group()
                |> count()
        '''
        total = 0
        for table in client.query_api().query(count_query):
            for record in table.records:
                total += record.get_value() or 0

        class_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => {filter_clause}r["_measurement"] == "health")
                |> group(columns: ["health_class"])
                |> count()
        '''
        class_dist = {}
        for table in client.query_api().query(class_query):
            for record in table.records:
                cls = record.values.get("health_class", "unknown")
                class_dist[cls] = class_dist.get(cls, 0) + (record.get_value() or 0)

        return {
            "camera_id": camera_id,
            "total_records": total,
            "avg_health_score": round(avg_score, 1),
            "min_health_score": round(min_score, 1) if min_score is not None else None,
            "max_health_score": round(max_score, 1) if max_score is not None else None,
            "class_distribution": class_dist,
        }
    finally:
        pass


async def query_health_summary(
    camera_id: str | None = None,
    start: str = "-1h",
    end: str = "now()",
    farm_id: str | None = None,
) -> dict:
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    if camera_id:
        validate_camera_id(camera_id)
    if farm_id:
        validate_farm_id(farm_id)

    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _query_health_summary_sync(camera_id, start, end, farm_id)
    )
