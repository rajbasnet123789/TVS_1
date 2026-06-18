"""
Webcam Enrollment Workflow.

Captures multiple face samples from webcam for each person,
averages embeddings for robust representation, and stores
them in the FaceGallery with JSON persistence.

Workflow:
1. Prompt for person name
2. Open webcam with live preview
3. Capture N frames (default 10) with countdown
4. Detect person + extract face embedding per frame
5. Average all valid embeddings and L2-normalize
6. Store in gallery and save to disk
"""

import os
import time
import cv2
import numpy as np
from typing import Optional

from detector import PersonDetector
from embedder import FaceEmbedder
from gallery import FaceGallery


def enroll_person(
    gallery: FaceGallery,
    detector: PersonDetector,
    embedder: FaceEmbedder,
    num_samples: int = 10,
    capture_delay: float = 0.3,
    gallery_path: str = "known_persons/embeddings.json",
) -> bool:
    """
    Enroll a new person via webcam capture.

    Args:
        gallery: FaceGallery to store the person's embedding.
        detector: PersonDetector for YOLOv8-seg person detection.
        embedder: FaceEmbedder for ArcFace embedding extraction.
        num_samples: Number of face samples to capture (default 10).
        capture_delay: Delay between captures in seconds.
        gallery_path: Path to save the gallery JSON.

    Returns:
        True if enrollment succeeded, False otherwise.
    """
    name = input("\nEnter person name to enroll: ").strip()
    if not name:
        print("Invalid name. Aborting enrollment.")
        return False

    if gallery.get_embedding(name) is not None:
        overwrite = input(f"Person '{name}' already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != "y":
            print("Enrollment cancelled.")
            return False
        gallery.remove(name)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Cannot open webcam.")
        return False

    print(f"\nEnrolling '{name}' - capturing {num_samples} samples...")
    print("Look at the camera. Press 'c' to capture manually or wait for auto-capture.")
    print("Press 'q' to abort.\n")

    window_name = f"Enroll: {name}"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    embeddings = []
    captured = 0
    auto_capture = True
    last_capture_time = time.time()

    while captured < num_samples:
        ret, frame = cap.read()
        if not ret:
            print("Error: Cannot read frame from webcam.")
            break

        # Detect persons in frame
        detections = detector.detect(frame)

        # Draw detections on frame
        vis = detector.draw_detections(frame, detections)

        # Status overlay
        h, w = vis.shape[:2]
        overlay = vis.copy()
        cv2.rectangle(overlay, (10, 10), (350, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, vis, 0.4, 0, vis)
        cv2.putText(vis, f"Enrolling: {name}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(vis, f"Captured: {captured}/{num_samples}", (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(vis, "c:capture q:abort a:toggle-auto", (20, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        # Progress bar
        bar_w = int((captured / num_samples) * (w - 40))
        cv2.rectangle(vis, (20, h - 40), (20 + bar_w, h - 20), (0, 255, 0), -1)
        cv2.rectangle(vis, (20, h - 40), (w - 20, h - 20), (255, 255, 255), 1)

        cv2.imshow(window_name, vis)

        # Handle keyboard
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            print("Enrollment aborted by user.")
            break
        elif key == ord("c"):
            auto_capture = False
        elif key == ord("a"):
            auto_capture = not auto_capture
            print(f"Auto-capture: {'ON' if auto_capture else 'OFF'}")

        # Auto-capture logic
        now = time.time()
        should_capture = False
        if auto_capture and (now - last_capture_time) >= capture_delay:
            should_capture = True
        elif not auto_capture and key == ord("c"):
            should_capture = True

        if should_capture and detections:
            # Use the largest person detection (by area)
            best_det = max(detections, key=lambda d: (
                (d.bbox["x2"] - d.bbox["x1"]) * (d.bbox["y2"] - d.bbox["y1"])
            ))

            # Extract face embedding from the person crop
            embedding = embedder.extract(frame, best_det.bbox)

            if embedding is not None:
                embeddings.append(embedding)
                captured += 1
                last_capture_time = time.time()
                print(f"  Sample {captured}/{num_samples} captured "
                      f"(confidence: {best_det.confidence:.2f})")
            else:
                print(f"  No face detected in frame. Try again.")
        elif should_capture and not detections:
            print(f"  No person detected. Move into view.")

    cap.release()
    cv2.destroyAllWindows()

    if not embeddings:
        print(f"Enrollment failed: no valid embeddings captured for '{name}'.")
        return False

    # Average embeddings and normalize
    avg_embedding = FaceEmbedder.average_embeddings(embeddings)
    gallery.add(name, avg_embedding, num_images=len(embeddings))
    gallery.save(gallery_path)

    print(f"\nEnrollment complete for '{name}':")
    print(f"  Valid samples: {len(embeddings)}/{num_samples}")
    print(f"  Gallery size: {gallery.size}")
    print(f"  Saved to: {gallery_path}")

    return True


def enroll_from_folder(
    gallery: FaceGallery,
    embedder: FaceEmbedder,
    folder_path: str,
    name: str = None,
    gallery_path: str = "known_persons/embeddings.json",
) -> bool:
    """
    Enroll a person from a folder of images.

    Args:
        gallery: FaceGallery to store the person's embedding.
        embedder: FaceEmbedder for ArcFace embedding extraction.
        folder_path: Path to folder containing face images.
        name: Person name (if None, uses folder name).
        gallery_path: Path to save the gallery JSON.

    Returns:
        True if enrollment succeeded.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        return False

    if name is None:
        name = os.path.basename(folder_path.rstrip("/\\"))

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if os.path.splitext(f)[1].lower() in image_extensions
    ]

    if not image_files:
        print(f"No images found in {folder_path}")
        return False

    print(f"\nEnrolling '{name}' from {len(image_files)} images...")

    embeddings = []
    for img_path in image_files:
        frame = cv2.imread(img_path)
        if frame is None:
            continue

        embedding = embedder.extract(frame)
        if embedding is not None:
            embeddings.append(embedding)
            print(f"  {os.path.basename(img_path)}: face detected")
        else:
            print(f"  {os.path.basename(img_path)}: no face found")

    if not embeddings:
        print(f"Enrollment failed: no faces found in images for '{name}'.")
        return False

    avg_embedding = FaceEmbedder.average_embeddings(embeddings)
    gallery.add(name, avg_embedding, num_images=len(embeddings))
    gallery.save(gallery_path)

    print(f"\nEnrollment complete for '{name}':")
    print(f"  Valid images: {len(embeddings)}/{len(image_files)}")
    print(f"  Saved to: {gallery_path}")

    return True
