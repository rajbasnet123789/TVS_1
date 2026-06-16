"""
GPU/CPU Consumption Report Runner for mcmt_images.py
Config: MiewID ReID + YOLOv11x + GUI mode
"""
import os
import sys
import time
import json
import threading
import subprocess
import tempfile
import GPUtil
import psutil
import torch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── GPU/CPU monitoring thread ──────────────────────────────────────
class ResourceMonitor:
    def __init__(self, interval=0.5):
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
            # GPU
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
            # CPU / RAM
            cpu_pct = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory()
            self.cpu_samples.append({"ts": ts, "cpu_pct": cpu_pct})
            self.ram_samples.append({"ts": ts, "ram_used_gb": ram.used / (1024**3), "ram_total_gb": ram.total / (1024**3), "ram_pct": ram.percent})
            # PyTorch CUDA memory
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
            return {"min": min(values), "max": max(values), "avg": sum(values) / len(values), "peak": max(values)}

        gpu_load = [s["load_pct"] for s in self.gpu_samples]
        gpu_mem = [s["mem_pct"] for s in self.gpu_samples]
        gpu_mem_mb = [s["mem_used_mb"] for s in self.gpu_samples]
        gpu_temp = [s["temp_c"] for s in self.gpu_samples]
        cpu = [s["cpu_pct"] for s in self.cpu_samples]
        ram_pct = [s["ram_pct"] for s in self.ram_samples]
        ram_gb = [s["ram_used_gb"] for s in self.ram_samples]
        cuda_alloc = [s["cuda_allocated_mb"] for s in self.gpu_mem_samples]
        cuda_res = [s["cuda_reserved_mb"] for s in self.gpu_mem_samples]

        duration = self.gpu_samples[-1]["ts"] - self.gpu_samples[0]["ts"] if len(self.gpu_samples) > 1 else 0

        report = {
            "duration_seconds": round(duration, 1),
            "sampling_interval_sec": self.interval,
            "total_samples": len(self.gpu_samples),
            "gpu": {
                "device": "NVIDIA GeForce RTX 3050 Laptop GPU (4 GB)",
                "gpu_utilization_pct": stats(gpu_load),
                "gpu_memory_utilization_pct": stats(gpu_mem),
                "gpu_memory_used_mb": stats(gpu_mem_mb),
                "gpu_temperature_c": stats(gpu_temp),
                "cuda_allocated_mb": stats(cuda_alloc),
                "cuda_reserved_mb": stats(cuda_res),
            },
            "cpu": {
                "cpu_utilization_pct": stats(cpu),
            },
            "ram": {
                "ram_utilization_pct": stats(ram_pct),
                "ram_used_gb": stats(ram_gb),
            },
        }
        return report


def build_modified_script(yolo_model_path):
    """Create a temp script that patches mcmt_images to use yolov11x + skip ROI prompt."""
    script = f'''import os, sys, json, time, threading, cv2, numpy as np, torch
from collections import defaultdict

# Suppress ROI prompt by pre-seeding empty input
import builtins
_real_input = builtins.input
_call_count = [0]
def _patched_input(prompt=""):
    _call_count[0] += 1
    # First call is ROI config choice -> return "s" (skip)
    # Second call (if any) is ROI confirm -> return "s"
    return "s"
builtins.input = _patched_input

sys.path.insert(0, r"{BASE_DIR}")
sys.path.insert(0, os.path.join(r"{BASE_DIR}", "weight_model"))

# Now import mcmt_images which will use patched input
import mcmt_images

# Monkey-patch the YOLO model path to use yolov11x
YOLO11X_PATH = r"{yolo_model_path}"
print(f"[PATCH] Using YOLOv11x model: {{YOLO11X_PATH}}")

# Override the YOLO_MODEL_PATH constant
mcmt_images.YOLO_MODEL_PATH = YOLO11X_PATH

# Run main
mcmt_images.main()
'''
    return script


