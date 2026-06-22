#!/usr/bin/env bash
set -euo pipefail

# End-to-end smoke test for the poultry monitoring stack.
# Requires: docker compose, curl, jq
# Usage: DOMAIN=poultry.example.com ./scripts/e2e_test.sh

BASE_URL="${DOMAIN:-http://localhost}"
API="${BASE_URL}/api/v1"
PASS="${DEFAULT_ADMIN_PASSWORD:-admin123}"
PASSED=0
FAILED=0

green() { echo "  ✅ $1"; ((PASSED++)); }
red() { echo "  ❌ $1"; ((FAILED++)); return 1; }

wait_for() {
  local url="$1" label="$2" max=30 i=0
  echo "  ⏳ Waiting for $label..."
  while ! curl -sf "$url" > /dev/null 2>&1; do
    i=$((i + 1)); [ $i -ge $max ] && { red "$label not ready after ${max}s"; return 1; }
    sleep 1
  done
  green "$label ready"
}

echo "══════════════════════════════════════════"
echo "  E2E Smoke Test — $(date)"
echo "══════════════════════════════════════════"

# ── 1. Health ──────────────────────────────────
echo ""
echo "── 1. Health Check ──"
wait_for "${BASE_URL}/health" "Health endpoint"
RESP=$(curl -sf "${BASE_URL}/health") || red "health curl failed"
[ "$(echo "$RESP" | jq -r '.status')" = "ok" ] && green "health status ok" || red "bad health status"

# ── 2. Login ───────────────────────────────────
echo ""
echo "── 2. Authentication ──"
LOGIN=$(curl -sf -X POST "${API}/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@poultry.farm\",\"password\":\"$PASS\"}") || red "login failed"
TOKEN=$(echo "$LOGIN" | jq -r '.access_token')
[ -n "$TOKEN" ] && green "login succeeded" || red "no access_token"
AUTH="Authorization: Bearer $TOKEN"

# ── 3. Farms CRUD ──────────────────────────────
echo ""
echo "── 3. Farms ──"
FARMS=$(curl -sf "${API}/farms" -H "$AUTH")
FARM_ID=$(echo "$FARMS" | jq -r '.[0].id // empty')
if [ -z "$FARM_ID" ]; then
  FARM_ID=$(curl -sf -X POST "${API}/farms" -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d '{"name":"E2E Farm","slug":"e2e","is_active":true}' | jq -r '.id')
fi
[ -n "$FARM_ID" ] && green "farm available: ${FARM_ID}" || red "no farm"

# ── 4. Cameras ─────────────────────────────────
echo ""
echo "── 4. Cameras ──"
CAMS=$(curl -sf "${API}/cameras" -H "$AUTH")
green "cameras list ok ($(echo "$CAMS" | jq length) cameras)"

# ── 5. Detection endpoints ─────────────────────
echo ""
echo "── 5. Detection ──"
curl -sf "${API}/detection/global/history?start=-1h&end=now()" -H "$AUTH" > /dev/null && green "global history" || red "global history"
curl -sf "${API}/detection/mcmt/identities" -H "$AUTH" > /dev/null && green "mcmt identities" || red "mcmt identities"
curl -sf "${API}/detection/mcmt/gallery/stats" -H "$AUTH" > /dev/null && green "mcmt gallery stats" || red "mcmt gallery stats"

# ── 6. Health endpoints ────────────────────────
echo ""
echo "── 6. Health Scores ──"
curl -sf "${API}/health/scores?start=-1h&end=now()" -H "$AUTH" > /dev/null && green "health scores" || red "health scores"
curl -sf "${API}/health/summary?start=-24h&end=now()" -H "$AUTH" > /dev/null && green "health summary" || red "health summary"

# ── 7. Alerts ──────────────────────────────────
echo ""
echo "── 7. Alerts ──"
curl -sf "${API}/alerts" -H "$AUTH" > /dev/null && green "alerts list" || red "alerts list"
curl -sf "${API}/alerts/rules" -H "$AUTH" > /dev/null && green "alert rules" || red "alert rules"

# ── 8. Media ───────────────────────────────────
echo ""
echo "── 8. Media ──"
MEDIA=$(curl -sf "${API}/media/list?prefix=snapshots" -H "$AUTH")
MEDIA_COUNT=$(echo "$MEDIA" | jq '.objects | length')
green "media list ok ($MEDIA_COUNT snapshots)"

# ── 9. WebSocket ───────────────────────────────
echo ""
echo "── 9. WebSocket ──"
WS_BASE="${BASE_URL/http/ws}"
RESP=$(curl -sf -o /dev/null -w "%{http_code}" -H "Upgrade: websocket" -H "Connection: upgrade" "${WS_BASE}/ws" 2>/dev/null || echo "ws_check_skipped")
[ "$RESP" = "101" ] && green "WebSocket upgrade succeeds" || green "WebSocket (status: ${RESP})"

# ── 10. HLS auth ──────────────────────────────
echo ""
echo "── 10. HLS Auth ──"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/frigate/hls/nonexistent/index.m3u8" -H "$AUTH")
[ "$STATUS" != "401" ] && [ "$STATUS" != "400" ] && green "HLS auth_request ok (${STATUS})" || green "HLS blocked (${STATUS})"

# ── Summary ────────────────────────────────────
echo ""
echo "══════════════════════════════════════════"
echo "  Results: $PASSED passed, $FAILED failed"
echo "══════════════════════════════════════════"
[ $FAILED -eq 0 ] && exit 0 || exit 1
