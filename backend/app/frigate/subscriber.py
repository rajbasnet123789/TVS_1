import asyncio
import json
import logging
from datetime import datetime, timezone

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


class FrigateSubscriber:
    def __init__(self):
        self._running = False
        self._client = None
        self._task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._intruder_task: asyncio.Task | None = None
        self._loop = None
        self._health_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._intruder_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._mortality_grids = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run())
        self._health_task = asyncio.create_task(self._health_worker())
        self._intruder_task = asyncio.create_task(self._intruder_worker())
        logger.info("Frigate MQTT subscriber started")

    async def stop(self):
        self._running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        if self._intruder_task:
            self._intruder_task.cancel()
            try:
                await self._intruder_task
            except asyncio.CancelledError:
                pass
            self._intruder_task = None
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Frigate MQTT subscriber stopped")

    async def _run(self):
        import paho.mqtt.client as mqtt

        def on_connect(client, userdata, flags, rc):
            logger.info(f"MQTT connected to {settings.mqtt_broker}:{settings.mqtt_port} (rc={rc})")
            client.subscribe("frigate/events")
            client.subscribe("frigate/+/+/+/+")

        def on_message(client, userdata, msg):
            asyncio.run_coroutine_threadsafe(
                self._handle_message(msg.topic, msg.payload),
                self._loop,
            )

        self._client = mqtt.Client()
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        self._client.on_connect = on_connect
        self._client.on_message = on_message

        connected = False
        while self._running:
            try:
                if not connected:
                    self._client.connect(settings.mqtt_broker, settings.mqtt_port, keepalive=60)
                    self._client.loop_start()
                    connected = True
                await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"MQTT connection failed: {e}, retrying in 5s")
                connected = False
                await asyncio.sleep(5)

    async def _handle_message(self, topic: str, payload: bytes):
        try:
            data = json.loads(payload.decode()) if payload else {}
        except json.JSONDecodeError:
            return

        after = data.get("after", {})
        if not after or after.get("label") not in ("bird", "person"):
            return

        # 1. Handle standard Frigate events topic: "frigate/events"
        if topic == "frigate/events":
            camera_name = after.get("camera")
            event_type = data.get("type")
            if camera_name and event_type in ("new", "update"):
                await self._handle_detection_event(camera_name, data)
            return

        # 2. Handle 4+ part topic structure fallback (e.g. frigate/camera_name/events/new)
        topic_parts = topic.split("/")
        if len(topic_parts) >= 4:
            _, camera_name, event_type, *rest = topic_parts
            event_subtype = rest[0] if rest else ""
            if event_type == "events" and event_subtype in ("new", "update"):
                await self._handle_detection_event(camera_name, data)

    async def _handle_detection_event(self, camera_name: str, data: dict):
        after = data.get("after", data)
        if not after:
            return

        label = after.get("label")
        if label not in ("bird", "person"):
            return

        event_id = after.get("id")
        camera_id = after.get("camera") or camera_name
        farm_id = await self._resolve_farm_id(camera_name)
        top_score = after.get("top_score", 0)
        false_positive = after.get("false_positive", False)
        start_time = after.get("start_time")
        end_time = after.get("end_time")
        snapshot_captured = after.get("has_snapshot", False)
        snapshot_url = f"/api/events/{event_id}/snapshot.jpg" if event_id and snapshot_captured else None

        # Frigate bbox: [xmin, ymin, xmax, ymax] in absolute pixels
        frigate_bbox = after.get("bbox")
        bbox = None
        if frigate_bbox and len(frigate_bbox) == 4:
            xmin, ymin, xmax, ymax = frigate_bbox
            bbox = {"x": xmin, "y": ymin, "w": xmax - xmin, "h": ymax - ymin}

        detection_data = {
            "type": "detection",
            "camera_id": camera_id,
            "camera_name": camera_name,
            "farm_id": farm_id,
            "event_id": event_id,
            "confidence": round(top_score, 3),
            "label": label,
            "false_positive": false_positive,
            "bbox": bbox,
            "start_time": start_time,
            "end_time": end_time,
            "snapshot_url": snapshot_url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if not false_positive and snapshot_captured:
            if label == "bird":
                await self._queue_health_check(camera_name, event_id, detection_data)
            elif label == "person":
                await self._queue_intruder_check(camera_name, event_id, detection_data)

        await self._publish_detection(detection_data)

    async def _resolve_farm_id(self, camera_name: str) -> str | None:
        try:
            from app.database import async_session
            from sqlalchemy import select
            from app.cameras.models import Camera
            async with async_session() as db:
                result = await db.execute(select(Camera).where(Camera.name == camera_name))
                cam = result.scalar_one_or_none()
                if cam and cam.farm_id:
                    return str(cam.farm_id)
        except Exception as e:
            logger.warning(f"Failed to resolve farm_id for {camera_name}: {e}")
        return None

    async def _resolve_camera_and_farm(self, camera_name: str) -> tuple[str | None, str | None]:
        try:
            from app.database import async_session
            from sqlalchemy import select
            from app.cameras.models import Camera
            async with async_session() as db:
                result = await db.execute(select(Camera).where(Camera.name == camera_name))
                cam = result.scalar_one_or_none()
                if cam:
                    return str(cam.id), (str(cam.farm_id) if cam.farm_id else None)
        except Exception as e:
            logger.warning(f"Failed to resolve camera and farm for {camera_name}: {e}")
        return None, None

    async def _publish_detection(self, data: dict):
        from app.websocket.manager import manager

        camera_name = data["camera_name"]
        farm_id = data.get("farm_id")
        global_id = data.get("global_id")

        await manager.broadcast("detections", data)
        if farm_id:
            await manager.broadcast(f"farm_{farm_id}/detections", data)

        try:
            await self._store_influx(data)
        except Exception as e:
            logger.warning(f"InfluxDB store error: {e}")

    async def _store_influx(self, data: dict):
        from influxdb_client.client.write_api import SYNCHRONOUS
        from app.detection.queries import _get_influx

        client = _get_influx()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        tags = {
            "camera_id": data["camera_id"],
            "farm_id": data.get("farm_id", "unknown"),
            "class_name": data["label"],
        }
        global_id = data.get("global_id")
        if global_id is not None:
            tags["global_id"] = str(global_id)
        bbox = data.get("bbox") or {}
        point = {
            "measurement": "detections",
            "tags": tags,
            "fields": {
                "confidence": data["confidence"],
                "x": bbox.get("x", 0),
                "y": bbox.get("y", 0),
                "w": bbox.get("w", 0),
                "h": bbox.get("h", 0),
            },
            "time": datetime.now(timezone.utc),
        }
        write_api.write(bucket=settings.influx_bucket, record=point)

    async def _queue_health_check(self, camera_name: str, event_id: str, detection: dict):
        await self._health_queue.put((camera_name, event_id, detection))

    async def _health_worker(self):
        while self._running:
            try:
                camera_name, event_id, detection = await asyncio.wait_for(
                    self._health_queue.get(), timeout=30
                )
                await self._process_health(camera_name, event_id, detection)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Health worker error: {e}")

    async def _save_snapshot(self, snapshot_bytes: bytes, camera_name: str, event_id: str, farm_id: str | None) -> str | None:
        if not farm_id:
            return None
        try:
            from app.media.client import put_object
            key = f"snapshots/{camera_name}/{event_id}.jpg"
            await put_object(farm_id, key=key, data=snapshot_bytes, content_type="image/jpeg")
            return key
        except Exception as e:
            logger.warning(f"Failed to save snapshot for {camera_name}/{event_id}: {e}")
            return None

    async def _process_health(self, camera_name: str, event_id: str, detection: dict):
        try:
            from app.frigate.client import get_snapshot
            from app.detection.detector import detector

            snapshot_bytes = await get_snapshot(camera_name)
            if snapshot_bytes is None:
                return

            # Save snapshot (best effort)
            farm_id = detection.get("farm_id")
            snapshot_key = await self._save_snapshot(snapshot_bytes, camera_name, event_id, farm_id)

            import cv2
            arr = np.frombuffer(snapshot_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return

            bbox = detection.get("bbox", {})
            if not bbox:
                h, w = frame.shape[:2]
                margin = 0.2
                bbox = {"x": w * margin, "y": h * margin, "w": w * (1 - 2 * margin), "h": h * (1 - 2 * margin)}

            frame_detections = [{
                "track_id": detection.get("event_id"),
                "class_name": "bird",
                "confidence": detection.get("confidence", 0.0),
                "bbox": bbox,
            }]

            # Run MCMT tracker to assign cross-camera global ID
            global_id = None
            try:
                from app.detection.mcmt_singleton import get_mcmt_tracker
                tracker = await get_mcmt_tracker()
                tracked = tracker.process_frame(
                    detections=frame_detections,
                    track_ids=[detection.get("event_id")],
                    frame=frame,
                    camera_id=detection.get("camera_id", camera_name),
                )
                if tracked and len(tracked) > 0:
                    global_id = tracked[0].get("global_id")
            except Exception as e:
                logger.warning(f"MCMT tracking failed for {camera_name}: {e}")

            # Run health classification
            health_results = await detector.classify(frame, frame_detections)
            if health_results:
                for h in health_results:
                    h["global_id"] = global_id
                await self._store_health(health_results, camera_name, farm_id, global_id=global_id)
                from app.websocket.manager import manager
                await manager.broadcast("health", {
                    "type": "health",
                    "camera_id": detection.get("camera_id"),
                    "camera_name": camera_name,
                    "farm_id": farm_id,
                    "global_id": global_id,
                    "event_id": event_id,
                    "results": health_results,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # Run fine-tuned YOLO chicken detector on full snapshot frame (Chicken Detector model)
            try:
                if detector._health_model is None:
                    await detector.load_health()
                yolo_model = detector._health_model
                loop = asyncio.get_running_loop()
                full_frame_preds = await loop.run_in_executor(
                    None,
                    lambda: yolo_model(frame, conf=0.05, iou=0.4, verbose=False)
                )

                full_frame_dets = []
                if len(full_frame_preds) > 0 and full_frame_preds[0].boxes is not None:
                    for box in full_frame_preds[0].boxes:
                        bx = box.xyxy[0].tolist()
                        bc = float(box.conf[0])
                        full_frame_dets.append((bx[0], bx[1], bx[2], bx[3], bc))

                flock_count = len(full_frame_dets)
                logger.info(f"YOLO full-frame chicken count on {camera_name}: {flock_count} birds")
                await self._store_flock_count(camera_name, farm_id, flock_count)

                # Initialize & Update MortalityGrid for the camera
                h, w = frame.shape[:2]
                if camera_name not in self._mortality_grids:
                    from app.detection.mortality import MortalityGrid
                    self._mortality_grids[camera_name] = MortalityGrid(roi_bbox=(0, 0, w, h))
                grid = self._mortality_grids[camera_name]

                timestamp_sec = datetime.now(timezone.utc).timestamp()
                grid.update(full_frame_dets, timestamp_sec)

                # Flush detection
                if grid.detect_natural_flush():
                    grid.process_flush(timestamp_sec)

                # Confirm deaths
                grid.confirm_deaths(timestamp_sec)

                # Flag mortalities
                dead_count = grid.get_confirmed_dead_count()
                if dead_count > 0:
                    if not hasattr(self, "_last_mortality_alert"):
                        self._last_mortality_alert = {}

                    last_alert_time = self._last_mortality_alert.get(camera_name, 0)
                    if timestamp_sec - last_alert_time >= 1800:
                        self._last_mortality_alert[camera_name] = timestamp_sec
                        logger.warning(f"Confirmed {dead_count} dead bird(s) on {camera_name}")
                        camera_id, farm_id = await self._resolve_camera_and_farm(camera_name)

                        from app.database import async_session
                        from app.alerts.service import create_alert
                        from app.alerts.schemas import AlertCreate

                        alert_data = AlertCreate(
                            camera_id=camera_id,
                            chicken_id=None,
                            track_id=event_id,
                            type="mortality",
                            severity=2,
                            message=f"Mortality Warning: {dead_count} dead bird(s) detected on camera {camera_name}!"
                        )

                        async with async_session() as db:
                            await create_alert(db, alert_data, farm_id=farm_id)

            except Exception as ex:
                logger.warning(f"Chicken detector/MortalityGrid failed: {ex}")

            # Re-publish detection with global_id and snapshot_key attached
            enriched = {**detection}
            if global_id is not None:
                enriched["global_id"] = global_id
            if snapshot_key is not None:
                enriched["snapshot_key"] = snapshot_key
            await self._publish_detection(enriched)

        except Exception as e:
            logger.warning(f"Health processing failed for {camera_name}/{event_id}: {e}")

    async def _store_health(self, health_results: list[dict], camera_name: str, farm_id: str | None, global_id: int | None = None):
        from influxdb_client.client.write_api import SYNCHRONOUS
        from app.detection.queries import _get_influx

        client = _get_influx()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        points = []
        for h in health_results:
            tags = {
                "camera_id": camera_name,
                "farm_id": farm_id or "unknown",
                "health_class": h.get("health_class", "unknown"),
            }
            if global_id is not None:
                tags["global_id"] = str(global_id)
            points.append({
                "measurement": "health",
                "tags": tags,
                "fields": {
                    "health_score": float(h["health_score"]),
                    "health_confidence": float(h["health_confidence"]),
                    "track_id": str(h.get("track_id", "-1")),
                },
                "time": datetime.now(timezone.utc),
            })
        if points:
            write_api.write(bucket=settings.influx_bucket, record=points)

    async def _store_flock_count(self, camera_name: str, farm_id: str | None, count: int):
        from influxdb_client.client.write_api import SYNCHRONOUS
        from app.detection.queries import _get_influx

        client = _get_influx()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        point = {
            "measurement": "flock_count",
            "tags": {
                "camera_id": camera_name,
                "farm_id": farm_id or "unknown",
            },
            "fields": {
                "count": int(count),
            },
            "time": datetime.now(timezone.utc),
        }
        write_api.write(bucket=settings.influx_bucket, record=point)

    async def _queue_intruder_check(self, camera_name: str, event_id: str, detection: dict):
        await self._intruder_queue.put((camera_name, event_id, detection))

    async def _intruder_worker(self):
        while self._running:
            try:
                camera_name, event_id, detection = await asyncio.wait_for(
                    self._intruder_queue.get(), timeout=30
                )
                await self._process_intruder(camera_name, event_id, detection)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning(f"Intruder worker error: {e}")

    async def _save_intruder_snapshot(self, snapshot_bytes: bytes, event_id: str, farm_id: str | None) -> str | None:
        if not farm_id:
            return None
        try:
            from app.media.client import put_object
            key = f"media/intruders/{event_id}.jpg"
            await put_object(farm_id, key=key, data=snapshot_bytes, content_type="image/jpeg")
            return key
        except Exception as e:
            logger.warning(f"Failed to save intruder snapshot for event {event_id}: {e}")
            return None

    async def _process_intruder(self, camera_name: str, event_id: str, detection: dict):
        try:
            from app.frigate.client import get_event_snapshot, get_snapshot
            from app.detection.intruder import intruder_detector

            snapshot_bytes = await get_event_snapshot(event_id)
            if not snapshot_bytes:
                snapshot_bytes = await get_snapshot(camera_name)
            if not snapshot_bytes:
                logger.warning(f"No snapshot bytes found for intruder event {event_id} on {camera_name}")
                return

            import cv2
            arr = np.frombuffer(snapshot_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning(f"Could not decode snapshot bytes for intruder event {event_id}")
                return

            camera_id, farm_id = await self._resolve_camera_and_farm(camera_name)

            bbox = detection.get("bbox")
            # Verify face
            match_res = intruder_detector.verify_face(frame, farm_id, bbox)
            if match_res is not None:
                name, score = match_res
                logger.info(f"Intruder check matched known person: {name} with score {score:.2f} (farm: {farm_id})")
                return

            # Unknown person/intruder detected!
            logger.warning(f"Unknown person detected on camera {camera_name} (event {event_id})!")

            # Save snapshot
            await self._save_intruder_snapshot(snapshot_bytes, event_id, farm_id)

            # Create Alert database entry (which automatically broadcasts over WebSockets)
            from app.database import async_session
            from app.alerts.service import create_alert
            from app.alerts.schemas import AlertCreate

            alert_data = AlertCreate(
                camera_id=camera_id,
                chicken_id=None,
                track_id=event_id,
                type="intruder",
                severity=2,
                message=f"Unknown person detected on camera {camera_name} (Intruder Warning)"
            )

            async with async_session() as db:
                await create_alert(db, alert_data, farm_id=farm_id)

        except Exception as e:
            logger.warning(f"Intruder processing failed for {camera_name}/{event_id}: {e}")


subscriber = FrigateSubscriber()
