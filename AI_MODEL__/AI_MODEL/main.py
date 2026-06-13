import cv2
import os
import sys
import torch
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))
from hen_counter import HenCounter

# ==========================================
# 1. SETUP & MODEL LOADING
# ==========================================
model = YOLO('yolov8x.pt')

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

video_path = r"C:\Users\wwwra\Downloads\WhatsApp Video 2026-06-10 at 11.28.32 AM.mp4"

if not os.path.exists(video_path):
    print(f"Error: Video file not found at {video_path}")
    exit()

cap = cv2.VideoCapture(video_path)

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

hen_counter = HenCounter(frame_width, frame_height)

# ==========================================
# 2. GUI WINDOW SETUP
# ==========================================
window_name = "Poultry Farm - Zone Counting"
cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

print(f"Running on: {device}")
print(f"Resolution: {frame_width}x{frame_height}")
print("Counting mode: Zone-based + BoT-SORT (OSNet ReID)")
print("Press 'q' to quit, 'r' to reset counter, 'z' to toggle zones.")


def draw_zones(frame, counter, show_zones):
    if not show_zones:
        return
    overlay = frame.copy()
    for zone in counter.counter._zones:
        pts = np.array(zone.polygon, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], (0, 255, 0, 30))
        cv2.polylines(overlay, [pts], True, (0, 255, 0), 1)
        cx = int(np.mean([p[0] for p in zone.polygon]))
        cy = int(np.mean([p[1] for p in zone.polygon]))
        cv2.putText(overlay, zone.name, (cx - 30, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)


def draw_trajectories(frame, trajectories, active_hens):
    for track_id, points in trajectories.items():
        if len(points) < 2:
            continue
        pts = np.array(points[-30:], dtype=np.int32)
        for i in range(1, len(pts)):
            thickness = int(1 + (i / len(pts)) * 2)
            alpha = i / len(pts)
            color = (0, int(150 * alpha + 50), int(255 * (1 - alpha)))
            cv2.line(frame, tuple(pts[i - 1]), tuple(pts[i]), color, thickness)


# ==========================================
# 3. MAIN PROCESSING LOOP
# ==========================================
show_zones = True

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    results = model.track(
        source=frame,
        conf=0.4,
        classes=[14],
        imgsz=1280,
        device=device,
        verbose=False,
        tracker="botsort_custom.yaml",
        persist=True,
    )[0]

    detections = []
    track_ids = []

    if results.boxes is not None and len(results.boxes) > 0:
        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            tid = int(box.id[0]) if box.id is not None else None

            detections.append({
                "bbox": {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1},
                "confidence": conf,
                "class_id": cls_id,
                "class_name": results.names.get(cls_id, str(cls_id)),
            })
            track_ids.append(tid)

    frame_result = hen_counter.process_frame(detections, track_ids)

    draw_zones(frame, hen_counter, show_zones)
    draw_trajectories(frame, hen_counter.get_trajectories(), hen_counter._active_hens)

    for det in frame_result["detections"]:
        bbox = det["bbox"]
        x1 = int(bbox["x"])
        y1 = int(bbox["y"])
        x2 = int(bbox["x"] + bbox["w"])
        y2 = int(bbox["y"] + bbox["h"])

        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        label = f"G{det['global_id']} T{det['track_id']} {det.get('zone', '')[:8]}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), (0, 255, 0), -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    h, w = frame.shape[:2]
    overlay = frame.copy()
    panel_w = 380
    panel_h = 180
    cv2.rectangle(overlay, (10, 10), (panel_w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    y_off = 40
    line_h = 32
    cv2.putText(frame, f"Visible Now: {frame_result['current_count']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Unique Hens: {frame_result['unique_count']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 0), 2)
    y_off += line_h
    cv2.putText(frame, f"Total Seen: {frame_result['total_seen']}",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 200, 255), 2)
    y_off += line_h
    zone_text = " | ".join(f"{k}:{v}" for k, v in frame_result["zone_counts"].items() if v > 0)
    if zone_text:
        cv2.putText(frame, f"Zones: {zone_text}",
                    (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    y_off += line_h
    cv2.putText(frame, "q:quit r:reset z:zones",
                (20, y_off), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    cv2.imshow(window_name, frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('r'):
        hen_counter.reset()
        print("Counter reset.")
    elif key == ord('z'):
        show_zones = not show_zones
        print(f"Zones: {'ON' if show_zones else 'OFF'}")

cap.release()
cv2.destroyAllWindows()
print("Processing complete.")
