# Face Detection & Person Recognition System

Real-time face detection, person segmentation, and identity recognition using YOLOv8-seg + InsightFace ArcFace + FAISS.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        INPUT (Webcam/Image)                      │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              YOLOv8-seg (Person Detection + Segmentation)        │
│  - Detects all persons in frame (COCO class 0)                  │
│  - Produces per-person binary segmentation masks                │
│  - Creates background-removed person crops                      │
│  - Output: List[PersonDetection(bbox, mask, cropped_image)]     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│          InsightFace ArcFace-R100 (Face Embedding)               │
│  - Detects face within each person crop                         │
│  - Extracts 512-dim L2-normalized embedding                     │
│  - Fallback: upper 40% face region if full detection fails      │
│  - Output: np.ndarray (512,) per person                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              FAISS Gallery (Cosine Similarity Search)             │
│  - IndexFlatIP on L2-normalized vectors = cosine similarity     │
│  - Matches query against known persons                          │
│  - EMA updates refine embeddings over time                      │
│  - JSON persistence for cross-session storage                   │
│  - Output: (name, similarity_score) or None                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VISUALIZATION + OUTPUT                        │
│  - Annotated frame with bounding boxes + names + scores         │
│  - Color-coded: Green (high), Yellow (medium), Red (unknown)    │
│  - Info panel with FPS, gallery size, threshold                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Face_detection/
├── main.py              # Entry point - CLI with --enroll, --run, --list, --remove
├── detector.py          # YOLOv8-seg person detection & instance segmentation
├── embedder.py          # InsightFace ArcFace 512-dim face embedding extraction
├── gallery.py           # FAISS IndexFlatIP gallery with JSON persistence
├── enroll.py            # Webcam enrollment workflow (multi-sample capture)
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── known_persons/       # Auto-created directory for stored embeddings
    └── embeddings.json  # Gallery persistence file
```

---

## Module Details

### 1. `detector.py` - Person Detection & Segmentation

**Class:** `PersonDetector`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_path` | `"yolov8x-seg.pt"` | YOLOv8 segmentation model weights |
| `confidence` | `0.5` | Minimum detection confidence |
| `imgsz` | `640` | Input image size for YOLO |
| `device` | `None` | Device (auto-detects CUDA/CPU) |

**Methods:**
- `load()` - Load YOLOv8-seg model
- `detect(frame) -> list[PersonDetection]` - Detect and segment persons
- `draw_detections(frame, detections) -> np.ndarray` - Visualize results

**Dataclass `PersonDetection`:**
```python
@dataclass
class PersonDetection:
    bbox: dict          # {"x1", "y1", "x2", "y2"} in pixels
    confidence: float   # Detection confidence [0, 1]
    mask: np.ndarray    # Binary mask (H, W), dtype=bool
    cropped_image: np.ndarray  # Background-removed person crop
```

**How it works:**
1. Loads YOLOv8x-seg pretrained on COCO (80 classes, class 0 = "person")
2. Runs inference with `classes=[0]` to filter only person detections
3. Extracts `results.masks.data[i]` for per-instance segmentation masks
4. Resizes masks to frame dimensions using bilinear interpolation
5. Applies binary mask to frame → blackens background → produces clean crop
6. Falls back to bounding-box crop if segmentation masks unavailable

---

### 2. `embedder.py` - Face Embedding Extraction

**Class:** `FaceEmbedder`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_name` | `"buffalo_l"` | InsightFace model pack |
| `det_size` | `(640, 640)` | Face detection input size |
| `det_threshold` | `0.5` | Minimum face detection confidence |
| `device_id` | `0` | GPU device ID |

**Methods:**
- `load()` - Load InsightFace ArcFace model
- `extract(frame, bbox=None) -> Optional[np.ndarray]` - Extract 512-dim embedding
- `extract_batch(frame, bboxes) -> list[Optional]` - Batch extraction
- `cosine_similarity(a, b) -> float` - Static cosine similarity
- `average_embeddings(embeddings) -> np.ndarray` - Average + re-normalize

**How it works:**
1. Loads InsightFace `buffalo_l` model (ArcFace-R100 backbone)
2. If bbox provided, crops to person region first
3. Runs InsightFace face detection within the crop
4. Picks face with highest `det_score`
5. Extracts `normed_embedding` (already L2-normalized by InsightFace)
6. Re-normalizes to ensure unit vector
7. **Fallback:** If no face found, tries upper 40% of person bbox (where face typically is)

**Embedding Properties:**
- Dimension: 512
- Normalized: L2 (unit vector)
- Range: [-1, 1] per dimension
- Similarity metric: Cosine (via dot product on normalized vectors)

---

### 3. `gallery.py` - FAISS Gallery with Persistence

**Class:** `FaceGallery`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `embedding_dim` | `512` | Embedding dimensionality |
| `match_threshold` | `0.45` | Minimum cosine similarity for a match |

**Methods:**
- `add(name, embedding, num_images)` - Add/update person in gallery
- `search(embedding) -> Optional[tuple[str, float]]` - Find best match
- `remove(name) -> bool` - Remove person from gallery
- `save(path)` - Serialize gallery to JSON
- `load(path) -> bool` - Load gallery from JSON
- `list_persons() -> list[dict]` - List all enrolled persons
- `get_embedding(name) -> Optional[np.ndarray]` - Get stored embedding
- `set_threshold(threshold)` - Update match threshold
- `size` - Number of enrolled persons

**Dataclass `PersonRecord`:**
```python
@dataclass
class PersonRecord:
    name: str
    embedding: np.ndarray       # 512-dim L2-normalized
    num_images: int             # Samples used during enrollment
    created_at: float           # Unix timestamp
    last_seen: float            # Unix timestamp
    match_count: int            # Times re-identified
