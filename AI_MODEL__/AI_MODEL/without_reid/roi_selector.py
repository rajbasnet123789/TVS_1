"""
ROI Selector GUI — User draws polygon counting zones on camera frames.

Coordinates stored as normalized (0..1) values for resolution independence.
Left click  = add polygon point
Right click = close polygon (minimum 3 points)
Enter       = close polygon (minimum 3 points)
Keys:
  r  = reset current polygon
  n  = next camera (without saving)
  s  = save current polygon (3+ points needed)
  q  = quit and save ALL drawn ROIs
"""
import cv2
import numpy as np
import json
import os
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "roi_config.json")


def _to_normalized(pts_pixel, w, h):
    return [[float(x) / w, float(y) / h] for x, y in pts_pixel]


def _to_pixel(pts_norm, w, h):
    return np.array([[int(x * w), int(y * h)] for x, y in pts_norm],
                    dtype=np.int32)


class ROISelector:
    def __init__(self):
        self.points = []
        self.polygons_norm: dict[str, list[list[float]]] = {}
        self.current_cam = ""
        self.frame = None
        self.clone = None
        self.frame_w = 0
        self.frame_h = 0
        self.window = "ROI Selector"

    def _close_polygon(self):
        if len(self.points) >= 3:
            norm = _to_normalized(self.points, self.frame_w, self.frame_h)
            self.polygons_norm[self.current_cam] = norm
            logger.info(f"[{self.current_cam}] ROI saved: {len(self.points)} points")
            self.points = []
            self._draw()
        elif self.points:
            logger.info(f"[{self.current_cam}] Need 3+ points to close (have {len(self.points)})")

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.points.append((x, y))
            self._draw()
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._close_polygon()

    def _draw(self):
        self.frame = self.clone.copy()
        h, w = self.frame.shape[:2]

        if self.points:
            pts = np.array(self.points, dtype=np.int32)
            overlay = self.frame.copy()
            cv2.fillPoly(overlay, [pts], (0, 255, 0))
            cv2.addWeighted(overlay, 0.25, self.frame, 0.75, 0, self.frame)
            cv2.polylines(self.frame, [pts], True, (0, 255, 0), 2,
                          cv2.LINE_AA)
            for p in self.points:
                cv2.circle(self.frame, p, 5, (0, 0, 255), -1)

        if self.current_cam in self.polygons_norm:
            pts = _to_pixel(self.polygons_norm[self.current_cam], w, h)
            cv2.polylines(self.frame, [pts], True, (255, 255, 0), 2,
                          cv2.LINE_AA)
            cx = int(np.mean(pts[:, 0]))
            cy = int(np.mean(pts[:, 1]))
            cv2.putText(self.frame, f"{self.current_cam} ROI SET",
                        (cx - 50, cy), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 0), 2)

        cv2.rectangle(self.frame, (0, 0), (w, 35), (0, 0, 0), -1)
        info = (f"{self.current_cam} | Points: {len(self.points)} | "
                f"ROIs set: {list(self.polygons_norm.keys())}")
        cv2.putText(self.frame, info, (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(self.frame,
                    "LClick:Add | RClick/Enter/s:Save(3+) | r:Reset | "
                    "n:Next | q:Quit&Save",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.4, (200, 200, 200), 1)
        cv2.imshow(self.window, self.frame)

    def select_rois(self, camera_frames: dict[str, np.ndarray]) -> dict:
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window, 1000, 700)
        cv2.setMouseCallback(self.window, self._mouse_callback)

        cam_list = sorted(camera_frames.keys())
        idx = 0

        while idx < len(cam_list):
            self.current_cam = cam_list[idx]
            self.frame = camera_frames[self.current_cam].copy()
            self.clone = self.frame.copy()
            self.frame_h, self.frame_w = self.frame.shape[:2]
            self.points = []
            logger.info(f"Draw ROI for {self.current_cam} "
                        f"(or press 's' to skip)")
            self._draw()

            while True:
                key = cv2.waitKey(0) & 0xFF
                if key == ord("q"):
                    cv2.destroyAllWindows()
                    return self.polygons_norm
                elif key == ord("n"):
                    idx += 1
                    break
                elif key == ord("r"):
                    self.points = []
                    self._draw()
                elif key == ord("s"):
                    self._close_polygon()
                    self._draw()
                elif key == 13:  # Enter
                    self._close_polygon()

        cv2.destroyAllWindows()
        return self.polygons_norm

    @staticmethod
    def save_config(config: dict):
        data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data["detection_roi"] = config
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"ROI config saved: {CONFIG_PATH}")

    @staticmethod
    def load_config() -> dict:
        if not os.path.exists(CONFIG_PATH):
            return {}
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            return data.get("detection_roi", {})
        except Exception:
            return {}

    @staticmethod
    def mask_from_roi(frame: np.ndarray,
                      roi_polygon: list[list[float]]) -> np.ndarray:
        if not roi_polygon:
            return np.ones(frame.shape[:2], dtype=np.uint8)
        h, w = frame.shape[:2]
        pts = _to_pixel(roi_polygon, w, h)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.fillPoly(mask, [pts], 255)
        return mask


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cameras = {}
    for ch in range(1, 7):
        ch_dir = os.path.join(PARENT_DIR, f"CH_{ch:02d}")
        if not os.path.isdir(ch_dir):
            continue
        img_files = [f for f in os.listdir(ch_dir)
                     if os.path.splitext(f)[1].lower() in
                     {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}]
        if not img_files:
            continue
        path = os.path.join(ch_dir, img_files[0])
        frame = cv2.imread(path)
        if frame is not None:
            cameras[f"CH_{ch:02d}"] = frame
            logger.info(f"Loaded {ch_dir}: {frame.shape[1]}x{frame.shape[0]}")

    if not cameras:
        logger.error("No camera frames found!")
    else:
        selector = ROISelector()
        config = selector.select_rois(cameras)
        if config:
            selector.save_config(config)
        else:
            logger.info("No ROIs defined.")
