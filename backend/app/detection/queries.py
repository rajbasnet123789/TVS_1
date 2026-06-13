import logging
from datetime import datetime
from typing import Optional

from influxdb_client import InfluxDBClient

from app.config import settings

logger = logging.getLogger(__name__)


def _query_headcount_snapshot(client: InfluxDBClient, camera_id: str | None, start: str, end: str) -> list[dict]:
    filter_clause = f'r["camera_id"] == "{camera_id}"' if camera_id else 'true'
    query = f'''
        from(bucket: "{settings.influx_bucket}")
            |> range(start: {start}, stop: {end})
            |> filter(fn: (r) => {filter_clause})
            |> filter(fn: (r) => r["track_id"] != "-1")
            |> distinct(column: "track_id")
            |> group()
            |> count()
    '''
    result = []
    for table in client.query_api().query(query):
        for record in table.records:
            result.append({
                "time": end.replace("now()", datetime.utcnow().isoformat() + "Z") if end == "now()" else end,
                "value": record.get_value() or 0,
            })
    return result


def _get_client() -> InfluxDBClient:
    return InfluxDBClient(
        url=settings.influx_url,
        token=settings.influx_token,
        org=settings.influx_org,
    )


def query_detection_history(
    camera_id: str,
    start: str,
    end: str,
    window: str = "5m",
) -> tuple[list[dict], list[dict]]:
    client = _get_client()
    try:
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
    finally:
        client.close()


def query_detection_summary(
    camera_id: str,
    start: str,
    end: str,
) -> dict:
    client = _get_client()
    try:
        total_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> group()
                |> count()
        '''
        total = 0
        for table in client.query_api().query(total_query):
            for record in table.records:
                total += record.get_value() or 0

        unique_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> group()
                |> distinct(column: "track_id")
        '''
        unique_ids = set()
        for table in client.query_api().query(unique_query):
            for record in table.records:
                val = record.get_value()
                if val and val != "-1":
                    unique_ids.add(val)

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

        peak_hc_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> filter(fn: (r) => r["track_id"] != "-1")
                |> group()
                |> distinct(column: "track_id")
                |> group()
                |> count()
        '''
        peak_hc = 0
        for table in client.query_api().query(peak_hc_query):
            for record in table.records:
                peak_hc = max(peak_hc, record.get_value() or 0)

        avg_conf_query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> filter(fn: (r) => r["_field"] == "confidence")
                |> group()
                |> mean()
        '''
        avg_conf = 0.0
        for table in client.query_api().query(avg_conf_query):
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
    finally:
        client.close()


def query_global_history(
    start: str,
    end: str,
    window: str = "5m",
) -> tuple[list[dict], list[dict]]:
    client = _get_client()
    try:
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
    finally:
        client.close()


def query_detected_chickens(
    start: str = "-1h",
    end: str = "now()",
) -> list[dict]:
    client = _get_client()
    try:
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["track_id"] != "-1" and r["track_id"] != "None")
                |> group(columns: ["track_id"])
                |> count()
        '''
        track_ids = set()
        for table in client.query_api().query(query):
            for record in table.records:
                tid = record.values.get("track_id")
                if tid and tid not in ("-1", "None"):
                    try:
                        track_ids.add(int(tid))
                    except (ValueError, TypeError):
                        continue

        results = []
        for tid in sorted(track_ids):
            stats_query = f'''
                from(bucket: "{settings.influx_bucket}")
                    |> range(start: -7d)
                    |> filter(fn: (r) => r["track_id"] == "{tid}")
                    |> group()
                    |> count()
            '''
            total = 0
            for table in client.query_api().query(stats_query):
                for record in table.records:
                    total += record.get_value() or 0

            avg_conf_query = f'''
                from(bucket: "{settings.influx_bucket}")
                    |> range(start: -7d)
                    |> filter(fn: (r) => r["track_id"] == "{tid}")
                    |> filter(fn: (r) => r["_field"] == "confidence")
                    |> group()
                    |> mean()
            '''
            avg_conf = 0.0
            for table in client.query_api().query(avg_conf_query):
                for record in table.records:
                    avg_conf = record.get_value() or 0.0

            last_query = f'''
                from(bucket: "{settings.influx_bucket}")
                    |> range(start: -7d)
                    |> filter(fn: (r) => r["track_id"] == "{tid}")
                    |> group()
                    |> last()
            '''
            last_seen = None
            first_seen = None
            last_cameras = set()
            for table in client.query_api().query(last_query):
                for record in table.records:
                    last_seen = record.get_time()
                    cam = record.values.get("camera_id")
                    if cam:
                        last_cameras.add(cam)

            first_query = f'''
                from(bucket: "{settings.influx_bucket}")
                    |> range(start: -7d)
                    |> filter(fn: (r) => r["track_id"] == "{tid}")
                    |> group()
                    |> first()
            '''
            for table in client.query_api().query(first_query):
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
    finally:
        client.close()


def query_raw_detections(
    camera_id: str,
    start: str,
    end: str,
    limit: int = 100,
) -> list[dict]:
    client = _get_client()
    try:
        query = f'''
            from(bucket: "{settings.influx_bucket}")
                |> range(start: {start}, stop: {end})
                |> filter(fn: (r) => r["camera_id"] == "{camera_id}")
                |> sort(columns: ["_time"], desc: true)
                |> limit(n: {limit})
        '''
        results = []
        for table in client.query_api().query(query):
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
    finally:
        client.close()
