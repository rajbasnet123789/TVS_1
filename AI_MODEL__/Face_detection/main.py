"""
Face Detection & Person Recognition System.

Main entry point with two modes:
1. Enrollment: Register known persons via webcam capture
2. Real-time Recognition: Detect and identify persons in webcam feed

Architecture:
- YOLOv8-seg for person detection with instance segmentation
- InsightFace ArcFace-R100 for 512-dim face embeddings
- FAISS IndexFlatIP for cosine similarity search
- EMA embedding updates for identity refinement

Usage:
    python main.py --enroll          # Enroll new persons
    python main.py --run             # Real-time recognition
    python main.py --enroll --run    # Enroll then recognize
    python main.py --list            # List enrolled persons
    python main.py --remove NAME    # Remove a person
    python main.py --threshold 0.5   # Set match threshold
"""

import os
import sys
import argparse
import time
import cv2
import numpy as np

from detector import PersonDetector
from embedder import FaceEmbedder
from gallery import FaceGallery
from enroll import enroll_person


# ==========================================
# Configuration
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GALLERY_PATH = os.path.join(SCRIPT_DIR, "known_persons", "embeddings.json")
YOLO_MODEL = "yolov8x-seg.pt"
INSIGHTFACE_MODEL = "buffalo_l"
DEFAULT_THRESHOLD = 0.45
DEFAULT_NUM_SAMPLES = 10


# ==========================================
# Color Palette
# ==========================================
COLORS = {
    "high": (0, 255, 0),       # Green - high confidence match
    "medium": (0, 200, 255),   # Yellow - medium confidence
    "low": (0, 0, 255),        # Red - unknown / low confidence
    "text_bg": (0, 0, 0),      # Black background for text
    "white": (255, 255, 255),
    "cyan": (255, 255, 0),
}


def get_match_color(score: float, threshold: float) -> tuple:
    """Return color based on match score."""
    if score >= threshold + 0.10:
        return COLORS["high"]
    elif score >= threshold:
        return COLORS["medium"]
    else:
        return COLORS["low"]


# ==========================================
# Model Loading
# ==========================================
def load_models(device: str = None):
    """Load all required models."""
    print("=" * 60)
    print("  Face Detection & Person Recognition System")
    print("=" * 60)

    detector = PersonDetector(
        model_path=YOLO_MODEL,
        confidence=0.5,
        imgsz=640,
        device=device,
    )
    detector.load()

    embedder = FaceEmbedder(
        model_name=INSIGHTFACE_MODEL,
        det_size=(640, 640),
    )
    embedder.load()

    gallery = FaceGallery(
        embedding_dim=FaceEmbedder.EMBEDDING_DIM,
        match_threshold=DEFAULT_THRESHOLD,
    )
    gallery.load(GALLERY_PATH)

    print("=" * 60)
    print(f"  Gallery: {gallery.size} known persons")
    print("=" * 60)

    return detector, embedder, gallery


