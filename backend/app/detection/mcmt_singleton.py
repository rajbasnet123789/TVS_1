import logging

logger = logging.getLogger(__name__)

import asyncio

_tracker_instance = None
_tracker_lock = asyncio.Lock()


async def get_mcmt_tracker():
    global _tracker_instance
    if _tracker_instance is None:
        async with _tracker_lock:
            if _tracker_instance is None:
                from app.detection.mcmt.tracker import GlobalTracker
                _tracker_instance = GlobalTracker(
                    match_threshold=0.5,
                    spatial_constraint_distance=50.0,
                    temporal_constraint_seconds=5.0,
                )
                await _tracker_instance.load()
    return _tracker_instance


async def init_mcmt_tracker():
    tracker = await get_mcmt_tracker()
    logger.info("MCMT GlobalTracker initialized")


async def reset_mcmt_tracker():
    global _tracker_instance
    async with _tracker_lock:
        _tracker_instance = None
