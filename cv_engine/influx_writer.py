import logging
import queue
import threading
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from cv_engine.config import settings

logger = logging.getLogger(__name__)


class InfluxWriter(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="influx-writer")
        self._queue: queue.Queue = queue.Queue(maxsize=5000)
        self._stop_event = threading.Event()
        self._client: InfluxDBClient | None = None
        self._write_api = None

    def start(self):
        self._client = InfluxDBClient(
            url=settings.INFLUX_URL,
            token=settings.INFLUX_TOKEN,
            org=settings.INFLUX_ORG,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        super().start()

    def enqueue(self, event: dict) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("InfluxDB write queue full, dropping event")

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        logger.info("InfluxDB writer started")
        while not self._stop_event.is_set():
            try:
                event = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._write_point(event)
            except Exception as e:
                logger.error("Failed to write to InfluxDB: %s", e)
        self._drain()
        if self._client:
            self._client.close()
        logger.info("InfluxDB writer stopped")

    def _write_point(self, event: dict) -> None:
        point = (
            Point("detections")
            .tag("camera_id", event["camera_id"])
            .tag("farm_id", event.get("farm_id", ""))
            .tag("track_id", str(event.get("track_id", "-1")))
            .tag("class_name", event.get("class_name", "unknown"))
            .field("confidence", float(event.get("confidence", 0.0)))
            .field("x", float(event.get("x", 0.0)))
            .field("y", float(event.get("y", 0.0)))
            .field("w", float(event.get("w", 0.0)))
            .field("h", float(event.get("h", 0.0)))
            .time(datetime.now(timezone.utc), WritePrecision.MS)
        )
        self._write_api.write(
            bucket=settings.INFLUX_BUCKET,
            org=settings.INFLUX_ORG,
            record=point,
        )

    def _drain(self) -> None:
        while not self._queue.empty():
            try:
                event = self._queue.get_nowait()
                self._write_point(event)
            except queue.Empty:
                break
            except Exception as e:
                logger.error("Failed to write drained event to InfluxDB: %s", e)
