import logging
import threading
import time
from datetime import datetime, timezone

import httpx
from influxdb_client import InfluxDBClient

from cv_engine.config import settings

logger = logging.getLogger(__name__)


class AlertEvaluator(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="alert-evaluator")
        self._stop_event = threading.Event()
        self._interval = 30
        self._influx: InfluxDBClient | None = None

    def start(self):
        self._influx = InfluxDBClient(
            url=settings.INFLUX_URL,
            token=settings.INFLUX_TOKEN,
            org=settings.INFLUX_ORG,
        )
        super().start()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("Alert evaluator started")
        while not self._stop_event.is_set():
            try:
                self._evaluate_once()
            except Exception as e:
                logger.error("Alert evaluation failed: %s", e)
            self._stop_event.wait(timeout=self._interval)
        if self._influx:
            self._influx.close()
        logger.info("Alert evaluator stopped")

    def _evaluate_once(self) -> None:
        rules = self._fetch_rules()
        if not rules:
            return
        for rule in rules:
            try:
                self._check_rule(rule)
            except Exception as e:
                logger.error("Failed to check rule %s: %s", rule.get("id"), e)

    def _fetch_rules(self) -> list[dict]:
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{settings.BUSINESS_BACKEND_URL}/v1/internal/alert-rules"
                )
                resp.raise_for_status()
                return resp.json().get("rules", [])
        except Exception as e:
            logger.warning("Could not fetch alert rules: %s", e)
            return []

    def _check_rule(self, rule: dict) -> None:
        rule_id = rule.get("id")
        metric = rule.get("metric", "")
        threshold = rule.get("threshold", 0)
        window_minutes = rule.get("window_minutes", 5)
        severity = rule.get("severity", 0)
        farm_id = rule.get("farm_id")
        camera_id = rule.get("camera_id")
        name = rule.get("name", "Unknown Rule")

        value = self._query_metric(metric, window_minutes, farm_id, camera_id)
        if value is None:
            return

        if value > threshold:
            msg = (
                f"Rule '{name}' triggered: {metric}={value} "
                f"exceeds threshold {threshold} "
                f"(window={window_minutes}m, farm={farm_id}, camera={camera_id})"
            )
            logger.warning(msg)
            self._create_alert(
                rule=rule,
                camera_id=camera_id,
                message=msg,
            )

    def _query_metric(
        self,
        metric: str,
        window_minutes: int,
        farm_id: str | None,
        camera_id: str | None,
    ) -> int | None:
        if not self._influx:
            return None

        filters = []
        if farm_id:
            filters.append(f'r["farm_id"] == "{farm_id}"')
        if camera_id:
            filters.append(f'r["camera_id"] == "{camera_id}"')

        filter_str = " and ".join(filters) if filters else "true"

        if metric == "head_count":
            query = f'''
                from(bucket: "{settings.INFLUX_BUCKET}")
                    |> range(start: -{window_minutes}m)
                    |> filter(fn: (r) => {filter_str})
                    |> filter(fn: (r) => r["track_id"] != "-1")
                    |> distinct(column: "track_id")
                    |> group()
                    |> count()
            '''
        elif metric == "detection_count":
            query = f'''
                from(bucket: "{settings.INFLUX_BUCKET}")
                    |> range(start: -{window_minutes}m)
                    |> filter(fn: (r) => {filter_str})
                    |> group()
                    |> count()
            '''
        else:
            return None

        try:
            result = 0
            for table in self._influx.query_api().query(query):
                for record in table.records:
                    result = max(result, record.get_value() or 0)
            return result
        except Exception as e:
            logger.error("InfluxDB query failed for metric %s: %s", metric, e)
            return None

    def _create_alert(
        self,
        rule: dict,
        camera_id: str | None,
        message: str,
    ) -> None:
        payload = {
            "camera_id": camera_id,
            "track_id": None,
            "type": rule.get("metric", "threshold"),
            "severity": rule.get("severity", 0),
            "message": message,
        }
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{settings.BUSINESS_BACKEND_URL}/v1/internal/alerts",
                    json=payload,
                )
                resp.raise_for_status()
                logger.info("Alert created: %s", message)
        except Exception as e:
            logger.error("Failed to create alert: %s", e)
