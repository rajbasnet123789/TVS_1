"""
Hen Counter — YOLO Detection + Zone-Based Counting (Image Mode)

Production-level pipeline:
  1. User draws ROI zones in GUI (normalized 0-1 coordinates)
  2. YOLO detects hens inside ROI for each image
  3. Count detections per camera across all images
  4. MiewID ONLY at overlap regions (greedy clustering dedup)
  5. Final count = sum(per-camera counts) - overlap duplicates

Usage:
  python main.py                   # Run with saved ROI config
  python main.py --setup           # Launch ROI selector first
  python main.py --no-gui          # Headless mode
"""
import os
import sys
import time
import json
import logging
import argparse
from dataclasses import dataclass, field

import cv2
import numpy as np
import torch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
YOLO_MODEL_PATH = os.path.join(PARENT_DIR, "weight_model", "yolov10b.pt")
ROI_CONFIG_PATH = os.path.join(BASE_DIR, "roi_config.json")
WEIGHT_MODEL_DIR = os.path.join(PARENT_DIR, "weight_model")

sys.path.insert(0, PARENT_DIR)
sys.path.insert(0, WEIGHT_MODEL_DIR)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}


@dataclass
class PipelineConfig:
    conf_threshold: float = 0.10
    nms_iou_threshold: float = 0.20
    min_box_area: int = 0
    max_aspect_ratio: float = 10.0
    max_detect_res: int = 2048
    chicken_class_id: int = 14
    clahe_clip: float = 2.0
    gui_delay_ms: int = 0
    overlap_threshold: float = 0.20
    device: str = field(default_factory=lambda: "cuda" if torch.cuda.is_available() else "cpu")


def load_roi_config() -> dict:
    if not os.path.exists(ROI_CONFIG_PATH):
        return {}
    try:
        with open(ROI_CONFIG_PATH, "r") as f:
            data = json.load(f)
        return data.get("detection_roi", {})
    except Exception:
        return {}


def save_roi_config(config: dict):
    data = {}
    if os.path.exists(ROI_CONFIG_PATH):
        try:
            with open(ROI_CONFIG_PATH, "r") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["detection_roi"] = config
    with open(ROI_CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"ROI config saved: {ROI_CONFIG_PATH}")


def find_cameras() -> dict[str, list[str]]:
    """Find ALL images in each CH_XX directory. Returns {cam_id: [image_paths]}."""
    cameras = {}
    for ch in range(1, 7):
        ch_dir = os.path.join(PARENT_DIR, f"CH_{ch:02d}")
        if not os.path.isdir(ch_dir):
            continue
        img_files = sorted([
            f for f in os.listdir(ch_dir)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        ])
        if img_files:
            cam_id = f"CH_{ch:02d}"
            cameras[cam_id] = [os.path.join(ch_dir, f) for f in img_files]
    return cameras


def point_in_roi(px: float, py: float,
                 roi_polygon: list[list[float]],
                 frame_shape: tuple[int, int]) -> bool:
    if not roi_polygon:
        return True
    h, w = frame_shape[:2]
    pts = np.array([[int(x * w), int(y * h)] for x, y in roi_polygon],
                   dtype=np.int32)
    return cv2.pointPolygonTest(pts, (int(px), int(py)), False) >= 0


def nms_suppress(boxes: list[tuple], scores: list[float],
                 iou_threshold: float) -> list[int]:
    if not boxes:
        return []
    indices = cv2.dnn.NMSBoxes(
        [list(b) for b in boxes], scores, 0.0, iou_threshold
    )
    if indices is None or len(indices) == 0:
        return []
    return indices.flatten().tolist()


