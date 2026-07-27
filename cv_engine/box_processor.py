import cv2
import numpy as np


def apply_nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.45,
) -> list[int]:
    if len(boxes) == 0:
        return []
    indices = cv2.dnn.NMSBoxes(
        bboxes=boxes.tolist(),
        scores=scores.tolist(),
        score_threshold=0.0,
        nms_threshold=iou_threshold,
    )
    if isinstance(indices, np.ndarray):
        return indices.flatten().tolist()
    return [int(i) for i in indices]


def filter_by_roi(
    boxes: np.ndarray,
    roi_polygon: list[list[float]] | None,
) -> list[bool]:
    if roi_polygon is None or len(roi_polygon) < 3:
        return [True] * len(boxes)

    contour = np.array(roi_polygon, dtype=np.float32)
    results = []
    for box in boxes:
        cx = float(box[0] + box[2] / 2)
        cy = float(box[1] + box[3] / 2)
        dist = cv2.pointPolygonTest(contour, (cx, cy), False)
        results.append(dist >= 0)
    return results


def process_detections(
    boxes: np.ndarray,
    scores: np.ndarray,
    class_ids: np.ndarray,
    roi_polygon: list[list[float]] | None = None,
    confidence_threshold: float = 0.55,
    nms_iou: float = 0.45,
) -> tuple[list[list[float]], list[float], list[int]]:
    if len(boxes) == 0:
        return [], [], []

    mask = scores >= confidence_threshold
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return [], [], []

    keep = apply_nms(boxes, scores, iou_threshold=nms_iou)
    boxes = boxes[keep]
    scores = scores[keep]
    class_ids = class_ids[keep]

    if roi_polygon is not None:
        in_roi = filter_by_roi(boxes, roi_polygon)
        boxes = boxes[in_roi]
        scores = scores[in_roi]
        class_ids = class_ids[in_roi]

    return boxes.tolist(), scores.tolist(), class_ids.tolist()