```

**How it works:**
- **FAISS IndexFlatIP**: Inner Product on L2-normalized vectors = cosine similarity
- **Search:** Queries top-5 nearest neighbors, returns first above threshold
- **EMA Update:** `updated = 0.3 * new + 0.7 * old` then re-normalize
- **Persistence:** JSON with numpy arrays serialized as nested lists
- **Fallback:** Brute-force numpy dot product if FAISS unavailable
- **Thread-safe:** All mutations wrapped in `threading.Lock`

**JSON Format:**
```json
{
  "dim": 512,
  "threshold": 0.45,
  "persons": {
    "John Doe": {
      "embedding": [0.012, -0.034, ...],
      "num_images": 10,
      "created_at": 1718700000.0,
      "last_seen": 1718700100.0,
      "match_count": 5
    }
  }
}
```

---

### 4. `enroll.py` - Webcam Enrollment

**Function:** `enroll_person(gallery, detector, embedder, num_samples, ...)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_samples` | `10` | Face samples to capture per person |
| `capture_delay` | `0.3` | Seconds between auto-captures |
| `gallery_path` | `"known_persons/embeddings.json"` | Save location |

**Enrollment Workflow:**
1. Prompt for person name via CLI
2. Open webcam (device 0) with live preview
3. Detect persons using YOLOv8-seg in real-time
4. Auto-capture at 0.3s intervals (or manual with 'c' key)
5. For each capture: extract face embedding via ArcFace
6. After N samples: average all embeddings → L2-normalize
7. Store in gallery with EMA if re-enrolling
8. Save gallery to JSON

**Keyboard Controls:**
| Key | Action |
|-----|--------|
| `c` | Manual capture (toggle off auto-capture) |
| `a` | Toggle auto-capture on/off |
| `q` | Abort enrollment |

**Alternative:** `enroll_from_folder()` for batch enrollment from image folder.

---

### 5. `main.py` - Main Entry Point

**CLI Arguments:**
```
python main.py [OPTIONS]

Modes:
  --enroll              Enter enrollment mode (webcam capture)
  --run                 Run real-time recognition (default if no mode)
  --list                List all enrolled persons
  --remove NAME         Remove a person from gallery

Options:
  --threshold FLOAT     Match threshold (default: 0.45)
  --samples INT         Enrollment samples per person (default: 10)
  --webcam INT          Webcam device index (default: 0)
  --device STR          YOLO device (e.g., 'cpu', 'cuda:0')
```

**Real-time Recognition Controls:**
| Key | Action |
|-----|--------|
| `q` | Quit |
| `e` | Pause and enter enrollment mode |
| `t` | Adjust match threshold |
| `l` | List enrolled persons in terminal |

**Color Coding:**
| Color | Score Range | Meaning |
|-------|-------------|---------|
| Green | >= threshold + 0.10 | High confidence match |
| Yellow | >= threshold | Medium confidence match |
| Red | < threshold | Unknown person |

---

## Installation

### Prerequisites
- Python >= 3.11
- Webcam
- (Optional) CUDA-capable GPU for faster inference

### Install Dependencies
```bash
cd Face_detection
pip install -r requirements.txt
```

**Required packages:**
| Package | Version | Purpose |
|---------|---------|---------|
| `insightface` | >= 0.7.3 | ArcFace face embedding model |
| `onnxruntime` | >= 1.16.0 | ONNX model inference backend |
| `ultralytics` | >= 8.4.61 | YOLOv8-seg detection + segmentation |
| `faiss-cpu` | >= 1.8.0 | Fast similarity search |
| `opencv-python` | >= 4.8.0 | Video capture and visualization |
| `numpy` | >= 1.24.0 | Array operations |

### First-time Setup
On first run, InsightFace will automatically download the `buffalo_l` model (~300MB) to `~/.insightface/models/`. YOLOv8x-seg weights (~140MB) will download to the current directory.

---

## Usage Examples

### 1. Enroll a New Person
```bash
python main.py --enroll
```
- Enter name when prompted
- Look at the camera
- System auto-captures 10 face samples
- Embedding is averaged and stored

### 2. Run Real-time Recognition
```bash
python main.py --run
```
- Detects all persons in webcam feed
- Segments each person from background
- Extracts face embeddings
- Searches gallery for matches
- Displays annotated feed with names

### 3. Full Workflow
```bash
# Step 1: Enroll known persons
python main.py --enroll