def main():
    print("=" * 70)
    print("  GPU/CPU CONSUMPTION REPORT")
    print("  Config: mcmt_images + MiewID ReID + YOLOv11x + GUI")
    print("=" * 70)

    yolo11x_path = os.path.join(BASE_DIR, "yolo11x.pt")
    if not os.path.exists(yolo11x_path):
        print(f"[ERROR] YOLOv11x model not found at {yolo11x_path}")
        sys.exit(1)

    # Pre-flight GPU info
    print("\n[PRE-FLIGHT] System info:")
    print(f"  PyTorch CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  CUDA device: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA version: {torch.version.cuda}")
        mem = torch.cuda.get_device_properties(0)
        print(f"  GPU total memory: {mem.total_memory / (1024**2):.0f} MB")

    cpu_info = psutil.cpu_count(logical=True)
    ram_info = psutil.virtual_memory()
    print(f"  CPU cores (logical): {cpu_info}")
    print(f"  RAM total: {ram_info.total / (1024**3):.1f} GB")

    gpus = GPUtil.getGPUs()
    if gpus:
        g = gpus[0]
        print(f"  GPU load (idle): {g.load * 100:.1f}%  |  GPU mem: {g.memoryUsed:.0f}/{g.memoryTotal:.0f} MB  |  Temp: {g.temperature}°C")

    # Write temp script
    script_content = build_modified_script(yolo11x_path)
    tmp_script = os.path.join(BASE_DIR, "_monitor_run.py")
    with open(tmp_script, "w", encoding="utf-8") as f:
        f.write(script_content)

    # Start monitoring
    monitor = ResourceMonitor(interval=0.3)
    monitor.start()
    print("\n[MONITOR] Resource monitoring started (0.3s interval)")

    # Run the script
    print("[RUN] Launching mcmt_images.py with YOLOv11x + MiewID ReID + GUI...\n")
    t_start = time.time()
    proc = subprocess.Popen(
        [sys.executable, tmp_script],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Stream stdout
    output_lines = []
    for line in proc.stdout:
        print(line, end="")
        output_lines.append(line.strip())

    proc.wait()
    t_end = time.time()
    elapsed = t_end - t_start

    # Stop monitoring
    monitor.stop()
    time.sleep(0.5)

    # Generate report
    report = monitor.report()
    report["wall_clock_seconds"] = round(elapsed, 1)
    report["process_exit_code"] = proc.returncode
    report["stdout_log"] = output_lines[-30:] if len(output_lines) > 30 else output_lines

    # Clean up temp script
    try:
        os.remove(tmp_script)
    except:
        pass

    # Pretty print report
    print("\n" + "=" * 70)
    print("  RESOURCE CONSUMPTION REPORT")
    print("=" * 70)
    print(f"  Wall clock time:       {report['wall_clock_seconds']}s")
    print(f"  Sampling duration:     {report['duration_seconds']}s")
    print(f"  Total samples:         {report['total_samples']}")
    print(f"  Process exit code:     {report['process_exit_code']}")
    print()
    print("  --- GPU ---")
    g = report["gpu"]
    print(f"  Device:                {g['device']}")
    print(f"  GPU Utilization:       min={g['gpu_utilization_pct']['min']:.1f}%  "
          f"avg={g['gpu_utilization_pct']['avg']:.1f}%  "
          f"max={g['gpu_utilization_pct']['max']:.1f}%  "
          f"peak={g['gpu_utilization_pct']['peak']:.1f}%")
    print(f"  GPU Memory Used:       min={g['gpu_memory_used_mb']['min']:.1f}MB  "
          f"avg={g['gpu_memory_used_mb']['avg']:.1f}MB  "
          f"max={g['gpu_memory_used_mb']['max']:.1f}MB  "
          f"peak={g['gpu_memory_used_mb']['peak']:.1f}MB")
    print(f"  GPU Memory %:          min={g['gpu_memory_utilization_pct']['min']:.1f}%  "
          f"avg={g['gpu_memory_utilization_pct']['avg']:.1f}%  "
          f"max={g['gpu_memory_utilization_pct']['max']:.1f}%")
    print(f"  GPU Temperature:       min={g['gpu_temperature_c']['min']}°C  "
          f"avg={g['gpu_temperature_c']['avg']:.1f}°C  "
          f"max={g['gpu_temperature_c']['max']}°C")
    print(f"  CUDA Allocated:        min={g['cuda_allocated_mb']['min']:.1f}MB  "
          f"avg={g['cuda_allocated_mb']['avg']:.1f}MB  "
          f"max={g['cuda_allocated_mb']['max']:.1f}MB")
    print(f"  CUDA Reserved:         min={g['cuda_reserved_mb']['min']:.1f}MB  "
          f"avg={g['cuda_reserved_mb']['avg']:.1f}MB  "
          f"max={g['cuda_reserved_mb']['max']:.1f}MB")
    print()
    print("  --- CPU ---")
    c = report["cpu"]
    print(f"  CPU Utilization:       min={c['cpu_utilization_pct']['min']:.1f}%  "
          f"avg={c['cpu_utilization_pct']['avg']:.1f}%  "
          f"max={c['cpu_utilization_pct']['max']:.1f}%  "
          f"peak={c['cpu_utilization_pct']['peak']:.1f}%")
    print()
    print("  --- RAM ---")
    r = report["ram"]
    print(f"  RAM Utilization:       min={r['ram_utilization_pct']['min']:.1f}%  "
          f"avg={r['ram_utilization_pct']['avg']:.1f}%  "
          f"max={r['ram_utilization_pct']['max']:.1f}%")
    print(f"  RAM Used:              min={r['ram_used_gb']['min']:.2f}GB  "
          f"avg={r['ram_used_gb']['avg']:.2f}GB  "
          f"max={r['ram_used_gb']['max']:.2f}GB")
    print("=" * 70)

    # Save JSON report
    report_path = os.path.join(BASE_DIR, "gpu_cpu_consumption_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Full report saved: {report_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