# ==========================================
# Real-time Recognition
# ==========================================
def run_recognition(
    detector: PersonDetector,
    embedder: FaceEmbedder,
    gallery: FaceGallery,
    webcam_id: int = 0,
):
    """
    Run real-time face detection and person recognition.

    Pipeline per frame:
    1. YOLOv8-seg detect + segment persons
    2. InsightFace extract face embeddings
    3. FAISS gallery search (cosine similarity)
    4. Draw annotated results
    """
    cap = cv2.VideoCapture(webcam_id)
    if not cap.isOpened():
        print("Error: Cannot open webcam.")
        return

    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = 0
    frame_count = 0
    fps_start = time.time()

    window_name = "Face Recognition - Press q:quit e:enroll t:threshold"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    print(f"\nWebcam: {frame_w}x{frame_h}")
    print("Controls: q=quit, e=enroll, t=adjust threshold, l=list persons\n")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1

        # Step 1: Detect and segment persons
        detections = detector.detect(frame)

        # Step 2: Extract face embeddings and search gallery
        results = []
        for det in detections:
            embedding = embedder.extract(frame, det.bbox)

            match_name = None
            match_score = 0.0

            if embedding is not None:
                match = gallery.search(embedding)
                if match:
                    match_name, match_score = match

            results.append({
                "detection": det,
                "embedding": embedding,
                "match_name": match_name,
                "match_score": match_score,
            })

        # Step 3: Draw results
        vis = frame.copy()

        for res in results:
            det = res["detection"]
            b = det.bbox
            x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])

            # Determine color and label
            if res["match_name"]:
                color = get_match_color(res["match_score"], gallery._threshold)
                label = f"{res['match_name']} ({res['match_score']:.2f})"
            else:
                color = COLORS["low"]
                label = "Unknown"

            # Draw mask overlay
            overlay = vis.copy()
            overlay[det.mask] = color
            cv2.addWeighted(overlay, 0.2, vis, 0.8, 0, vis)

            # Draw bounding box
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            # Draw label background
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - th - 10), (x1 + tw + 4, y1), color, -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            # Draw confidence below box
            conf_text = f"det:{det.confidence:.2f}"
            cv2.putText(vis, conf_text, (x1, y2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # Draw info panel
        vis = draw_info_panel(vis, len(detections), gallery.size, fps, gallery._threshold)

        cv2.imshow(window_name, vis)

        # FPS calculation
        if frame_count % 30 == 0:
            elapsed = time.time() - fps_start
            fps = frame_count / elapsed if elapsed > 0 else 0

        # Keyboard controls
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("e"):
            # Pause recognition for enrollment
            cv2.destroyAllWindows()
            enroll_person(gallery, detector, embedder, gallery_path=GALLERY_PATH)
            cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        elif key == ord("t"):
            # Adjust threshold
            try:
                new_thresh = input(f"\nCurrent threshold: {gallery._threshold}. New value: ").strip()
                gallery.set_threshold(float(new_thresh))
            except (ValueError, EOFError):
                print("Invalid threshold.")
        elif key == ord("l"):
            # List enrolled persons
            persons = gallery.list_persons()
            print(f"\n--- Enrolled Persons ({len(persons)}) ---")
            for p in persons:
                print(f"  {p['name']}: images={p['num_images']}, "
                      f"matches={p['match_count']}")
            print()

    cap.release()
    cv2.destroyAllWindows()

    elapsed = time.time() - fps_start
    avg_fps = frame_count / elapsed if elapsed > 0 else 0
    print(f"\nSession: {frame_count} frames, {avg_fps:.1f} FPS")


def draw_info_panel(
    frame: np.ndarray,
    num_persons: int,
    gallery_size: int,
    fps: float,
    threshold: float,
) -> np.ndarray:
    """Draw information overlay panel on frame."""
    h, w = frame.shape[:2]
    overlay = frame.copy()
    panel_w = 380
    panel_h = 160
    cv2.rectangle(overlay, (10, 10), (panel_w, panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    y = 35
    line_h = 25
    cv2.putText(frame, "Face Recognition System", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["cyan"], 2)
    y += line_h
    cv2.putText(frame, f"Persons Detected: {num_persons}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS["white"], 1)
    y += line_h
    cv2.putText(frame, f"Known Persons: {gallery_size}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS["white"], 1)
    y += line_h
    cv2.putText(frame, f"Threshold: {threshold:.2f}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS["white"], 1)
    y += line_h
    cv2.putText(frame, f"FPS: {fps:.1f}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    y += line_h
    cv2.putText(frame, "q:quit e:enroll t:threshold l:list", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    return frame


# ==========================================
# Utility Commands
# ==========================================
def list_persons(gallery: FaceGallery):
    """List all enrolled persons."""
    persons = gallery.list_persons()
    if not persons:
        print("No persons enrolled.")
        return

    print(f"\n{'='*50}")
    print(f" Enrolled Persons ({len(persons)})")
    print(f"{'='*50}")
    for p in persons:
        print(f"  Name: {p['name']}")
        print(f"    Images: {p['num_images']}")
        print(f"    Matches: {p['match_count']}")
        print(f"    Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(p['created_at']))}")
        print(f"    Last seen: {time.strftime('%Y-%m-%d %H:%M', time.localtime(p['last_seen']))}")
        print()
    print(f"{'='*50}")


def remove_person(gallery: FaceGallery, name: str):
    """Remove a person from the gallery."""
    if gallery.remove(name):
        gallery.save(GALLERY_PATH)
        print(f"Removed '{name}' from gallery.")
    else:
        print(f"Person '{name}' not found.")


# ==========================================
# Main Entry Point
# ==========================================
def main():
    parser = argparse.ArgumentParser(
        description="Face Detection & Person Recognition System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --enroll              Enroll new persons via webcam
  python main.py --run                 Run real-time recognition
  python main.py --enroll --run        Enroll then recognize
  python main.py --list                List enrolled persons
  python main.py --remove "John Doe"   Remove a person
  python main.py --threshold 0.5       Set match threshold
  python main.py --webcam 1            Use webcam index 1
        """
    )

    parser.add_argument("--enroll", action="store_true",
                        help="Enter enrollment mode")
    parser.add_argument("--run", action="store_true",
                        help="Run real-time recognition")
    parser.add_argument("--list", action="store_true",
                        help="List all enrolled persons")
    parser.add_argument("--remove", type=str, metavar="NAME",
                        help="Remove a person from gallery")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Match threshold (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("--samples", type=int, default=DEFAULT_NUM_SAMPLES,
                        help=f"Enrollment samples per person (default: {DEFAULT_NUM_SAMPLES})")
    parser.add_argument("--webcam", type=int, default=0,
                        help="Webcam device index (default: 0)")
    parser.add_argument("--device", type=str, default=None,
                        help="Device for YOLO (e.g., 'cpu', 'cuda:0')")

    args = parser.parse_args()

    # Default to --run if no mode specified
    if not args.enroll and not args.run and not args.list and not args.remove:
        args.run = True

    # Load models
    detector, embedder, gallery = load_models(device=args.device)
    gallery.set_threshold(args.threshold)

    # Execute requested mode
    if args.list:
        list_persons(gallery)
    elif args.remove:
        remove_person(gallery, args.remove)
    elif args.enroll:
        while True:
            success = enroll_person(
                gallery, detector, embedder,
                num_samples=args.samples,
                gallery_path=GALLERY_PATH,
            )
            if not success:
                break
            cont = input("\nEnroll another person? (y/n): ").strip().lower()
            if cont != "y":
                break
        if args.run:
            run_recognition(detector, embedder, gallery, webcam_id=args.webcam)
    elif args.run:
        run_recognition(detector, embedder, gallery, webcam_id=args.webcam)


if __name__ == "__main__":
    main()