# Step 2: Run recognition
python main.py --run

# Or combine:
python main.py --enroll --run
```

### 4. Manage Gallery
```bash
# List enrolled persons
python main.py --list

# Remove a person
python main.py --remove "John Doe"

# Adjust threshold (stricter = fewer false matches)
python main.py --run --threshold 0.55
```

### 5. Use Different Webcam
```bash
python main.py --run --webcam 1
```

### 6. Force CPU Mode
```bash
python main.py --run --device cpu
```

---

## Embedding Robustness Techniques

### 1. Multi-Sample Enrollment
- Captures 10 frames per person at different angles
- Averages all valid embeddings into single representation
- Reduces sensitivity to any single bad capture

### 2. L2 Normalization
- All embeddings normalized to unit vectors
- Enables cosine similarity via simple dot product
- Makes matching invariant to embedding magnitude

### 3. EMA (Exponential Moving Average) Updates
```python
updated = 0.3 * new_embedding + 0.7 * stored_embedding
updated = updated / ||updated||  # re-normalize
```
- When a known person is re-identified, their stored embedding is refined
- Gradually improves accuracy over multiple encounters
- Alpha=0.3 balances new observations vs. historical data

### 4. Face Quality Filtering
- InsightFace detection confidence threshold (default: 0.5)
- Skips frames where face is occluded, blurry, or at extreme angle
- Fallback region extraction for challenging poses

### 5. Background Removal via Segmentation
- YOLOv8-seg provides per-person binary masks
- Removes background clutter before face embedding
- Improves embedding quality in complex scenes

### 6. Fallback Face Region
- If InsightFace face detector fails on full person crop
- Automatically tries upper 40% of bounding box (face region)
- Handles cases where person is far from camera

---

## Cosine Similarity Thresholds

The `--threshold` parameter controls matching strictness:

| Threshold | Behavior |
|-----------|----------|
| `0.35` | Loose - more matches, more false positives |
| `0.45` | Default - balanced accuracy |
| `0.55` | Strict - fewer matches, fewer false positives |
| `0.65` | Very strict - only very similar faces match |

**Tuning tips:**
- Start with 0.45 and adjust based on results
- If too many false matches → increase threshold
- If missing known persons → decrease threshold
- Well-lit, front-facing enrollment → can use higher threshold
- Poor lighting, varied angles → use lower threshold

---

## Performance

| Metric | Value |
|--------|-------|
| Detection FPS (GPU) | ~30-40 FPS |
| Detection FPS (CPU) | ~5-10 FPS |
| Embedding extraction | ~5ms per face (GPU) |
| FAISS search | <1ms per query |
| Model sizes | YOLOv8x-seg: ~140MB, buffalo_l: ~300MB |

---

## Troubleshooting

### "No module named 'insightface'"
```bash
pip install insightface onnxruntime
```

### "No module named 'ultralytics'"
```bash
pip install ultralytics
```

### "Cannot open webcam"
- Check if another application is using the webcam
- Try different webcam index: `--webcam 1`
- On Linux, check permissions: `ls -l /dev/video*`

### "No face detected during enrollment"
- Ensure good lighting on face
- Look directly at camera
- Move closer to camera (face should be >100px)
- Check if InsightFace model downloaded correctly

### "Wrong person matched"
- Increase threshold: `--threshold 0.55`
- Re-enroll with more samples: `--enroll --samples 15`
- Ensure enrollment images are well-lit and front-facing

### Low FPS
- Use GPU: ensure CUDA is available
- Reduce input size: edit `imgsz` in detector.py
- Use lighter model: change to `yolov8m-seg.pt` in detector.py

---

## Integration with Existing Codebase

This module follows the same patterns used in the AI_MODEL project:

| Pattern | Source File | Reused In |
|---------|-------------|-----------|
| YOLO segmentation | `research_paper/segmenter.py` | `detector.py` |
| FAISS gallery + EMA | `mcmt_test.py`, `global_id_manager.py` | `gallery.py` |
| Embedding persistence | `hyperspectral_image/hen_identifier.py` | `gallery.py` |
| Transformer ReID extract | `model_config/transformer_reid.py` | `embedder.py` |

---

## File Dependencies

```
main.py
├── detector.py    (PersonDetector)
├── embedder.py    (FaceEmbedder)
├── gallery.py     (FaceGallery)
└── enroll.py      (enroll_person)
                    ├── detector.py
                    ├── embedder.py
                    └── gallery.py
```
