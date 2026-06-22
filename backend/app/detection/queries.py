import logging
import re
import uuid
from datetime import datetime

from influxdb_client import InfluxDBClient

from app.config import settings

logger = logging.getLogger(__name__)

_TIME_PATTERN = re.compile(r"^-?\d+[mhdw]$")
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_WINDOW_PATTERN = re.compile(r"^\d+[mhdw]$")
_UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


import threading

def validate_camera_id(camera_id: str) -> str:
    if not _UUID_PATTERN.match(camera_id):
        raise ValueError(f"Invalid camera_id format: {camera_id}")
    return camera_id

_influx_client = None
_influx_lock = threading.Lock()


def _get_influx() -> InfluxDBClient:
    global _influx_client
    if _influx_client is None:
        with _influx_lock:
            if _influx_client is None:
                _influx_client = InfluxDBClient(
                    url=settings.influx_url,
                    token=settings.influx_token,
                    org=settings.influx_org,
                )
    return _influx_client


def query_detection_stats(camera_id: str) -> dict:
    validate_camera_id(camera_id)
    client = _get_influx()
    params = {"bucket": settings.influx_bucket, "camera_id": camera_id}
    query = '''
        from(bucket: params.bucket)
            |> range(start: -5m)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> count()
    '''
    total = 0
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            total += record.get_value() or 0

    unique_query = '''
        from(bucket: params.bucket)
            |> range(start: -5m)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> distinct(column: "track_id")
    '''
    unique_ids = set()
    for table in client.query_api().query(unique_query, params=params):
        for record in table.records:
            unique_ids.add(record.get_value())

    return {"total": total, "unique": len(unique_ids), "per_minute": round(total / 5, 1)}


def validate_time_param(value: str, name: str) -> str:
    if value == "now()":
        return value
    if _TIME_PATTERN.match(value):
        return value
    if _DATETIME_PATTERN.match(value):
        return value
    raise ValueError(f"Invalid {name}: {value}")


def validate_window(value: str) -> str:
    if not _WINDOW_PATTERN.match(value):
        raise ValueError(f"Invalid window: {value}")
    return value


def _query_headcount_snapshot(client: InfluxDBClient, camera_id: str | None, start: str, end: str) -> list[dict]:
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end}
    filter_clause = 'r["track_id"] != "-1"'
    if camera_id:
        params["camera_id"] = camera_id
        filter_clause = 'r["camera_id"] == params.camera_id and r["track_id"] != "-1"'
    query = f'''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => {filter_clause})
            |> distinct(column: "track_id")
            |> group()
            |> count()
    '''
    result = []
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            result.append({
                "time": end.replace("now()", datetime.utcnow().isoformat() + "Z") if end == "now()" else end,
                "value": record.get_value() or 0,
            })
    return result


def query_detection_history(
    camera_id: str,
    start: str,
    end: str,
    window: str = "5m",
) -> tuple[list[dict], list[dict]]:
    validate_camera_id(camera_id)
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    validate_window(window)
    client = _get_influx()
    query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> group()
            |> aggregateWindow(every: params.window, fn: count, createEmpty: false)
            |> yield(name: "count")
    '''
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end, "camera_id": camera_id, "window": window}
    seen_times = set()
    detection_points = []
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            t = record.get_time()
            if t not in seen_times:
                seen_times.add(t)
                detection_points.append({
                    "time": t,
                    "value": record.get_value() or 0,
                })

    hc_points = _query_headcount_snapshot(client, camera_id, start, end)

    return detection_points, hc_points


def query_detection_summary(
    camera_id: str,
    start: str,
    end: str,
) -> dict:
    validate_camera_id(camera_id)
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    client = _get_influx()
    total_query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> group()
            |> count()
    '''
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end, "camera_id": camera_id}
    total = 0
    for table in client.query_api().query(total_query, params=params):
        for record in table.records:
            total += record.get_value() or 0

    unique_query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> group()
            |> distinct(column: "track_id")
    '''
    unique_ids = set()
    for table in client.query_api().query(unique_query, params=params):
        for record in table.records:
            val = record.get_value()
            if val and val != "-1":
                unique_ids.add(val)

    window_counts_query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> group()
            |> aggregateWindow(every: 1h, fn: count, createEmpty: false)
    '''
    window_counts = []
    for table in client.query_api().query(window_counts_query, params=params):
        for record in table.records:
            window_counts.append(record.get_value() or 0)

    peak_hc_query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id and r["track_id"] != "-1")
            |> group()
            |> distinct(column: "track_id")
            |> group()
            |> count()
    '''
    peak_hc = 0
    for table in client.query_api().query(peak_hc_query, params=params):
        for record in table.records:
            peak_hc = max(peak_hc, record.get_value() or 0)

    avg_conf_query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id and r["_field"] == "confidence")
            |> group()
            |> mean()
    '''
    avg_conf = 0.0
    for table in client.query_api().query(avg_conf_query, params=params):
        for record in table.records:
            avg_conf = record.get_value() or 0.0

    hours = max(1, len(window_counts))
    per_hour = round(total / hours, 1)
    active_minutes = len(window_counts) * 60

    return {
        "total_detections": total,
        "unique_chickens": len(unique_ids),
        "peak_head_count": peak_hc,
        "avg_confidence": round(avg_conf, 3),
        "active_minutes": active_minutes,
        "detections_per_hour": per_hour,
    }


