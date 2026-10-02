#!/usr/bin/env bash
set -euo pipefail

: "${VNC_PASSWORD:?VNC_PASSWORD is required}"
export TZ="${TZ:-UTC}"
BROWSER_LANG="${BROWSER_LANG:-en-US}"
DISPLAY_NUM=:99
export DISPLAY="$DISPLAY_NUM"

mkdir -p /browser-profile/anon /tmp/vnc /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
# Clear stale Chrome singleton lock (not user data) left by a prior run.
rm -f /browser-profile/anon/SingletonLock /browser-profile/anon/SingletonCookie /browser-profile/anon/SingletonSocket

# VNC auth file
x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vnc/passwd

# Xvfb
Xvfb "$DISPLAY_NUM" -screen 0 1280x800x24 -nolisten tcp &
sleep 1

# Light WM
DISPLAY="$DISPLAY_NUM" openbox &
sleep 1

# x11vnc (RFB auth via password file, loopback only)
x11vnc -display "$DISPLAY_NUM" -forever -shared -rfbauth /tmp/vnc/passwd \
  -rfbport 5900 -listen localhost -xkb &
X11VNC_PID=$!

# noVNC (websockify) on 6080
websockify --web=/usr/share/novnc 0.0.0.0:6080 localhost:5900 &
WEBSOCKIFY_PID=$!

# Stagehand service launches its own Chrome (with the Stagehand extension
# pre-loaded) under Xvfb, drives it via act/observe/extract, and exposes an
# HTTP API on :8931 for the gateway.
export CHROME_PATH="/usr/bin/google-chrome-stable"
export STAGEHAND_PORT="8931"
node /app/stagehand-server.mjs &
STAGEHAND_PID=$!

cleanup() {
  kill "$STAGEHAND_PID" "$WEBSOCKIFY_PID" "$X11VNC_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait -n
