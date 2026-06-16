"""
GPU/CPU Consumption Report - ALL VIDEO CHANNELS
Config: YOLOv11x + MiewID ReID + BoT-SORT Tracking + GUI
Processes all available MP4 videos from CH_01-CH_06
"""
import os
import sys
import time
import json
import threading
import subprocess
import GPUtil
import psutil
import torch
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class ResourceMonitor:
    def __init__(self, interval=0.3):
        self.interval = interval
        self.gpu_samples = []
        self.cpu_samples = []
        self.ram_samples = []
        self.gpu_mem_samples = []
        self.running = False
        self.thread = None

    def _poll(self):
        while self.running:
            ts = time.time()
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    self.gpu_samples.append({
                        "ts": ts,
                        "load_pct": g.load * 100,
                        "mem_used_mb": g.memoryUsed,
                        "mem_total_mb": g.memoryTotal,
                        "mem_pct": (g.memoryUsed / g.memoryTotal) * 100 if g.memoryTotal else 0,
                        "temp_c": g.temperature,
                    })
                else:
                    self.gpu_samples.append({"ts": ts, "load_pct": 0, "mem_used_mb": 0, "mem_total_mb": 0, "mem_pct": 0, "temp_c": 0})
            except Exception:
                self.gpu_samples.append({"ts": ts, "load_pct": 0, "mem_used_mb": 0, "mem_total_mb": 0, "mem_pct": 0, "temp_c": 0})
            cpu_pct = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            self.cpu_samples.append({"ts": ts, "cpu_pct": cpu_pct})
            self.ram_samples.append({"ts": ts, "ram_used_gb": ram.used / (1024**3), "ram_total_gb": ram.total / (1024**3), "ram_pct": ram.percent})
            if torch.cuda.is_available():
                alloc = torch.cuda.memory_allocated() / (1024**2)
                reserved = torch.cuda.memory_reserved() / (1024**2)
                self.gpu_mem_samples.append({"ts": ts, "cuda_allocated_mb": alloc, "cuda_reserved_mb": reserved})
            else:
                self.gpu_mem_samples.append({"ts": ts, "cuda_allocated_mb": 0, "cuda_reserved_mb": 0})
            time.sleep(self.interval)

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)

    def report(self):
        def stats(values):
            if not values:
                return {"min": 0, "max": 0, "avg": 0, "peak": 0}
            return {"min": round(min(values), 2), "max": round(max(values), 2),
                    "avg": round(sum(values) / len(values), 2), "peak": round(max(values), 2)}
        gpu_load = [s["load_pct"] for s in self.gpu_samples]
        gpu_mem_pct = [s["mem_pct"] for s in self.gpu_samples]
        gpu_mem_mb = [s["mem_used_mb"] for s in self.gpu_samples]
        gpu_temp = [s["temp_c"] for s in self.gpu_samples]
        cpu = [s["cpu_pct"] for s in self.cpu_samples]
        ram_pct = [s["ram_pct"] for s in self.ram_samples]
        ram_gb = [s["ram_used_gb"] for s in self.ram_samples]
        cuda_alloc = [s["cuda_allocated_mb"] for s in self.gpu_mem_samples]
        cuda_res = [s["cuda_reserved_mb"] for s in self.gpu_mem_samples]
        duration = self.gpu_samples[-1]["ts"] - self.gpu_samples[0]["ts"] if len(self.gpu_samples) > 1 else 0
        return {
            "duration_seconds": round(duration, 1),
            "sampling_interval_sec": self.interval,
            "total_samples": len(self.gpu_samples),
            "gpu": {
                "device": "NVIDIA GeForce RTX 3050 Laptop GPU (4 GB)",
                "gpu_utilization_pct": stats(gpu_load),
                "gpu_memory_utilization_pct": stats(gpu_mem_pct),
                "gpu_memory_used_mb": stats(gpu_mem_mb),
                "gpu_temperature_c": stats(gpu_temp),
                "cuda_allocated_mb": stats(cuda_alloc),
                "cuda_reserved_mb": stats(cuda_res),
            },
            "cpu": {"cpu_utilization_pct": stats(cpu)},
            "ram": {"ram_utilization_pct": stats(ram_pct), "ram_used_gb": stats(ram_gb)},
        }


