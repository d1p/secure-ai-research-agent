#!/usr/bin/env bash
set -euo pipefail

: "${VNC_PASSWORD:?VNC_PASSWORD is required}"
export TZ="${TZ:-UTC}"
BROWSER_LANG="${BROWSER_LANG:-en-US}"
PROXY_HOST="${PROXY_HOST:-proxy-web}"
PROXY_PORT="${PROXY_PORT:-8888}"
DISPLAY_NUM=:99

mkdir -p /browser-profile/anon /tmp/vnc /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# VNC auth file
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vnc/passwd

# Xvfb
Xvfb "$DISPLAY_NUM" -screen 0 1280x800x24 -nolisten tcp &
sleep 1

# Light WM
DISPLAY="$DISPLAY_NUM" openbox &
sleep 1

# Headed Chrome under Xvfb (CDP bound to loopback only)
DISPLAY="$DISPLAY_NUM" google-chrome \
  --user-data-dir=/browser-profile/anon \
  --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage \
  --remote-debugging-port=9222 \
  --proxy-server="http://${PROXY_HOST}:${PROXY_PORT}" \
  --proxy-bypass-list="<-loopback>" \
  --lang="${BROWSER_LANG}" \
  --window-size=1280,800 --start-maximized \
  --no-sandbox \
  about:blank &
CHROME_PID=$!

# Wait for the Chrome CDP endpoint and resolve the browser WebSocket URL
# (the root ws://127.0.0.1:9222/ is not a valid CDP debugger target).
CDP_WS=""
for _ in $(seq 1 30); do
  CDP_WS="$(curl -sf http://127.0.0.1:9222/json/version 2>/dev/null \
    | grep -o '"webSocketDebuggerUrl": *"[^"]*"' | cut -d'"' -f4 || true)"
  [ -n "$CDP_WS" ] && break
  sleep 1
done
if [ -z "$CDP_WS" ]; then
  echo "FATAL: Chrome CDP endpoint did not become ready" >&2
  exit 1
fi

# x11vnc (RFB auth via password file, loopback only)
x11vnc -display "$DISPLAY_NUM" -forever -shared -rfbauth /tmp/vnc/passwd \
  -rfbport 5900 -listen localhost -xkb &
X11VNC_PID=$!

# noVNC (websockify) on 6080
websockify --web=/usr/share/novnc 0.0.0.0:6080 localhost:5900 &
WEBSOCKIFY_PID=$!

# Playwright MCP over Chrome CDP (vision cap enables scroll via mouse wheel)
playwright-mcp \
  --cdp-endpoint "$CDP_WS" \
  --browser chrome \
  --host 0.0.0.0 \
  --port 8931 \
  --allowed-hosts "*" \
  --caps=vision &
MCP_PID=$!

cleanup() {
  kill "$MCP_PID" "$WEBSOCKIFY_PID" "$X11VNC_PID" "$CHROME_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait -n
