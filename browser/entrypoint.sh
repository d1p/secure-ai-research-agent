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

# x11vnc (RFB auth via password file, loopback only)
x11vnc -display "$DISPLAY_NUM" -forever -shared -rfbauth /tmp/vnc/passwd \
  -rfbport 5900 -listen localhost -xkb &
X11VNC_PID=$!

# noVNC (websockify) on 6080
websockify --web=/usr/share/novnc 0.0.0.0:6080 localhost:5900 &
WEBSOCKIFY_PID=$!

# Playwright MCP over Chrome CDP (vision cap enables scroll via mouse wheel)
mcp-server-playwright \
  --cdp-endpoint ws://127.0.0.1:9222 \
  --browser chrome \
  --host 0.0.0.0 \
  --port 8931 \
  --caps=vision &
MCP_PID=$!

cleanup() {
  kill "$MCP_PID" "$WEBSOCKIFY_PID" "$X11VNC_PID" "$CHROME_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait -n
