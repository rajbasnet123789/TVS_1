"""
Streamlit Face Recognition App - Intruder Detection System.

Upload images of known people, then run real-time face detection
and recognition on an IP camera feed.

If a detected face matches the DB -> "NO INTRUDER" (safe)
If a detected face does NOT match  -> "INTRUDER WARNING"
"""

import os
import time
import json
import cv2
import numpy as np
import streamlit as st
from datetime import datetime

from detector import PersonDetector
from embedder import FaceEmbedder
from gallery import FaceGallery

# ==========================================
# Configuration
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GALLERY_PATH = os.path.join(SCRIPT_DIR, "known_persons", "embeddings.json")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
YOLO_MODEL = "yolov8x-seg.pt"
INSIGHTFACE_MODEL = "buffalo_l"
DEFAULT_THRESHOLD = 0.45

COLORS = {
    "safe": (0, 200, 0),
    "warning": (0, 0, 255),
    "medium": (0, 200, 255),
    "white": (255, 255, 255),
    "cyan": (255, 255, 0),
    "black": (0, 0, 0),
}


def get_match_color(score: float, threshold: float) -> tuple:
    if score >= threshold + 0.10:
        return COLORS["safe"]
    elif score >= threshold:
        return COLORS["medium"]
    else:
        return COLORS["warning"]


def log_intruder(person_name: str, score: float, frame: np.ndarray):
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, "intruder_log.json")

    entry = {
        "timestamp": timestamp,
        "name": person_name,
        "score": round(score, 4),
        "is_known": person_name != "INTRUDER",
    }

    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except (json.JSONDecodeError, ValueError):
            logs = []

    logs.append(entry)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

    if person_name == "INTRUDER":
        img_path = os.path.join(LOG_DIR, f"intruder_{timestamp}.jpg")
        cv2.imwrite(img_path, frame)


@st.cache_resource
def load_detector():
    detector = PersonDetector(
        model_path=YOLO_MODEL,
        confidence=0.5,
        imgsz=640,
    )
    detector.load()
    return detector


@st.cache_resource
def load_embedder():
    embedder = FaceEmbedder(
        model_name=INSIGHTFACE_MODEL,
        det_size=(640, 640),
    )
    embedder.load()
    return embedder


@st.cache_resource
def load_gallery():
    gallery = FaceGallery(
        embedding_dim=FaceEmbedder.EMBEDDING_DIM,
        match_threshold=DEFAULT_THRESHOLD,
    )
    gallery.load(GALLERY_PATH)
    return gallery


