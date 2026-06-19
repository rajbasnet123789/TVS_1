# Weight Estimator — XGBoost Regressor

Predicts chicken weight (in Kg) from binary mask features derived from the detected chicken bounding box.

## Model Details

- **Architecture**: XGBoost XGBRegressor
- **Framework**: XGBoost (xgboost Python package)
- **Input**: 11 normalized features extracted from chicken binary mask
- **Output**: Predicted weight in Kg (float)
- **File**: `weight_model.ubj` (~965 KB)
- **Companion**: `norm_stats.json` — min-max normalization statistics for the 11 features

## Features (11)

| # | Feature | Description |
|---|---------|-------------|
| 1 | area | Number of mask pixels |
| 2 | perimeter | Length of mask boundary |
| 3 | rmin | Minimum Feret diameter |
| 4 | rmax | Maximum Feret diameter |
| 5 | convex_area | Area of convex hull |
| 6 | rect_area | Area of bounding rectangle |
| 7 | solidity | area / convex_area |
| 8 | extent | area / rect_area |
| 9 | circularity | 4π × area / perimeter² |
| 10 | aspect_ratio | rmax / rmin |
| 11 | equiv_diameter | √(4 × area / π) |

## Training

- **Algorithm**: XGBoost with 500 trees, max_depth=5, learning_rate=0.05
- **Mask source**: Mask R-CNN or YOLO bounding-box derived masks
- **Status**: ⚠️ Needs retraining — currently outputs near-constant ~2.38 Kg

## Usage

```python
import xgboost as xgb
import json
import numpy as np

model = xgb.XGBRegressor()
model.load_model("weight_model.ubj")

with open("norm_stats.json") as f:
    stats = json.load(f)

# Extract 11 features from a chicken mask, then normalize:
features = np.array([area, perimeter, rmin, rmax, convex_area, rect_area,
                     solidity, extent, circularity, aspect_ratio, equiv_diameter])
features_norm = (features - stats["min"]) / (stats["max"] - stats["min"] + 1e-8)

weight = model.predict(features_norm.reshape(1, -1))[0]
print(f"Predicted weight: {weight:.3f} Kg")
```

## Notes

- The normalization statistics in `norm_stats.json` contain `min` and `max` arrays (11 values each) used for min-max scaling
- Add a small epsilon (1e-8) to avoid division by zero when min == max
