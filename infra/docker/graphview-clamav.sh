#!/bin/sh
set -eu

if [ ! -f /var/lib/clamav/main.cvd ]; then
  cp -a /opt/clamav-seed/. /var/lib/clamav/
fi

freshclam --daemon --foreground --stdout --user=clamav &
freshclam_pid=$!
clamd --foreground --log=/tmp/clamd.log --pid=/tmp/clamd.pid &
clamd_pid=$!

terminate() {
  kill "$clamd_pid" "$freshclam_pid" 2>/dev/null || true
}
trap terminate INT TERM EXIT
wait "$clamd_pid"
