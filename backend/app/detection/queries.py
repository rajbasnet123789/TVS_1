import logging
import re
from datetime import UTC, datetime, timedelta

from influxdb_client import InfluxDBClient

from app.config import settings

logger = logging.getLogger(__name__)

_TIME_PATTERN = re.compile(r"^-?\d+[mhdw]$")
_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_WINDOW_PATTERN = re.compile(r"^\d+[mhdw]$")
_UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


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
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: -5m)
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
            |> count()
    '''
    total = 0
    for table in client.query_api().query(query):
        for record in table.records:
            total += record.get_value() or 0

    # track_id is a TAG — distinct() only works on fields.
    # Count unique tag values by grouping per track_id, then counting the groups.
    unique_query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: -5m)
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}" and r["track_id"] != "-1" and r["_field"] == "confidence")
            |> group(columns: ["track_id"])
            |> count()
            |> group()
            |> count()
    '''
    unique_count = 0
    for table in client.query_api().query(unique_query):
        for record in table.records:
            unique_count = record.get_value() or 0

    return {"total": total, "unique": unique_count, "per_minute": round(total / 5, 1)}


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
    # track_id is a TAG — must group by it to count uniques, then re-count groups.
    cam_filter = f'r["camera_id"] == "{camera_id}" and ' if camera_id else ''
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => {cam_filter}r["track_id"] != "-1" and r["_field"] == "confidence")
            |> group(columns: ["track_id"])
            |> count()
            |> group()
            |> count()
    '''
    result = []
    for table in client.query_api().query(query):
        for record in table.records:
            result.append({
                "time": end.replace("now()", datetime.now(UTC).isoformat().replace("+00:00", "Z")) if end == "now()" else end,
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
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
            |> group()
            |> aggregateWindow(every: {window}, fn: count, createEmpty: false)
            |> yield(name: "count")
    '''
    seen_times = set()
    detection_points = []
    for table in client.query_api().query(query):
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

    # Query 1: per-hour counts → total, active minutes, detections/hour
    window_counts_query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
            |> group()
            |> aggregateWindow(every: 1h, fn: count, createEmpty: false)
    '''
    window_counts = []
    for table in client.query_api().query(window_counts_query):
        for record in table.records:
            window_counts.append(record.get_value() or 0)

    total = sum(window_counts)
    hours = max(1, len(window_counts))
    per_hour = round(total / hours, 1)
    active_minutes = len(window_counts) * 60

    # Query 2: unique track_ids seen (group per track_id → count groups)
    unique_query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}" and r["track_id"] != "-1" and r["_field"] == "confidence")
            |> group(columns: ["track_id"])
            |> count()
            |> group()
            |> count()
    '''
    unique_count = 0
    for table in client.query_api().query(unique_query):
        for record in table.records:
            unique_count = record.get_value() or 0

    # Query 3: mean confidence
    avg_conf_query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => r["camera_id"] == "{camera_id}" and r["_field"] == "confidence")
            |> group()
            |> mean()
    '''
    avg_conf = 0.0
    for table in client.query_api().query(avg_conf_query):
        for record in table.records:
            avg_conf = record.get_value() or 0.0

    return {
        "total_detections": total,
        "unique_chickens": unique_count,
        "peak_head_count": unique_count,
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
    if farm_id:
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["farm_id"] == "{farm_id}")
                |> group()
                |> aggregateWindow(every: {window}, fn: count, createEmpty: false)
                |> yield(name: "count")
        '''
    else:
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> group()
                |> aggregateWindow(every: {window}, fn: count, createEmpty: false)
                |> yield(name: "count")
        '''
    seen_times = set()
    detection_points = []
    for table in client.query_api().query(query):
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
    """Return per-track summary stats for all tracked chickens in the window.

    Uses a single aggregated Flux query (group by track_id + reduce) instead of
    the previous N+1 pattern (4 separate queries per track_id).
    """
    validate_time_param(start, "start")
    validate_time_param(end, "end")
    client = _get_influx()
    farm_filter = f' and r["farm_id"] == "{farm_id}"' if farm_id else ""
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => r["track_id"] != "-1" and r["track_id"] != "None"{farm_filter})
            |> filter(fn: (r) => r["_field"] == "confidence")
            |> group(columns: ["track_id"])
            |> reduce(
                identity: {{detections: 0, conf_sum: 0.0, first: 0, last: 0, cameras: ""}},
                fn: (r, accumulator) => ({{
                    detections: accumulator.detections + 1,
                    conf_sum: accumulator.conf_sum + r._value,
                    first: if accumulator.detections == 0 then int(v: r._time) else accumulator.first,
                    last: int(v: r._time),
                    cameras: accumulator.cameras + (if accumulator.cameras == "" then string(v: r.camera_id) else "," + string(v: r.camera_id)),
                }})
            )
    '''
    now = datetime.now(UTC)
    five_min_ago = now - timedelta(minutes=5)

    results: list[dict] = []
    for table in client.query_api().query(query):
        for record in table.records:
            tid = record.values.get("track_id")
            detections = int(record.values.get("detections") or 0)
            conf_sum = float(record.values.get("conf_sum") or 0.0)
            first_ns = int(record.values.get("first") or 0)
            last_ns = int(record.values.get("last") or 0)
            cameras_raw = record.values.get("cameras") or ""
            cameras = [c for c in cameras_raw.split(",") if c]
            cameras = list(dict.fromkeys(cameras)) or ["unknown"]

            try:
                tid_int = int(tid)
            except (ValueError, TypeError):
                continue

            first_seen = datetime.fromtimestamp(first_ns / 1e9, tz=UTC) if first_ns else now
            last_seen = datetime.fromtimestamp(last_ns / 1e9, tz=UTC) if last_ns else now

            results.append({
                "track_id": tid_int,
                "detections": detections,
                "avg_confidence": round(conf_sum / detections, 3) if detections else 0.0,
                "last_seen": last_seen,
                "first_seen": first_seen,
                "cameras": cameras,
                "status": "active" if last_seen > five_min_ago else "inactive",
            })

    results.sort(key=lambda r: r["track_id"])
    return results


def query_per_camera_live_counts(farm_id: str | None = None, window_minutes: int = 15) -> list[dict]:
    """Return the count of unique track_ids seen per camera in the last `window_minutes` minutes.

    track_id is stored as a TAG. To count unique values we group by (camera_id, track_id),
    collapse each group to a single row (count), then re-group by camera_id only and count
    the remaining rows — giving unique track_ids per camera.

    Returns a list of {camera_id, count} sorted by camera_id.
    """
    client = _get_influx()
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: -{window_minutes}m)
            |> filter(fn: (r) =>
                r["_field"] == "confidence"
                and r["track_id"] != "-1"
                and r["track_id"] != "None"
            )
            |> group(columns: ["camera_id", "track_id"])
            |> count()
            |> group(columns: ["camera_id"])
            |> count()
    '''
    results: list[dict] = []
    for table in client.query_api().query(query):
        for record in table.records:
            cam_id = record.values.get("camera_id")
            count = record.get_value() or 0
            if cam_id:
                results.append({"camera_id": cam_id, "count": count})

    results.sort(key=lambda r: r["camera_id"])
    return results
