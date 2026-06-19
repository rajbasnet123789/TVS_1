"""
Whole-Body + Face Intruder Detection.

Uses:
- YOLO nano with low threshold for wide detection range
- Body appearance matching (ResNet18) for far persons
- Face matching (InsightFace) for near persons
- Both body + face embeddings stored in gallery
"""

import os
import time
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
from datetime import datetime
from gallery import FaceGallery
from body_embedder import BodyEmbedder

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GALLERY_PATH = os.path.join(SCRIPT_DIR, "known_persons", "embeddings.json")
BODY_GALLERY_PATH = os.path.join(SCRIPT_DIR, "known_persons", "body_embeddings.json")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
DEFAULT_THRESHOLD = 0.40
DEFAULT_STREAM_URL = "http://192.168.1.30:8080/video"
DISPLAY_WIDTH = 640


def log_intruder(score, frame, bbox):
    def _log():
        os.makedirs(LOG_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        lf = os.path.join(LOG_DIR, "intruder_log.json")
        logs = []
        if os.path.exists(lf):
            try:
                with open(lf) as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        logs.append({"timestamp": ts, "score": round(score, 4)})
        with open(lf, "w") as f:
            json.dump(logs, f, indent=2)
        x1, y1 = max(0, int(bbox[0])), max(0, int(bbox[1]))
        x2, y2 = int(bbox[2]), int(bbox[3])
        h, w = frame.shape[:2]
        x2, y2 = min(w, x2), min(h, y2)
        if x2 > x1 and y2 > y1:
            cv2.imwrite(os.path.join(LOG_DIR, "intruder_%s.jpg" % ts), frame[y1:y2, x1:x2])
    threading.Thread(target=_log, daemon=True).start()


class CameraThread(threading.Thread):
    def __init__(self, url):
        super().__init__(daemon=True)
        self.url = url
        self.running = False
        self.frame = None
        self.lock = threading.Lock()

    def run(self):
        import urllib3
        urllib3.disable_warnings()
        cap = cv2.VideoCapture(self.url)
        self.running = True
        while self.running:
            ret, frame = cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.005)
        cap.release()

    def get(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.running = False


class DetectThread(threading.Thread):
    def __init__(self, yolo, face_app, body_emb, camera, face_gallery, body_gallery):
        super().__init__(daemon=True)
        self.yolo = yolo
        self.face_app = face_app
        self.body_emb = body_emb
        self.camera = camera
        self.face_gallery = face_gallery
        self.body_gallery = body_gallery
        self.running = False
        self.lock = threading.Lock()
        self.results = []
        self.display = None
        self.idx = 0
        self.last_log_time = 0

    def run(self):
        self.running = True
        while self.running:
            frame = self.camera.get()
            if frame is None:
                time.sleep(0.005)
                continue

            h, w = frame.shape[:2]
            scale = DISPLAY_WIDTH / w
            display = cv2.resize(frame, (DISPLAY_WIDTH, int(h * scale)))
            self.idx += 1

            results = []

            # YOLO person detection - LOW threshold for wide range
            yolo_results = self.yolo(display, conf=0.15, imgsz=480,
                                      verbose=False, classes=[0])[0]

            if yolo_results.boxes is not None and len(yolo_results.boxes) > 0:
                for box in yolo_results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    yolo_conf = float(box.conf[0])

                    px1 = max(0, int(x1))
                    py1 = max(0, int(y1))
                    px2 = min(DISPLAY_WIDTH, int(x2))
                    py2 = min(display.shape[0], int(y2))
                    ph = py2 - py1
                    pw = px2 - px1

                    if ph < 20 or pw < 10:
                        continue

                    # Extract FULL person crop for body matching
                    person_crop = display[py1:py2, px1:px2]

                    # Body appearance embedding (whole person)
                    body_emb = self.body_emb.extract(person_crop)
                    body_match = None
                    body_score = 0
                    if body_emb is not None:
                        m = self.body_gallery.search(body_emb)
                        if m:
                            body_match, body_score = m

                    # Face detection on upper portion
                    face_y2 = py1 + int(ph * 0.5)
                    face_crop = display[py1:face_y2, px1:px2]
                    face_match = None
                    face_score = 0
                    face_bbox = None

                    if face_crop.size > 0 and face_crop.shape[0] >= 15:
                        faces = self.face_app.get(face_crop)
                        if faces:
                            best = max(faces, key=lambda f: f.det_score)
                            if best.det_score >= 0.25:
                                emb = best.normed_embedding.astype(np.float32)
                                emb = emb / (np.linalg.norm(emb) + 1e-6)
                                m = self.face_gallery.search(emb)
                                if m:
                                    face_match, face_score = m
                                face_bbox = [
                                    px1 + int(best.bbox[0]),
                                    py1 + int(best.bbox[1]),
                                    px1 + int(best.bbox[2]),
                                    py1 + int(best.bbox[3]),
                                ]

                    # Combine: if EITHER body or face matches, it's known
                    is_known = False
                    match_name = None
                    match_score = 0

                    if body_match and face_match:
                        # Both match same person = very confident
                        if body_match == face_match:
                            is_known = True
                            match_name = body_match
                            match_score = (body_score + face_score) / 2
                        else:
                            # Conflicting - take higher score
                            if body_score > face_score:
                                is_known = body_score >= DEFAULT_THRESHOLD
                                match_name = body_match
                                match_score = body_score
                            else:
                                is_known = face_score >= DEFAULT_THRESHOLD
                                match_name = face_match
                                match_score = face_score
                    elif body_match:
                        is_known = body_score >= DEFAULT_THRESHOLD
                        match_name = body_match
                        match_score = body_score
                    elif face_match:
                        is_known = face_score >= DEFAULT_THRESHOLD
                        match_name = face_match
                        match_score = face_score

                    # Display bbox = full person
                    display_bbox = [px1, py1, px2, py2]

                    # Determine match type label
                    if body_match and face_match:
                        match_type = "BODY+FACE"
                    elif body_match:
                        match_type = "BODY"
                    elif face_match:
                        match_type = "FACE"
                    else:
                        match_type = "NONE"

                    results.append({
                        "bbox": display_bbox,
                        "face_bbox": face_bbox,
                        "match_name": match_name if is_known else None,
                        "match_score": match_score,
                        "match_type": match_type,
                        "yolo_conf": yolo_conf,
                        "person_size": ph,
                    })

            # Log intruders
            has_intruder = any(not r["match_name"] for r in results)
            if has_intruder:
                now = time.time()
                if now - self.last_log_time > 15:
                    self.last_log_time = now
                    for r in results:
                        if not r["match_name"]:
                            log_intruder(r["match_score"], display, r["bbox"])

            with self.lock:
                self.results = results
                self.display = display

        self.running = False

    def get(self):
        with self.lock:
            return list(self.results), self.display

    def stop(self):
        self.running = False


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Intruder Detection - Body + Face")
        self.root.geometry("900x650")
        self.root.configure(bg="#1a1a2e")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.camera = None
        self.detect = None
        self.running = False
        self.fps_start = time.time()
        self.frame_count = 0

        self.status_var = tk.StringVar(value="Loading models...")
        self.build_gui()
        self.load_models_async()

    def build_gui(self):
        top = tk.Frame(self.root, bg="#0f3460", height=38)
        top.pack(fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="INTRUDER DETECTION", bg="#0f3460", fg="white",
                 font=("Consolas", 13, "bold")).pack(side=tk.LEFT, padx=10)
        self.status_label = tk.Label(top, textvariable=self.status_var,
                                     bg="#0f3460", fg="#00ff88", font=("Consolas", 10))
        self.status_label.pack(side=tk.RIGHT, padx=10)

        self.video = tk.Label(self.root, bg="black", text="Click START",
                               fg="white", font=("Consolas", 14))
        self.video.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        bot = tk.Frame(self.root, bg="#16213e", height=80)
        bot.pack(fill=tk.X, padx=5, pady=(0, 5))
        bot.pack_propagate(False)

        row = tk.Frame(bot, bg="#16213e")
        row.pack(fill=tk.X, padx=8, pady=3)

        tk.Label(row, text="URL:", bg="#16213e", fg="white",
                 font=("Consolas", 9)).pack(side=tk.LEFT)
        self.url_var = tk.StringVar(value=DEFAULT_STREAM_URL)
        tk.Entry(row, textvariable=self.url_var, font=("Consolas", 9),
                 bg="#0f3460", fg="white", insertbackground="white",
                 width=30).pack(side=tk.LEFT, padx=4)

        self.start_btn = tk.Button(row, text="START", bg="#00b894", fg="white",
                                    font=("Consolas", 9, "bold"), width=7,
                                    command=self.toggle_feed)
        self.start_btn.pack(side=tk.LEFT, padx=4)

        tk.Button(row, text="ENROLL", bg="#0984e3", fg="white",
                  font=("Consolas", 9, "bold"), width=7,
                  command=self.open_enroll_window).pack(side=tk.LEFT, padx=3)

        tk.Button(row, text="LOGS", bg="#6c5ce7", fg="white",
                  font=("Consolas", 9, "bold"), width=5,
                  command=self.open_logs_window).pack(side=tk.LEFT, padx=3)

        tk.Label(row, text="Thresh:", bg="#16213e", fg="white",
                 font=("Consolas", 9)).pack(side=tk.LEFT, padx=(8, 2))
        self.threshold_var = tk.DoubleVar(value=DEFAULT_THRESHOLD)
        tk.Scale(row, from_=0.1, to=1.0, resolution=0.01,
                 variable=self.threshold_var, orient=tk.HORIZONTAL,
                 bg="#16213e", fg="white", highlightthickness=0,
                 troughcolor="#0f3460", length=100,
                 command=self.on_threshold_change).pack(side=tk.LEFT)

        row2 = tk.Frame(bot, bg="#16213e")
        row2.pack(fill=tk.X, padx=8)
        self.info_label = tk.Label(row2, text="FPS: --",
                                    bg="#16213e", fg="#dfe6e9", font=("Consolas", 9))
        self.info_label.pack(side=tk.LEFT)
        self.alert_label = tk.Label(row2, text="IDLE",
                                     bg="#16213e", fg="#00ff88", font=("Consolas", 10, "bold"))
        self.alert_label.pack(side=tk.RIGHT)

    def load_models_async(self):
        def _load():
            try:
                from ultralytics import YOLO
                self.yolo = YOLO("yolov8n.pt")

                from insightface.app import FaceAnalysis
                app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
                app.prepare(ctx_id=0, det_size=(320, 320))
                self.face_app = app

                self.body_emb = BodyEmbedder()
                self.body_emb.load()

                self.face_gallery = FaceGallery(
                    embedding_dim=512, match_threshold=DEFAULT_THRESHOLD)
                self.face_gallery.load(GALLERY_PATH)

                self.body_gallery = FaceGallery(
                    embedding_dim=512, match_threshold=DEFAULT_THRESHOLD)
                self.body_gallery.load(BODY_GALLERY_PATH)

                self.root.after(0, lambda: self.status_var.set("Ready"))
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.root.after(0, lambda: self.status_var.set("Error: %s" % e))
                self.root.after(0, lambda: self.status_label.configure(fg="#ff4444"))
        threading.Thread(target=_load, daemon=True).start()

    def toggle_feed(self):
        if self.running:
            self.stop_feed()
        else:
            self.start_feed()

    def start_feed(self):
        url = self.url_var.get().strip()
        if not hasattr(self, "face_app"):
            messagebox.showwarning("Wait", "Models loading...")
            return

        self.camera = CameraThread(url)
        self.camera.start()
        time.sleep(0.3)

        self.detect = DetectThread(
            self.yolo, self.face_app, self.body_emb, self.camera,
            self.face_gallery, self.body_gallery)
        self.detect.start()

        self.running = True
        self.start_btn.config(text="STOP", bg="#d63031")
        self.fps_start = time.time()
        self.frame_count = 0
        self.loop()

    def stop_feed(self):
        self.running = False
        if self.detect:
            self.detect.stop()
        if self.camera:
            self.camera.stop()
        self.detect = None
        self.camera = None
        self.start_btn.config(text="START", bg="#00b894")
        self.video.config(image="", text="Stopped")
        self.info_label.config(text="FPS: --")
        self.alert_label.config(text="IDLE", fg="#00ff88")

    def loop(self):
        if not self.running:
            return

        results, display = self.detect.get()
        if display is None:
            self.root.after(5, self.loop)
            return

        self.frame_count += 1
        dw = display.shape[1]

        has_intruder = any(not r["match_name"] for r in results)
        bc = (0, 0, 200) if has_intruder else (0, 140, 0)
        bt = "!! INTRUDER !!" if has_intruder else "ALL CLEAR"
        display[0:32, :] = (display[0:32, :] * 0.2 + np.array(bc) * 0.8).astype(np.uint8)
        (tw, _), _ = cv2.getTextSize(bt, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(display, bt, ((dw - tw) // 2, 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        for r in results:
            x1, y1, x2, y2 = [int(v) for v in r["bbox"]]

            if r["match_name"]:
                sc = r["match_score"]
                if sc >= self.face_gallery._threshold + 0.10:
                    color = (0, 200, 0)
                elif sc >= self.face_gallery._threshold:
                    color = (0, 200, 255)
                else:
                    color = (0, 0, 255)
                label = "%s %.2f [%s]" % (r["match_name"], sc, r["match_type"])
            else:
                color = (0, 0, 255)
                label = "INTRUDER [%s]" % r["match_type"]

            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(display, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(display, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

            # Draw face bbox if available
            if r["face_bbox"]:
                fx1, fy1, fx2, fy2 = [int(v) for v in r["face_bbox"]]
                cv2.rectangle(display, (fx1, fy1), (fx2, fy2), (255, 255, 0), 1)

        elapsed = time.time() - self.fps_start
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        known = sum(1 for r in results if r["match_name"])
        intruders = len(results) - known
        self.info_label.config(
            text="FPS: %.0f | Persons: %d | Known: %d | Intruders: %d" %
            (fps, len(results), known, intruders))
        if has_intruder:
            self.alert_label.config(text="!! INTRUDER (%d) !!" % intruders, fg="#ff4444")
        else:
            self.alert_label.config(text="ALL CLEAR", fg="#00ff88")

        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        imgtk = ImageTk.PhotoImage(image=img)
        self.video.imgtk = imgtk
        self.video.config(image=imgtk, text="")

        self.root.after(1, self.loop)

    def open_enroll_window(self):
        if not hasattr(self, "face_app"):
            return
        win = tk.Toplevel(self.root)
        win.title("Enroll Person")
        win.geometry("500x350")
        win.configure(bg="#1a1a2e")

        tk.Label(win, text="Name:", bg="#1a1a2e", fg="white",
                 font=("Consolas", 10)).pack(pady=(10, 3))
        name_var = tk.StringVar()
        tk.Entry(win, textvariable=name_var, font=("Consolas", 10),
                 bg="#0f3460", fg="white", insertbackground="white", width=25).pack()

        selected = []
        files_var = tk.StringVar(value="No files")

        def browse():
            files = filedialog.askopenfilenames(
                filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
            if files:
                selected.clear()
                selected.extend(files)
                files_var.set("%d file(s)" % len(files))

        tk.Button(win, text="Browse", bg="#0984e3", fg="white",
                  font=("Consolas", 9), command=browse).pack(pady=4)
        tk.Label(win, textvariable=files_var, bg="#1a1a2e", fg="#aaa",
                 font=("Consolas", 8)).pack()

        res_var = tk.StringVar()
        res_lbl = tk.Label(win, textvariable=res_var, bg="#1a1a2e", fg="white",
                           font=("Consolas", 9))
        res_lbl.pack(pady=5)

        def enroll():
            name = name_var.get().strip()
            if not name or not selected:
                res_var.set("Fill name + select images")
                res_lbl.configure(fg="#ff4444")
                return

            res_var.set("Enrolling... (%d images)" % len(selected))
            res_lbl.configure(fg="#00ff88")
            win.update()

            def _enroll():
                try:
                    face_embs = []
                    body_embs = []

                    for p in selected:
                        img = cv2.imread(p)
                        if img is None:
                            continue

                        # Face embedding
                        faces = self.face_app.get(img)
                        if faces:
                            best = max(faces, key=lambda f: f.det_score)
                            if best.det_score >= 0.3:
                                emb = best.normed_embedding.astype(np.float32)
                                emb = emb / (np.linalg.norm(emb) + 1e-6)
                                face_embs.append(emb)

                        # Body embedding
                        be = self.body_emb.extract(img)
                        if be is not None:
                            body_embs.append(be)

                    saved = 0
                    if face_embs:
                        avg = np.mean(face_embs, axis=0).astype(np.float32)
                        avg = avg / (np.linalg.norm(avg) + 1e-6)
                        self.face_gallery.add(name, avg, num_images=len(face_embs))
                        self.face_gallery.save(GALLERY_PATH)
                        saved += 1

                    if body_embs:
                        avg = np.mean(body_embs, axis=0).astype(np.float32)
                        avg = avg / (np.linalg.norm(avg) + 1e-6)
                        self.body_gallery.add(name, avg, num_images=len(body_embs))
                        self.body_gallery.save(BODY_GALLERY_PATH)
                        saved += 1

                    if saved == 0:
                        self.root.after(0, lambda: res_var.set("No faces or bodies found"))
                        self.root.after(0, lambda: res_lbl.configure(fg="#ff4444"))
                    else:
                        parts = []
                        if face_embs:
                            parts.append("face:%d" % len(face_embs))
                        if body_embs:
                            parts.append("body:%d" % len(body_embs))
                        msg = "OK: '%s' (%s)" % (name, " ".join(parts))
                        self.root.after(0, lambda: res_var.set(msg))
                        self.root.after(0, lambda: res_lbl.configure(fg="#00ff88"))
                except Exception as e:
                    self.root.after(0, lambda: res_var.set("Error: %s" % e))
                    self.root.after(0, lambda: res_lbl.configure(fg="#ff4444"))

            threading.Thread(target=_enroll, daemon=True).start()

        tk.Button(win, text="ENROLL", bg="#00b894", fg="white",
                  font=("Consolas", 10, "bold"), command=enroll).pack(pady=8)

    def open_logs_window(self):
        win = tk.Toplevel(self.root)
        win.title("Logs")
        win.geometry("500x350")
        win.configure(bg="#1a1a2e")
        lf = os.path.join(LOG_DIR, "intruder_log.json")
        if not os.path.exists(lf):
            tk.Label(win, text="No logs.", bg="#1a1a2e", fg="white").pack(pady=40)
            return
        try:
            with open(lf) as f:
                logs = json.load(f)
        except Exception:
            tk.Label(win, text="Corrupted.", bg="#1a1a2e", fg="#ff4444").pack(pady=40)
            return
        tk.Label(win, text="Events: %d" % len(logs), bg="#1a1a2e", fg="white",
                 font=("Consolas", 10, "bold")).pack(pady=5)
        tw = tk.Text(win, bg="#0f3460", fg="white", font=("Consolas", 8), bd=0)
        tw.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        for e in logs[-40:]:
            tw.insert(tk.END, "%s | score=%s\n" % (e["timestamp"], e["score"]))
        tw.config(state=tk.DISABLED)

    def on_threshold_change(self, val):
        t = float(val)
        if hasattr(self, "face_gallery"):
            self.face_gallery.set_threshold(t)
        if hasattr(self, "body_gallery"):
            self.body_gallery.set_threshold(t)

    def on_close(self):
        self.running = False
        if self.detect:
            self.detect.stop()
        if self.camera:
            self.camera.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