def draw_detection_overlay(frame, results, gallery):
    vis = frame.copy()
    has_intruder = False
    known_names = []

    for res in results:
        det = res["detection"]
        b = det.bbox
        x1, y1, x2, y2 = int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])

        if res["match_name"]:
            color = get_match_color(res["match_score"], gallery._threshold)
            label = f"{res['match_name']} ({res['match_score']:.2f})"
            known_names.append(res["match_name"])
        else:
            color = COLORS["warning"]
            label = "INTRUDER"
            has_intruder = True

        overlay = vis.copy()
        overlay[det.mask] = color
        cv2.addWeighted(overlay, 0.25, vis, 0.75, 0, vis)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 3)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(vis, (x1, y1 - th - 12), (x1 + tw + 6, y1), color, -1)
        cv2.putText(vis, label, (x1 + 3, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLORS["black"], 2)

        conf_text = f"det:{det.confidence:.2f}"
        cv2.putText(vis, conf_text, (x1, y2 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    return vis, has_intruder, known_names


def draw_status_banner(frame, has_intruder, num_persons, known_names):
    h, w = frame.shape[:2]

    if has_intruder:
        banner_color = (0, 0, 200)
        banner_text = "!! INTRUDER WARNING !!"
    else:
        banner_color = (0, 160, 0)
        banner_text = "NO INTRUDER - ALL CLEAR"

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 50), banner_color, -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    (tw, th), _ = cv2.getTextSize(banner_text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
    tx = (w - tw) // 2
    cv2.putText(frame, banner_text, (tx, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)

    panel_y = 70
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (10, panel_y), (400, panel_y + 140), COLORS["black"], -1)
    cv2.addWeighted(overlay2, 0.6, frame, 0.4, 0, frame)

    y = panel_y + 25
    line_h = 25
    cv2.putText(frame, "Intruder Detection System", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLORS["cyan"], 2)
    y += line_h
    cv2.putText(frame, f"Persons Detected: {num_persons}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS["white"], 1)
    y += line_h
    if known_names:
        cv2.putText(frame, f"Known: {', '.join(known_names)}", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS["safe"], 1)
    else:
        cv2.putText(frame, "Known: None", (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)
    y += line_h
    intruder_count = num_persons - len(known_names)
    cv2.putText(frame, f"Intruders: {intruder_count}", (20, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                COLORS["warning"] if intruder_count > 0 else COLORS["safe"], 1)

    return frame


def process_frame(frame, detector, embedder, gallery):
    detections = detector.detect(frame)
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

    vis, has_intruder, known_names = draw_detection_overlay(frame, results, gallery)
    vis = draw_status_banner(vis, has_intruder, len(results), known_names)

    return vis, results, has_intruder


def get_stream_url(ip, port):
    return f"http://{ip}:{port}/video"


def main():
    st.set_page_config(
        page_title="Intruder Detection System",
        page_icon=":shield:",
        layout="wide",
    )

    st.title("Intruder Detection System")
    st.markdown(
        "**Embedding Robustness:** ArcFace-R100 (512-dim) + FAISS cosine similarity. "
        "Upload multiple images per person for EMA-averaged embeddings robust to lighting, angle, and expression."
    )

    with st.spinner("Loading AI models..."):
        detector = load_detector()
        embedder = load_embedder()
        gallery = load_gallery()

    # ---- Sidebar: Enrollment ----
    with st.sidebar:
        st.header("Enroll Known Persons")

        person_name = st.text_input("Person Name", placeholder="e.g. John Doe")
        uploaded_images = st.file_uploader(
            "Upload face images (multiple for better accuracy)",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
            accept_multiple_files=True,
        )

        if st.button("Enroll Person", use_container_width=True):
            if not person_name.strip():
                st.error("Please enter a name.")
            elif not uploaded_images:
                st.error("Please upload at least one image.")
            else:
                embeddings = []
                progress = st.progress(0, text="Processing images...")
                for i, img_file in enumerate(uploaded_images):
                    img_bytes = img_file.read()
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        emb = embedder.extract(frame)
                        if emb is not None:
                            embeddings.append(emb)
                    progress.progress(
                        (i + 1) / len(uploaded_images),
                        text=f"Processing {i + 1}/{len(uploaded_images)}...",
                    )

                if embeddings:
                    avg_emb = FaceEmbedder.average_embeddings(embeddings)
                    gallery.add(person_name.strip(), avg_emb, num_images=len(embeddings))
                    gallery.save(GALLERY_PATH)
                    st.success(f"Enrolled '{person_name.strip()}' with {len(embeddings)} images")
                else:
                    st.error("No faces detected in any uploaded images.")

        st.divider()

        st.subheader("Enrolled Persons")
        persons = gallery.list_persons()
        if persons:
            for p in persons:
                with st.expander(f"{p['name']} ({p['num_images']} images)"):
                    st.write(f"Created: {time.strftime('%Y-%m-%d %H:%M', time.localtime(p['created_at']))}")
                    st.write(f"Last seen: {time.strftime('%Y-%m-%d %H:%M', time.localtime(p['last_seen']))}")
                    st.write(f"Matches: {p['match_count']}")
                    if st.button(f"Remove {p['name']}", key=f"rm_{p['name']}"):
                        gallery.remove(p["name"])
                        gallery.save(GALLERY_PATH)
                        st.rerun()
        else:
            st.warning("No persons enrolled - everyone flagged as INTRUDER.")

        st.divider()
        threshold = st.slider("Match Threshold", 0.1, 1.0, gallery._threshold, 0.05)
        gallery.set_threshold(threshold)

        st.divider()
        st.subheader("Logs")
        log_file = os.path.join(LOG_DIR, "intruder_log.json")
        if os.path.exists(log_file):
            try:
                with open(log_file, "r") as f:
                    logs = json.load(f)
                st.write(f"Total events: {len(logs)}")
                intruders = [l for l in logs if not l.get("is_known", True)]
                st.write(f"Intruder alerts: {len(intruders)}")
                if st.button("View Recent Logs"):
                    for entry in logs[-10:]:
                        icon = "OK" if entry.get("is_known", True) else "!!"
                        st.text(f"{icon} {entry['timestamp']} | {entry['name']} | score:{entry['score']}")
            except (json.JSONDecodeError, ValueError):
                st.info("Corrupted log file.")
        else:
            st.info("No logs yet.")

    # ---- Main: Camera Feed ----
    st.header("IP Camera Feed")

    col1, col2 = st.columns([3, 1])
    with col2:
        camera_ip = st.text_input("Camera IP", value="192.168.1.30")
        camera_port = st.text_input("Camera Port", value="8080")
        stream_url = get_stream_url(camera_ip, camera_port)
        st.code(stream_url, language=None)

        run_recognition = st.checkbox("Run Recognition", value=False)

    frame_placeholder = st.empty()
    alert_placeholder = st.empty()
    status_placeholder = st.empty()

    if run_recognition:
        # Store video capture in session state to persist across reruns
        if "cap" not in st.session_state or st.session_state.get("stream_url") != stream_url:
            if "cap" in st.session_state and st.session_state.cap is not None:
                st.session_state.cap.release()
            st.session_state.cap = cv2.VideoCapture(stream_url)
            st.session_state.stream_url = stream_url
            st.session_state.frame_count = 0
            st.session_state.fps_start = time.time()
            st.session_state.intruder_streak = 0

        cap = st.session_state.cap

        if not cap.isOpened():
            st.error(f"Cannot connect to camera at {stream_url}")
            st.info("Make sure the camera is accessible and the URL is correct.")
            return

        ret, frame = cap.read()
        if not ret:
            st.warning("Failed to read frame from camera.")
            return

        st.session_state.frame_count += 1
        frame_count = st.session_state.frame_count

        vis, results, has_intruder = process_frame(frame, detector, embedder, gallery)

        # Log intruder
        if has_intruder:
            st.session_state.intruder_streak += 1
            if st.session_state.intruder_streak % 30 == 0:
                for r in results:
                    if not r["match_name"]:
                        log_intruder("INTRUDER", r["match_score"], frame)
        else:
            st.session_state.intruder_streak = 0

        vis_rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
        frame_placeholder.image(vis_rgb, channels="RGB", use_container_width=True)

        if has_intruder:
            alert_placeholder.error("INTRUDER DETECTED - Security alert!")
        else:
            alert_placeholder.success("All clear - All persons are known.")

        names = [r["match_name"] for r in results if r["match_name"]]
        unknown_count = sum(1 for r in results if not r["match_name"])
        status_text = f"Detected: {len(results)} persons"
        if names:
            status_text += f" | Known: {', '.join(names)}"
        if unknown_count:
            status_text += f" | INTRUDERS: {unknown_count}"

        elapsed = time.time() - st.session_state.fps_start
        fps = frame_count / elapsed if elapsed > 0 else 0
        status_text += f" | FPS: {fps:.1f}"
        status_placeholder.caption(status_text)

        # Trigger rerun for next frame
        time.sleep(0.03)
        st.rerun()

    else:
        # Release camera when unchecked
        if "cap" in st.session_state and st.session_state.cap is not None:
            st.session_state.cap.release()
            del st.session_state.cap
        st.info("Enable 'Run Recognition' to start the intruder detection feed.")


if __name__ == "__main__":
    main()
