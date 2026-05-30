#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:0}"
APP_URL="${APP_URL:-http://localhost:8080/tv}"
BROWSER_COMMAND="${BROWSER_COMMAND:-surf}"
BROWSER_ARGS="${BROWSER_ARGS:--F}"

xset -dpms || true
xset s off || true
xset s noblank || true

unclutter -idle 0.5 -root >/dev/null 2>&1 &
openbox-session >/dev/null 2>&1 &
OPENBOX_PID=$!

i=0
while [ "$i" -lt 60 ]; do
  if curl -fsS "$APP_URL" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

"$BROWSER_COMMAND" $BROWSER_ARGS "$APP_URL" &
BROWSER_PID=$!

trap 'kill "$BROWSER_PID" >/dev/null 2>&1 || true; kill "$OPENBOX_PID" >/dev/null 2>&1 || true' INT TERM EXIT
wait "$OPENBOX_PID"
