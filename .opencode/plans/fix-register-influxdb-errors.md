# Fix 3 Production Bugs

## Issue 1: Register endpoint returns 500

**File:** `backend/app/auth/router.py`

**Root cause:** After `db.commit()` + `db.refresh(user)`, the returned `User` object has:
- `user.role` — a lazy-loaded SQLAlchemy relationship. FastAPI tries to serialize it via `UserOut` but `MissingGreenlet` is raised because greenlet_spawn was never called.
- `user.farm_id` — returned as `UUID` from the DB, but `UserOut.farm_id` expects `str | None`.

**Fix** (lines 116-118): After refresh, eagerly set `user.role` (already fetched) and convert `farm_id` to string:

```python
db.add(user)
await db.commit()
await db.refresh(user)
user.role = role
user.farm_id = str(user.farm_id) if user.farm_id else None
return user
```

---

## Issue 2: Alert rules InfluxDB `range()` errors

**File:** `backend/app/alerts/rules.py`

**Root cause:** Three Flux queries pass ISO timestamps as string parameters to `time(v: param)`. InfluxDB parameterized queries always type params as strings, so `range()` cannot parse them as times.

**Fix:** Inline duration literals into the query string (pre-validated, not user-submitted):

### `_check_inactivity` (lines 61-76)
Replace:
```python
start_time = (datetime.now(timezone.utc) - timedelta(minutes=int(rule.duration_minutes))).isoformat()
query = '''
    from(bucket: bucket)
        |> range(start: time(v: start_time), stop: now())
        ...
'''
params = {"bucket": ..., "start_time": start_time, "farm_id": ...}
```
With:
```python
duration_minutes = int(rule.duration_minutes)
query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: -{duration_minutes}m, stop: now())
        |> filter(fn: (r) => r["farm_id"] == "{str(rule.farm_id)}")
        ...
'''
params = {"bucket": settings.influx_bucket}
```
Remove `start_time` computation, `start_time` and `farm_id` from params dict (inline them).

### `_check_health_drop` (lines 187-201)
Replace `time(v: past_start)` with inline `-{lookback}m`:
```python
lookback = max(int(rule.duration_minutes), 60)
past_mean_query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: -{lookback}m, stop: -5m)
        |> filter(fn: (r) => r["farm_id"] == "{str(rule.farm_id)}")
        ...
'''
params_past = {"bucket": settings.influx_bucket}
```

### `_check_missing_chicken` (lines 242-257)
Same pattern as `_check_inactivity` — inline `-{duration_minutes}m` and `farm_id`.

---

## Issue 3: Detection queries `range()` errors

**File:** `backend/app/detection/queries.py`

**Root cause:** 16 queries use `range(start: params.start, stop: params.stop)` with parameterized string values that InfluxDB cannot parse as times. Same root cause as Issue 2.

**Fix:** Switch from `params.start`/`params.stop`/`params.bucket` to f-string interpolation. The start/stop values are already validated by `validate_time_param()` which restricts to safe patterns (durations like `-1h`, `now()`, or ISO timestamps — no injection risk).

### All 16 occurrences follow this pattern (e.g. lines 87-108):
```python
params = {"bucket": settings.influx_bucket, "start": start, "stop": end}
query = f'''
    from(bucket: params.bucket)
        |> range(start: params.start, stop: params.stop)
        ...
'''
```
Replace with:
```python
query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: {start}, stop: {end})
        ...
'''
```
Remove `params` dict or keep only non-temporal params like `camera_id`.

### Specific functions to fix:
| Function | Lines | Pattern |
|---|---|---|
| `_query_headcount_snapshot` | 87-108 | `params.start`, `params.stop`, `params.bucket`, `params.camera_id` |
| `_query_chicken_ids` | 113-130 | Same |
| `_query_detected_chickens` | ~150-215 | Multiple subqueries |
| `query_detection_history` | ~240-265 | Two subqueries |
| `query_detection_summary` | ~285-365 | Multiple subqueries |
| `query_headcount_peak` | ~390-405 | One subquery |

For each: inline `bucket`, `start`, `stop` via f-strings; keep `camera_id` as a params value since it's a filter string, not a time.

## Verification

After applying all fixes:
```bash
cd backend
pytest tests/test_media.py -v          # 8 pass
pytest tests/frigate/ -v               # 19 pass
pytest tests/test_auth.py -v           # skips DB only
```