def draw_info(frame: np.ndarray, cam_id: str,
              count: int, dets_count: int,
              roi_polygon: list[list[float]],
              img_name: str = ""):
    h_f, w_f = frame.shape[:2]

    if roi_polygon:
        pts = np.array([[int(x * w_f), int(y * h_f)]
                        for x, y in roi_polygon], dtype=np.int32)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], (30, 30, 30))
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
        cv2.polylines(frame, [pts], True, (0, 255, 255), 2, cv2.LINE_AA)

    panel_h = 70
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h_f - panel_h), (w_f, h_f), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    cv2.putText(frame,
                f"{cam_id} | Hens: {count} | {img_name}",
                (10, h_f - panel_h + 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    cv2.putText(frame,
                f"Detections: {dets_count}",
                (10, h_f - panel_h + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)


def run_pipeline(cameras: dict[str, list[str]],
                 roi_config: dict,
                 cfg: PipelineConfig,
                 gui: bool = True,
                 use_miewid: bool = False):
    from ultralytics import YOLO

    model = YOLO(YOLO_MODEL_PATH)
    model.to(cfg.device)
    logger.info(f"YOLO chicken model loaded on {cfg.device}: {YOLO_MODEL_PATH}")

    overlap_dedup = None
    if use_miewid:
        from overlap_dedup import OverlapDeduplicator, OverlapZone
        overlap_zones = [
            OverlapZone("overlap_1", ["CH_01", "CH_02"],
                        [(0.3, 0.0), (0.7, 0.0), (0.7, 1.0), (0.3, 1.0)]),
            OverlapZone("overlap_2", ["CH_03", "CH_06"],
                        [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]),
        ]
        overlap_dedup = OverlapDeduplicator(overlap_zones,
                                            threshold=cfg.overlap_threshold)
        overlap_dedup.load()

    if gui:
        window = "Hen Counter - YOLO Image Counting"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 1600, 900)

    cam_results = {}
    for cam_id in sorted(cameras.keys()):
        cam_results[cam_id] = {"count": 0, "total_dets": 0, "images": 0}

    total_images = 0
    total_detections = 0
    start_time = time.time()

    COLORS = [(0, 255, 0), (255, 0, 0), (0, 0, 255),
              (255, 255, 0), (0, 255, 255), (255, 0, 255),
              (128, 255, 0), (255, 128, 0)]

    for cam_id in sorted(cameras.keys()):
        image_paths = cameras[cam_id]
        roi_poly = roi_config.get(cam_id, [])
        logger.info(f"Processing {cam_id}: {len(image_paths)} images, "
                    f"roi={'yes' if roi_poly else 'no'}")

        for img_path in image_paths:
            frame = cv2.imread(img_path)
            if frame is None:
                logger.warning(f"  Skip: cannot read {img_path}")
                continue

            h_f, w_f = frame.shape[:2]
            if max(h_f, w_f) > cfg.max_detect_res:
                sc = cfg.max_detect_res / max(h_f, w_f)
                frame = cv2.resize(frame, (int(w_f * sc), int(h_f * sc)))
                h_f, w_f = frame.shape[:2]

            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=cfg.clahe_clip, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            frame = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

            results = model(
                source=frame, conf=cfg.conf_threshold,
                imgsz=cfg.max_detect_res, device=cfg.device,
                verbose=False, classes=[cfg.chicken_class_id]
            )[0]

            dets_frame = []
            if results.boxes is not None and len(results.boxes) > 0:
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    bw, bh = int(x2 - x1), int(y2 - y1)
                    if bw * bh < cfg.min_box_area:
                        continue
                    if max(bw, bh) / max(min(bw, bh), 1) > cfg.max_aspect_ratio:
                        continue
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    if not point_in_roi(cx, cy, roi_poly, (h_f, w_f)):
                        continue
                    dets_frame.append({
                        "bbox": (x1, y1, bw, bh),
                        "conf": conf,
                    })

            if len(dets_frame) > 1:
                nms_boxes = [(d["bbox"][0], d["bbox"][1],
                              d["bbox"][2], d["bbox"][3])
                             for d in dets_frame]
                nms_scores = [d["conf"] for d in dets_frame]
                keep = nms_suppress(nms_boxes, nms_scores, cfg.nms_iou_threshold)
                dets_frame = [dets_frame[i] for i in keep]

            n_dets = len(dets_frame)
            cam_results[cam_id]["count"] += n_dets
            cam_results[cam_id]["total_dets"] += n_dets
            cam_results[cam_id]["images"] += 1
            total_detections += n_dets
            total_images += 1

            if use_miewid and overlap_dedup:
                overlap_dedup.extract_overlap_embeddings(cam_id, frame, dets_frame)

            img_name = os.path.basename(img_path)
            for det in dets_frame:
                x1, y1, bw, bh = det["bbox"]
                conf = det.get("conf", 0)
                color = COLORS[total_detections % len(COLORS)]
                cv2.rectangle(frame, (int(x1), int(y1)),
                              (int(x1 + bw), int(y1 + bh)), color, 2)
                cv2.putText(frame, f"{conf:.2f}", (int(x1), max(int(y1) - 6, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

            draw_info(frame, cam_id, n_dets, n_dets, roi_poly, img_name)

            if gui:
                display = cv2.resize(frame, (900, 700))
                cv2.imshow(window, display)
                key = cv2.waitKey(0) & 0xFF
                if key == ord("q"):
                    logger.info("Quit requested")
                    cv2.destroyAllWindows()
                    return

            logger.info(f"  {img_name}: {n_dets} hens detected")

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.info("FINAL COUNT — Image-Based Detection")
    logger.info("=" * 60)
    logger.info(f"Total images: {total_images} | Wall: {elapsed:.2f}s")

    raw_total = 0
    for cam_id in sorted(cam_results):
        s = cam_results[cam_id]
        raw_total += s["count"]
        logger.info(f"  {cam_id}: {s['count']} hens across {s['images']} images")

    overlap_dup = 0
    if overlap_dedup:
        overlap_dedup.find_duplicates()
        overlap_dup = overlap_dedup.get_total_duplicates()
        overlap_dedup.clear_embeddings()

    final_count = raw_total - overlap_dup
    logger.info(f"Raw total: {raw_total}")
    logger.info(f"Overlap dedup: -{overlap_dup}")
    logger.info(f"FINAL COUNT: {final_count}")
    logger.info("=" * 60)

    results = {
        "config": "YOLO image detection" +
                  (" + MiewID overlap" if use_miewid else ""),
        "elapsed_s": round(elapsed, 2),
        "total_images": total_images,
        "per_camera": cam_results,
        "raw_total": raw_total,
        "overlap_duplicates": overlap_dup,
        "final_count": final_count,
    }
    report_path = os.path.join(BASE_DIR, "count_report.json")
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Report saved: {report_path}")

    if gui:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Hen Counter — YOLO Image Detection"
    )
    parser.add_argument("--setup", action="store_true",
                        help="Launch ROI selector GUI first")
    parser.add_argument("--no-gui", action="store_true",
                        help="Run headless (no OpenCV windows)")
    parser.add_argument("--miewid", action="store_true",
                        help="Enable MiewID at overlap zones")
    parser.add_argument("--conf", type=float, default=0.15,
                        help="Detection confidence threshold")
    parser.add_argument("--nms-iou", type=float, default=0.45,
                        help="NMS IoU threshold (0.0-1.0)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Hen Counter — YOLO + Zone-Based Counting (Image Mode)")
    logger.info("No Full ReID — MiewID Only at Overlap Regions")
    logger.info("=" * 60)

    cameras = find_cameras()
    logger.info(f"Found {len(cameras)} cameras:")
    for cid, paths in sorted(cameras.items()):
        logger.info(f"  {cid}: {len(paths)} images")

    if not cameras:
        logger.error("No cameras found!")
        sys.exit(1)

    if args.setup:
        from roi_selector import ROISelector
        frames = {}
        for cid, paths in sorted(cameras.items()):
            frame = cv2.imread(paths[0])
            if frame is not None:
                frames[cid] = frame
                logger.info(f"Loaded {cid}: {frame.shape[1]}x{frame.shape[0]}")
        if frames:
            selector = ROISelector()
            config = selector.select_rois(frames)
            if config:
                selector.save_config(config)
                logger.info(f"Saved ROI config for: {list(config.keys())}")
            else:
                logger.info("No ROIs defined. Using full frame.")
        else:
            logger.error("Could not load any frames!")

    roi_config = load_roi_config()
    if roi_config:
        logger.info(f"ROI config loaded for: {list(roi_config.keys())}")
    else:
        logger.info("ROI config: None (full frame)")

    cfg = PipelineConfig(
        conf_threshold=args.conf,
        nms_iou_threshold=args.nms_iou,
    )

    run_pipeline(
        cameras, roi_config, cfg,
        gui=not args.no_gui,
        use_miewid=args.miewid,
    )


if __name__ == "__main__":
    main()
