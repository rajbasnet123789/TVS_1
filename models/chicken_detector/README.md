# Chicken Detector — YOLOv8s

Fine-tuned YOLOv8s model for detecting chickens in farm CCTV images.

## Model Details

- **Architecture**: YOLOv8s (small variant, ~22.5M params)
- **Framework**: Ultralytics YOLO (PyTorch backend)
- **Input**: RGB image (typically 512×512 or native CCTV resolution)
- **Output**: Bounding boxes with confidence scores (class: `chicken`)
- **File**: `best.pt` (~22 MB)

## Training

- **Base model**: `yolov8s.pt` (COCO pretrained)
- **Dataset**: 1,035 farm chicken images
- **Epochs**: 100
- **Image size**: 512
- **Batch**: 2
- **Hardware**: GPU (CUDA)

## Inference Parameters

| Use Case | Confidence | IoU Threshold | Max Detections |
|----------|-----------|---------------|----------------|
| Counting (max recall) | 0.05 | 0.4 | 2000 |
| Clean detection | 0.15 | 0.5 | 2000 |

## Usage

```python
from ultralytics import YOLO

model = YOLO("best.pt")
results = model("image.jpg", conf=0.05, iou=0.4, verbose=False)[0]
boxes = results.boxes  # each has .xyxy, .conf, .cls
print(f"Detected {len(boxes)} chickens")
```

## Performance

- Detects chickens in dense clusters with high recall at `conf=0.05`
- Tested on top-view CCTV frames (1371×768): **1,303 chickens detected** in single frame
- Works across 5 camera channels (CH_01 through CH_06) with ROI filtering