def query_global_history(
    start: str,
    end: str,
    window: str = "5m",
    farm_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    validate_window(window)
    client = _get_influx()
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end, "window": window}
    if farm_id:
        params["farm_id"] = farm_id
        query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["farm_id"] == params.farm_id)
                |> group()
                |> aggregateWindow(every: params.window, fn: count, createEmpty: false)
                |> yield(name: "count")
        '''
    else:
        query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> group()
                |> aggregateWindow(every: params.window, fn: count, createEmpty: false)
                |> yield(name: "count")
        '''
    seen_times = set()
    detection_points = []
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            t = record.get_time()
            if t not in seen_times:
                seen_times.add(t)
                detection_points.append({
                    "time": t,
                    "value": record.get_value() or 0,
                })

    hc_points = _query_headcount_snapshot(client, None, start, end)

    return detection_points, hc_points


def query_detected_chickens(
    start: str = "-1h",
    end: str = "now()",
    farm_id: str | None = None,
) -> list[dict]:
    client = _get_influx()
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end}
    if farm_id:
        params["farm_id"] = farm_id
        query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] != "-1" and r["track_id"] != "None" and r["farm_id"] == params.farm_id)
                |> group(columns: ["track_id"])
                |> count()
        '''
    else:
        query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] != "-1" and r["track_id"] != "None")
                |> group(columns: ["track_id"])
                |> count()
        '''
    track_ids = set()
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            tid = record.values.get("track_id")
            if tid and tid not in ("-1", "None"):
                try:
                    track_ids.add(int(tid))
                except (ValueError, TypeError):
                    continue

    results = []
    for tid in sorted(track_ids):
        stats_query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] == string(v: params.tid))
                |> group()
                |> count()
        '''
        stats_params = {"bucket": settings.influx_bucket, "tid": tid, "start": start, "stop": end}
        total = 0
        for table in client.query_api().query(stats_query, params=stats_params):
            for record in table.records:
                total += record.get_value() or 0

        avg_conf_query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] == string(v: params.tid) and r["_field"] == "confidence")
                |> group()
                |> mean()
        '''
        avg_conf = 0.0
        for table in client.query_api().query(avg_conf_query, params=stats_params):
            for record in table.records:
                avg_conf = record.get_value() or 0.0

        last_query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] == string(v: params.tid))
                |> group()
                |> last()
        '''
        last_seen = None
        first_seen = None
        last_cameras = set()
        for table in client.query_api().query(last_query, params=stats_params):
            for record in table.records:
                last_seen = record.get_time()
                cam = record.values.get("camera_id")
                if cam:
                    last_cameras.add(cam)

        first_query = '''
            from(bucket: params.bucket)
                |> range(start: params.start, stop: params.stop)
                |> filter(fn: (r) => r["track_id"] == string(v: params.tid))
                |> group()
                |> first()
        '''
        for table in client.query_api().query(first_query, params=stats_params):
            for record in table.records:
                first_seen = record.get_time()
                if first_seen:
                    break

        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        five_min_ago = now - dt.timedelta(minutes=5)
        is_active = last_seen and last_seen > five_min_ago

        results.append({
            "track_id": tid,
            "detections": total,
            "avg_confidence": round(avg_conf, 3),
            "last_seen": last_seen or now,
            "first_seen": first_seen or now,
            "cameras": list(last_cameras) if last_cameras else ["unknown"],
            "status": "active" if is_active else "inactive",
        })

    return results


def query_raw_detections(
    camera_id: str,
    start: str,
    end: str,
    limit: int = 100,
) -> list[dict]:
    client = _get_influx()
    query = '''
        from(bucket: params.bucket)
            |> range(start: params.start, stop: params.stop)
            |> filter(fn: (r) => r["camera_id"] == params.camera_id)
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: params.limit)
    '''
    params = {"bucket": settings.influx_bucket, "start": start, "stop": end, "camera_id": camera_id, "limit": limit}
    results = []
    for table in client.query_api().query(query, params=params):
        for record in table.records:
            results.append({
                "time": record.get_time(),
                "track_id": record.values.get("track_id"),
                "class_name": record.values.get("class_name"),
                "confidence": record.get_value_by_key("confidence"),
                "x": record.get_value_by_key("x"),
                "y": record.get_value_by_key("y"),
                "w": record.get_value_by_key("w"),
                "h": record.get_value_by_key("h"),
            })
    return results
