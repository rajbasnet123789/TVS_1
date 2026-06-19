# TVS Chicken Farm — ML Models

This directory contains the trained models used in the chicken detection, counting, and weight estimation pipeline.

## Structure

```
models/
├── README.md                    # This file
├── chicken_detector/            # YOLOv8s — chicken detection & counting
│   ├── best.pt                  # Trained model weights
│   └── README.md                # Model details
├── weight_estimator/            # XGBoost — weight from mask features
│   ├── weight_model.ubj         # Trained XGBoost regressor
│   ├── norm_stats.json          # Feature normalization stats
│   └── README.md                # Model details
└── mortality_grid/              # Rule-based grid mortality detection
    └── README.md                # Algorithm documentation
```

## Quick Reference

| Model | Type | Input | Output | Size |
|-------|------|-------|--------|------|
| Chicken Detector | YOLOv8s (fine-tuned) | Image | Bounding boxes per chicken | ~22 MB |
| Weight Estimator | XGBoost Regressor | 11 mask features | Weight in Kg | ~965 KB |
| Mortality Grid | Rule-based (algorithm) | Detection boxes + timestamp | Dead/suspect cell states | — |

## Integration

- **Chicken counting**: Load `chicken_detector/best.pt` with `ultralytics.YOLO`, use `conf=0.05, iou=0.4`
- **Weight estimation**: Load `weight_estimator/weight_model.ubj` via `xgboost.XGBRegressor`, pass 11 normalized features
- **Mortality detection**: Import `MortalityGrid` from `mortality_grid.py` and call `.update(detections, timestamp)` per frame