def main():
    print("=" * 70)
    print("  GPU/CPU CONSUMPTION REPORT - ALL VIDEO CHANNELS")
    print("  Config: YOLOv11x + MiewID ReID + BoT-SORT + GUI")
    print("=" * 70)

    yolo11x_path = os.path.join(BASE_DIR, "yolo11x.pt")
    if not os.path.exists(yolo11x_path):
        print(f"[ERROR] YOLOv11x not found: {yolo11x_path}")
        sys.exit(1)

    print("\n[PRE-FLIGHT] System:")
    print(f"  CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA: {torch.version.cuda}")
        props = torch.cuda.get_device_properties(0)
        print(f"  VRAM: {props.total_memory / (1024**2):.0f} MB")
    print(f"  CPU cores: {psutil.cpu_count(logical=True)}")
    ram = psutil.virtual_memory()
    print(f"  RAM: {ram.total / (1024**3):.1f} GB")
    gpus = GPUtil.getGPUs()
    if gpus:
        g = gpus[0]
        print(f"  GPU idle: load={g.load*100:.1f}%  mem={g.memoryUsed:.0f}/{g.memoryTotal:.0f}MB  temp={g.temperature}C")

    print("\n[SCAN] Available videos:")
    ch_videos = {}
    total_frames_all = 0
    for ch_num in [1, 2, 3, 4, 5, 6]:
        ch_dir = os.path.join(BASE_DIR, f"CH_{ch_num:02d}")
        if not os.path.isdir(ch_dir):
            print(f"  CH_{ch_num:02d}: directory not found")
            continue
        mp4s = [f for f in os.listdir(ch_dir) if f.endswith(".mp4")]
        if not mp4s:
            print(f"  CH_{ch_num:02d}: no .mp4 files")
            continue
        vpath = os.path.join(ch_dir, mp4s[0])
        cap = cv2.VideoCapture(vpath)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        duration_sec = total_frames / fps if fps > 0 else 0
        size_mb = os.path.getsize(vpath) / (1024 * 1024)
        ch_videos[f"CH_{ch_num:02d}"] = vpath
        total_frames_all += total_frames
        print(f"  CH_{ch_num:02d}: {mp4s[0]}")
        print(f"           {size_mb:.1f}MB | {w}x{h} | {fps:.0f}fps | {duration_sec:.1f}s | {total_frames} frames")

    if not ch_videos:
        print("[ERROR] No video files found!")
        sys.exit(1)

    print(f"\n  Total videos: {len(ch_videos)} | Total frames across all: {total_frames_all}")

    # Write inner processing script as a file
    inner_script_path = os.path.join(BASE_DIR, "_inner_video_worker.py")

    # We need to write it as a regular file to avoid f-string escaping issues
    videos_json = json.dumps(ch_videos)

    inner_code = r'''
import os, sys, time, cv2, numpy as np, torch
from collections import defaultdict

sys.path.insert(0, r''' + repr(BASE_DIR) + r''')
sys.path.insert(0, os.path.join(r''' + repr(BASE_DIR) + r''', "weight_model"))

from ultralytics import YOLO
from weight_predictor import ChickenWeightPredictor

BASE_DIR = r''' + repr(BASE_DIR) + r'''
YOLO11X_PATH = r''' + repr(yolo11x_path) + r'''
TRACKER_CONFIG = os.path.join(BASE_DIR, "botsort_custom.yaml")
CONF_THRESHOLD = 0.35
MIN_BOX_AREA = 400
MAX_ASPECT_RATIO = 3.0
MAX_DETECT_RES = 1280
FRAME_SKIP = 1
GUI_DELAY_MS = 1
REID_THRESHOLD = 0.35
MIEWID_REPO = "conservationxlabs/miewid-msv3"
MIEWID_DIM = 2152

CAMERAS = VIDEO_PATHS_PLACEHOLDER

class GeM(torch.nn.Module):
    def __init__(self, p=3, eps=1e-6):
        super().__init__()
        self.p = torch.nn.Parameter(torch.ones(1) * p)
        self.eps = eps
    def forward(self, x):
        return torch.nn.functional.avg_pool2d(x.clamp(min=self.eps).pow(self.p), (x.size(-2), x.size(-1))).pow(1./self.p)

class MiewIDExtractor:
    def __init__(self):
        self._backbone = None
        self._bn = None
        self._transform = None
        self._device = "cpu"
        self._loaded = False
        self._dim = MIEWID_DIM

    def load(self):
        self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
        try:
            import timm
            from safetensors.torch import load_file
            from huggingface_hub import hf_hub_download
            from timm.data import resolve_data_config, create_transform
            backbone = timm.create_model("efficientnetv2_rw_m", pretrained=False, num_classes=0)
            backbone.global_pool = GeM()
            bn = torch.nn.BatchNorm1d(MIEWID_DIM)
            weights_path = hf_hub_download(MIEWID_REPO, "model.safetensors")
            weights = load_file(weights_path)
            backbone_state = {k.replace("backbone.", ""): v for k, v in weights.items() if k.startswith("backbone.")}
            backbone.load_state_dict(backbone_state, strict=False)
            bn_state = {k.replace("bn.", ""): v for k, v in weights.items() if k.startswith("bn.")}
            bn.load_state_dict(bn_state)
            self._backbone = backbone.to(self._device).eval()
            self._bn = bn.to(self._device).eval()
            data_config = resolve_data_config(self._backbone.pretrained_cfg)
            self._transform = create_transform(**data_config, is_training=False)
            self._loaded = True
            print(f"[ReID] MiewID loaded on {self._device} (dim={MIEWID_DIM})")
        except Exception as e:
            print(f"[ReID] MiewID load failed: {e}")

    def extract(self, frame, bboxes):
        if not self._loaded or not bboxes:
            return [None] * len(bboxes)
        from PIL import Image
        crops, valid_idx = [], []
        for i, bbox in enumerate(bboxes):
            x1, y1 = max(0, int(bbox["x"])), max(0, int(bbox["y"]))
            x2 = min(frame.shape[1], int(bbox["x"] + bbox["w"]))
            y2 = min(frame.shape[0], int(bbox["y"] + bbox["h"]))
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            pil = Image.fromarray(crop[:, :, ::-1] if crop.shape[2] == 3 else crop)
            crops.append(self._transform(pil).unsqueeze(0))
            valid_idx.append(i)
        if not crops:
            return [None] * len(bboxes)
        try:
            batch = torch.cat(crops, dim=0).to(self._device)
            with torch.no_grad():
                feat = self._backbone(batch)
                feat = feat.view(feat.size(0), -1)
                features = self._bn(feat)
            features = features.cpu().numpy()
            result = [None] * len(bboxes)
            for j, idx in enumerate(valid_idx):
                if j < len(features):
                    emb = features[j].flatten()
                    n = np.linalg.norm(emb)
                    result[idx] = emb / n if n > 0 else emb
            return result
        except Exception:
            return [None] * len(bboxes)


class Gallery:
    def __init__(self, dim=MIEWID_DIM):
        self.dim = dim
        self._emb = {}
        self._meta = {}
        self._next_id = 1
        try:
            import faiss
            self._index = faiss.IndexFlatIP(dim)
            self._map = []
            self._faiss = True
        except ImportError:
            self._index = None
            self._map = []
            self._faiss = False

    def add(self, emb, cam, conf=0.0):
        gid = self._next_id
        self._next_id += 1
        self._emb[gid] = emb.copy()
        self._meta[gid] = {"camera": cam, "conf": conf, "first": time.time(), "last": time.time(), "count": 1}
        if self._faiss:
            self._index.add(emb.reshape(1, -1).astype(np.float32))
        self._map.append(gid)
        return gid

    def search(self, q, k=10, thr=0.35):
        if not self._map:
            return []
        if self._faiss and self._index.ntotal > 0:
            k = min(k, self._index.ntotal)
            dists, idxs = self._index.search(q.reshape(1, -1).astype(np.float32), k)
            return [(self._map[i], float(d)) for d, i in zip(dists[0], idxs[0]) if 0 <= i < len(self._map) and d >= thr]
        return []

    def update(self, gid, emb, cam, conf=0.0):
        if gid not in self._emb:
            return
        a = 0.3
        u = a * emb + (1 - a) * self._emb[gid]
        n = np.linalg.norm(u)
        if n > 0:
            u /= n
        self._emb[gid] = u
        self._meta[gid]["last"] = time.time()
        self._meta[gid]["camera"] = cam
        self._meta[gid]["count"] += 1

    def meta(self, gid):
        return self._meta.get(gid)

    def size(self):
        return len(self._emb)


COLORS = [(0,255,0),(255,0,0),(0,0,255),(255,255,0),(0,255,255),(255,0,255),(128,255,0),(255,128,0)]


def main():
    print("=" * 60)
    print("  MCMT VIDEO - YOLOv11x + MiewID ReID")
    print(f"  Cameras: {len(CAMERAS)}")
    print("=" * 60)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = YOLO(YOLO11X_PATH)
    model.to(device)
    print(f"[YOLO] YOLOv11x loaded on {device}")

    wp = ChickenWeightPredictor(
        model_path=os.path.join(BASE_DIR, "weight_model", "weight_model.ubj"),
        stats_path=os.path.join(BASE_DIR, "weight_model", "norm_stats.json"),
    )

    extractor = MiewIDExtractor()
    extractor.load()
    gallery = Gallery()

    cam_data = {}
    for cam_id, vpath in CAMERAS.items():
        cap = cv2.VideoCapture(vpath)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            total_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cam_data[cam_id] = {
                "cap": cap, "frames": 0, "dets": 0, "ids": set(), "weights": [],
                "total_frames": total_f, "fps": fps,
            }
            print(f"[Cam] {cam_id}: {total_f} frames @ {fps:.0f}fps")
        else:
            print(f"[SKIP] {cam_id}: cannot open")

    if not cam_data:
        print("[ERROR] No cameras")
        return

    window = "MCMT VIDEO - YOLOv11x + MiewID"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window, 1600, 900)

    frame_num = 0
    all_ids = set()
    start = time.time()
    cam_cycle = list(cam_data.keys())
    cam_idx = 0

    while cam_data:
        cam_id = cam_cycle[cam_idx % len(cam_cycle)]
        cam_idx += 1
        if cam_id not in cam_data:
            if all(c not in cam_data for c in cam_cycle):
                break
            continue

        cam = cam_data[cam_id]
        for _ in range(FRAME_SKIP):
            ret = cam["cap"].grab()
            if not ret:
                cam["cap"].release()
                del cam_data[cam_id]
                break
        else:
            ret, frame = cam["cap"].retrieve()
            if not ret:
                cam["cap"].release()
                del cam_data[cam_id]
                continue

            frame_num += 1
            h_f, w_f = frame.shape[:2]
            if max(h_f, w_f) > MAX_DETECT_RES:
                sc = MAX_DETECT_RES / max(h_f, w_f)
                frame = cv2.resize(frame, (int(w_f * sc), int(h_f * sc)))

            results = model.track(
                source=frame, conf=CONF_THRESHOLD, imgsz=1280,
                device=device, verbose=False, tracker=TRACKER_CONFIG, persist=True,
            )[0]

            bboxes_frame = []
            if results.boxes is not None and len(results.boxes) > 0:
                for box in results.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    bw, bh = int(x2 - x1), int(y2 - y1)
                    if bw * bh < MIN_BOX_AREA:
                        continue
                    if max(bw, bh) / max(min(bw, bh), 1) > MAX_ASPECT_RATIO:
                        continue
                    bboxes_frame.append({
                        "x": x1, "y": y1, "w": bw, "h": bh,
                        "conf": float(box.conf[0]),
                        "bbox_orig": (int(x1), int(y1), int(x2), int(y2)),
                    })

            embeddings = extractor.extract(frame, bboxes_frame)
            for det, emb in zip(bboxes_frame, embeddings):
                if emb is not None:
                    matches = gallery.search(emb, k=5, thr=REID_THRESHOLD)
                    best_gid, best_score = None, 0.0
                    for gid, score in matches:
                        if score > best_score:
                            best_score = score
                            best_gid = gid
                    if best_gid is not None:
                        gallery.update(best_gid, emb, cam_id, det["conf"])
                        det["gid"] = best_gid
                    else:
                        det["gid"] = gallery.add(emb, cam_id, det["conf"])
                else:
                    det["gid"] = gallery.add(np.zeros(MIEWID_DIM), cam_id, det["conf"])

                gid = det["gid"]
                cam["dets"] += 1
                cam["ids"].add(gid)
                all_ids.add(gid)
                mask = np.zeros((det["h"], det["w"]), dtype=np.uint8)
                cv2.rectangle(mask, (0, 0), (det["w"] - 1, det["h"] - 1), 255, -1)
                w_kg = wp.predict(mask)
                if w_kg:
                    cam["weights"].append(w_kg)

            cam["frames"] += 1

            for det in bboxes_frame:
                x1, y1, x2, y2 = det["bbox_orig"]
                gid = det.get("gid", 0)
                color = COLORS[gid % len(COLORS)] if gid else (128, 128, 128)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"G{gid} {det['conf']:.2f}"
                cv2.putText(frame, label, (x1, max(y1 - 6, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

            cv2.rectangle(frame, (0, 0), (frame.shape[1], 24), (0, 0, 0), -1)
            cv2.putText(
                frame, f"{cam_id} | Gallery:{gallery.size()} Dets:{cam['dets']} IDs:{len(cam['ids'])}",
                (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2,
            )

            display = cv2.resize(frame, (800, 600))
            cv2.imshow(window, display)
            key = cv2.waitKey(GUI_DELAY_MS) & 0xFF
            if key == ord("q"):
                cam_data.clear()
                break

    elapsed = time.time() - start
    for c in cam_data.values():
        c["cap"].release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 60)
    print("  FINAL RESULTS - YOLOv11x + MiewID VIDEO")
    print("=" * 60)
    print(f"  Total frames processed:  {frame_num}")
    print(f"  Wall clock time:         {elapsed:.2f}s")
    print(f"  Throughput:              {frame_num / elapsed:.2f} FPS")
    print(f"  Gallery size:            {gallery.size()} unique hens")
    print()
    for cid in sorted(cam_data):
        s = cam_data[cid]
        w_arr = np.array(s["weights"]) if s["weights"] else np.array([0])
        print(f"  {cid}: {s['frames']} frames, {s['dets']} dets, {len(s['ids'])} IDs, weight avg={w_arr.mean():.3f}kg")
    print()
    cross = defaultdict(list)
    for gid in all_ids:
        seen = [cid for cid, s in cam_data.items() if gid in s["ids"]]
        if len(seen) > 1:
            cross[len(seen)].append(gid)
    if cross:
        print("  Cross-Camera Matches:")
        for n in sorted(cross, reverse=True):
            print(f"    Seen in {n} cameras: {len(cross[n])} hens")
    print("=" * 60)


if __name__ == "__main__":
    main()
'''

    inner_code = inner_code.replace("VIDEO_PATHS_PLACEHOLDER", videos_json)

    with open(inner_script_path, "w", encoding="utf-8") as f:
        f.write(inner_code)

    # Start monitoring
    monitor = ResourceMonitor(interval=0.3)
    monitor.start()
    print("\n[MONITOR] Resource monitoring started (0.3s interval)")

    print("[RUN] Launching YOLOv11x + MiewID on ALL video channels with GUI...\n")
    t_start = time.time()
    proc = subprocess.Popen(
        [sys.executable, inner_script_path],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    output_lines = []
    for line in proc.stdout:
        print(line, end="")
        output_lines.append(line.strip())

    proc.wait()
    elapsed = time.time() - t_start

    monitor.stop()
    time.sleep(0.5)

    report = monitor.report()
    report["wall_clock_seconds"] = round(elapsed, 1)
    report["process_exit_code"] = proc.returncode
    report["stdout_log"] = output_lines[-40:] if len(output_lines) > 40 else output_lines
    report["videos_processed"] = ch_videos

    try:
        os.remove(inner_script_path)
    except Exception:
        pass

    g = report["gpu"]
    c = report["cpu"]
    r = report["ram"]

    print("\n" + "=" * 70)
    print("  RESOURCE CONSUMPTION REPORT - ALL VIDEO CHANNELS")
    print("=" * 70)
    print(f"  Configuration:     YOLOv11x + MiewID ReID + BoT-SORT + GUI")
    print(f"  Wall clock time:   {report['wall_clock_seconds']}s")
    print(f"  Sampling duration: {report['duration_seconds']}s")
    print(f"  Total samples:     {report['total_samples']}")
    print(f"  Exit code:         {report['process_exit_code']}")
    print()
    print("  -- GPU --")
    print(f"  Device:              {g['device']}")
    print(f"  Utilization:         min={g['gpu_utilization_pct']['min']:.1f}%  avg={g['gpu_utilization_pct']['avg']:.1f}%  max={g['gpu_utilization_pct']['max']:.1f}%  peak={g['gpu_utilization_pct']['peak']:.1f}%")
    print(f"  Memory Used:         min={g['gpu_memory_used_mb']['min']:.1f}MB  avg={g['gpu_memory_used_mb']['avg']:.1f}MB  max={g['gpu_memory_used_mb']['max']:.1f}MB  peak={g['gpu_memory_used_mb']['peak']:.1f}MB")
    print(f"  Memory %:            min={g['gpu_memory_utilization_pct']['min']:.1f}%  avg={g['gpu_memory_utilization_pct']['avg']:.1f}%  max={g['gpu_memory_utilization_pct']['max']:.1f}%")
    print(f"  Temperature:         min={g['gpu_temperature_c']['min']}C  avg={g['gpu_temperature_c']['avg']:.1f}C  max={g['gpu_temperature_c']['max']}C")
    print(f"  CUDA Allocated:      min={g['cuda_allocated_mb']['min']:.1f}MB  avg={g['cuda_allocated_mb']['avg']:.1f}MB  max={g['cuda_allocated_mb']['max']:.1f}MB")
    print(f"  CUDA Reserved:       min={g['cuda_reserved_mb']['min']:.1f}MB  avg={g['cuda_reserved_mb']['avg']:.1f}MB  max={g['cuda_reserved_mb']['max']:.1f}MB")
    print()
    print("  -- CPU --")
    print(f"  Utilization:         min={c['cpu_utilization_pct']['min']:.1f}%  avg={c['cpu_utilization_pct']['avg']:.1f}%  max={c['cpu_utilization_pct']['max']:.1f}%  peak={c['cpu_utilization_pct']['peak']:.1f}%")
    print()
    print("  -- RAM --")
    print(f"  Utilization:         min={r['ram_utilization_pct']['min']:.1f}%  avg={r['ram_utilization_pct']['avg']:.1f}%  max={r['ram_utilization_pct']['max']:.1f}%")
    print(f"  Used:                min={r['ram_used_gb']['min']:.2f}GB  avg={r['ram_used_gb']['avg']:.2f}GB  max={r['ram_used_gb']['max']:.2f}GB")
    print("=" * 70)

    report_path = os.path.join(BASE_DIR, "gpu_cpu_video_consumption_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Full report saved: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
