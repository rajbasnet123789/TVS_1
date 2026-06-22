import numpy as np
import logging

logger = logging.getLogger(__name__)


class MortalityGrid:
    ACTIVE = 0
    SUSPECT_STATIC = 1
    DEAD_CANDIDATE = 2
    CONFIRMED_DEAD = 3

    def __init__(self, roi_bbox, cell_size=35):
        # roi_bbox: (x1, y1, x2, y2)
        self.roi = roi_bbox
        self.cell_size = cell_size

        w = max(1, roi_bbox[2] - roi_bbox[0])
        h = max(1, roi_bbox[3] - roi_bbox[1])
        self.cols = int(np.ceil(w / cell_size))
        self.rows = int(np.ceil(h / cell_size))

        self.states = np.zeros((self.rows, self.cols), dtype=np.int32)
        self.last_move = np.zeros((self.rows, self.cols))
        self.static_start = np.zeros((self.rows, self.cols))
        self.debounce_counts = np.zeros((self.rows, self.cols), dtype=np.int32)

        # Centroid history per cell: dict of (r, c) -> list of [cx, cy]
        self.centroid_history = {}

        # Default configuration parameters from README
        self.static_threshold_min = 30.0  # 30 mins
        self.movement_threshold_px = 10.0  # 10 px displacement
        self.flush_threshold = 0.7  # 70% cells active
        self.auto_escalation_hours = 3.0  # 3 hours static -> confirmed dead
        self.debounce_frames = 15

    def update(self, detections, timestamp):
        # detections: list of (x1, y1, x2, y2, conf)
        active_cells = set()
        cell_dets = {}

        for det in detections:
            x1, y1, x2, y2, conf = det
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            # Map to ROI relative
            rx = cx - self.roi[0]
            ry = cy - self.roi[1]

            c = int(rx // self.cell_size)
            r = int(ry // self.cell_size)

            if 0 <= r < self.rows and 0 <= c < self.cols:
                active_cells.add((r, c))
                cell_dets.setdefault((r, c), []).append(det)

        changes = []
        for r in range(self.rows):
            for c in range(self.cols):
                is_active = (r, c) in active_cells
                curr_state = self.states[r, c]

                if is_active:
                    moved = True
                    dets = cell_dets[(r, c)]
                    best_det = max(dets, key=lambda d: d[4])
                    bx1, by1, bx2, by2, _ = best_det
                    cx = (bx1 + bx2) / 2
                    cy = (by1 + by2) / 2

                    if (r, c) in self.centroid_history and len(self.centroid_history[(r, c)]) > 0:
                        prev_cx, prev_cy = self.centroid_history[(r, c)][-1]
                        dist = np.sqrt((cx - prev_cx) ** 2 + (cy - prev_cy) ** 2)
                        if dist < self.movement_threshold_px:
                            moved = False

                    if moved:
                        self.last_move[r, c] = timestamp
                        self.debounce_counts[r, c] = 0
                        if curr_state != self.ACTIVE:
                            self.states[r, c] = self.ACTIVE
                            changes.append(((r, c), curr_state, self.ACTIVE))

                        self.centroid_history[(r, c)] = [[cx, cy]]
                    else:
                        self.debounce_counts[r, c] += 1
                        if self.debounce_counts[r, c] >= self.debounce_frames:
                            if curr_state == self.ACTIVE:
                                self.states[r, c] = self.SUSPECT_STATIC
                                self.static_start[r, c] = timestamp
                                changes.append(((r, c), self.ACTIVE, self.SUSPECT_STATIC))

                            self.centroid_history.setdefault((r, c), []).append([cx, cy])
                            if len(self.centroid_history[(r, c)]) > 50:
                                self.centroid_history[(r, c)].pop(0)
                else:
                    self.debounce_counts[r, c] += 1
                    if self.debounce_counts[r, c] >= self.debounce_frames:
                        if curr_state == self.ACTIVE:
                            self.states[r, c] = self.SUSPECT_STATIC
                            self.static_start[r, c] = timestamp
                            changes.append(((r, c), self.ACTIVE, self.SUSPECT_STATIC))

        # Check threshold static duration for promotions
        for r in range(self.rows):
            for c in range(self.cols):
                if self.states[r, c] == self.SUSPECT_STATIC:
                    elapsed = (timestamp - self.static_start[r, c]) / 60.0
                    if elapsed >= self.static_threshold_min:
                        # Aspect ratio stability check: dead birds have near-zero centroid variance
                        variance_ok = True
                        if (r, c) in self.centroid_history and len(self.centroid_history[(r, c)]) > 5:
                            hist = np.array(self.centroid_history[(r, c)])
                            x_var = np.var(hist[:, 0])
                            y_var = np.var(hist[:, 1])
                            if x_var > 1.5 or y_var > 1.5:
                                variance_ok = False

                        if variance_ok:
                            self.states[r, c] = self.DEAD_CANDIDATE
                            changes.append(((r, c), self.SUSPECT_STATIC, self.DEAD_CANDIDATE))

        return changes

    def detect_natural_flush(self):
        total_cells = self.rows * self.cols
        if total_cells == 0:
            return False
        active_count = np.sum(self.states == self.ACTIVE)
        return (active_count / total_cells) >= self.flush_threshold

    def process_flush(self, timestamp):
        changes = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.states[r, c] == self.SUSPECT_STATIC:
                    self.states[r, c] = self.DEAD_CANDIDATE
                    changes.append(((r, c), self.SUSPECT_STATIC, self.DEAD_CANDIDATE))
        return changes

    def confirm_deaths(self, timestamp):
        changes = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.states[r, c] == self.DEAD_CANDIDATE:
                    elapsed = (timestamp - self.static_start[r, c]) / 3600.0
                    if elapsed >= self.auto_escalation_hours:
                        self.states[r, c] = self.CONFIRMED_DEAD
                        changes.append(((r, c), self.DEAD_CANDIDATE, self.CONFIRMED_DEAD))
        return changes

    def get_confirmed_dead_count(self):
        return int(np.sum(self.states == self.CONFIRMED_DEAD))

    def get_candidate_dead_count(self):
        return int(np.sum(self.states == self.DEAD_CANDIDATE))
