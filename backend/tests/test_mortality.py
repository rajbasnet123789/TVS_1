import pytest
import numpy as np
from app.detection.mortality import MortalityGrid


def test_mortality_grid_initialization():
    grid = MortalityGrid(roi_bbox=(0, 0, 70, 70), cell_size=35)
    assert grid.cols == 2
    assert grid.rows == 2
    assert np.all(grid.states == MortalityGrid.ACTIVE)


def test_mortality_grid_static_transitions():
    grid = MortalityGrid(roi_bbox=(0, 0, 70, 70), cell_size=35)
    grid.debounce_frames = 2
    grid.static_threshold_min = 1.0  # 1 min

    # Cell (0, 0) has detections
    # Cell (1, 1) has NO detections (should become static)
    timestamp = 1700000000.0
    
    # 1. Update first frame
    grid.update([(10, 10, 20, 20, 0.9)], timestamp)
    assert grid.states[0, 0] == MortalityGrid.ACTIVE
    
    # 2. Update second frame (reaches debounce count = 2)
    grid.update([(10, 10, 20, 20, 0.9)], timestamp + 1.0)
    assert grid.states[1, 1] == MortalityGrid.SUSPECT_STATIC
    assert grid.states[0, 0] == MortalityGrid.ACTIVE

    # 3. Simulate static duration elapsed (1.1 minutes later)
    grid.update([(10, 10, 20, 20, 0.9)], timestamp + 70.0)
    assert grid.states[1, 1] == MortalityGrid.DEAD_CANDIDATE


def test_mortality_grid_natural_flush():
    grid = MortalityGrid(roi_bbox=(0, 0, 105, 105), cell_size=35)
    assert grid.cols == 3
    assert grid.rows == 3

    # Manually transition some cells to SUSPECT_STATIC
    grid.states[0, 0] = MortalityGrid.SUSPECT_STATIC
    grid.states[0, 1] = MortalityGrid.SUSPECT_STATIC
    
    # All other 7 cells are ACTIVE (7/9 = 77.7% active, exceeds flush_threshold=0.7)
    assert bool(grid.detect_natural_flush()) is True
    
    # Process flush should promote SUSPECT_STATIC cells immediately
    changes = grid.process_flush(timestamp=1700000000.0)
    assert len(changes) == 2
    assert grid.states[0, 0] == MortalityGrid.DEAD_CANDIDATE
    assert grid.states[0, 1] == MortalityGrid.DEAD_CANDIDATE


def test_mortality_grid_confirm_death():
    grid = MortalityGrid(roi_bbox=(0, 0, 70, 70), cell_size=35)
    grid.auto_escalation_hours = 2.0  # 2 hours

    grid.states[0, 0] = MortalityGrid.DEAD_CANDIDATE
    grid.static_start[0, 0] = 1700000000.0

    # Cooldown elapsed (2.1 hours later)
    changes = grid.confirm_deaths(1700000000.0 + 2.1 * 3600.0)
    assert len(changes) == 1
    assert grid.states[0, 0] == MortalityGrid.CONFIRMED_DEAD
    assert grid.get_confirmed_dead_count() == 1
