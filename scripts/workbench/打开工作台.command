#!/bin/bash
WORKBENCH_DIRECTORY="$(cd "$(dirname "$0")" && pwd)"
if command -v rtk >/dev/null 2>&1; then
  rtk python3 "$WORKBENCH_DIRECTORY/launch.py" "$@"
else
  python3 "$WORKBENCH_DIRECTORY/launch.py" "$@"
fi
