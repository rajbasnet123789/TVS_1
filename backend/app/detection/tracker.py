import asyncio
import logging

import numpy as np

logger = logging.getLogger(__name__)


class BotSortWrapper:
    def __init__(self):
        self._tracker = None

    async def load(self):
        if self._tracker is not None:
            return
        try:
            import torch
            from boxmot.reid.core import ReID
            from boxmot.trackers.bbox.botsort.botsort import BotSort

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            reid_model = ReID(device=device).model
            self._tracker = BotSort(
                reid_model=reid_model,
                track_high_thresh=0.25,
                track_low_thresh=0.1,
                new_track_thresh=0.25,
                track_buffer=30,
                match_thresh=0.8,
                proximity_thresh=0.5,
                appearance_thresh=0.8,
                with_reid=True,
                cmc_method="ecc",
                frame_rate=30,
            )
            logger.info(f"BoT-SORT tracker loaded with OSNet ReID on {device}")
        except ImportError:
            logger.warning("boxmot not available, using fallback tracker")
            self._tracker = "fallback"

    async def update(
        self, detections: list[dict], frame: np.ndarray
    ) -> list[dict]:
        if self._tracker is None:
            await self.load()

        if self._tracker == "fallback":
            return self._fallback_track(detections)

        if not detections:
            return []

        boxes = np.array([
            [d["bbox"]["x"], d["bbox"]["y"], d["bbox"]["w"], d["bbox"]["h"]]
            for d in detections
        ], dtype=np.float32)
        confidences = np.array([d["confidence"] for d in detections], dtype=np.float32)
        class_ids = np.array([d["class_id"] for d in detections], dtype=np.float32)

        xyxy = np.zeros_like(boxes)
        xyxy[:, 0] = boxes[:, 0]
        xyxy[:, 1] = boxes[:, 1]
        xyxy[:, 2] = boxes[:, 0] + boxes[:, 2]
        xyxy[:, 3] = boxes[:, 1] + boxes[:, 3]

        dets_np = np.column_stack([xyxy, confidences, class_ids])

        loop = asyncio.get_running_loop()
        tracked = await loop.run_in_executor(
            None, lambda: self._tracker.update(dets_np, frame)
        )

        result = []
        if tracked is not None and len(tracked) > 0:
            track_ids = tracked.id
            for i, d in enumerate(detections):
                entry = {**d}
                if i < len(track_ids):
                    entry["track_id"] = int(track_ids[i])
                else:
                    entry["track_id"] = None
                result.append(entry)
        else:
            for d in detections:
                entry = {**d}
                entry["track_id"] = None
                result.append(entry)

        return result

    def _fallback_track(self, detections: list[dict]) -> list[dict]:
        for i, d in enumerate(detections):
            d["track_id"] = i + 1
        return detections


tracker = BotSortWrapper()
