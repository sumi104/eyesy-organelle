#!/bin/bash
# Launch the simulator with the project virtualenv.
#
# Run it from Terminal.app the first time: the microphone prompt is attributed
# to whichever app started python, and only that app can be granted access.

set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$HERE/../../.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "no virtualenv at $PYTHON"
  echo "create one with:"
  echo "  /opt/local/bin/python3.11 -m venv $HERE/../../.venv"
  echo "  $HERE/../../.venv/bin/pip install pygame-ce flask sounddevice numpy psutil"
  exit 1
fi

exec "$PYTHON" "$HERE/sim.py" "$@"
