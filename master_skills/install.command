#!/usr/bin/env bash
# Double-click in Finder (macOS) or run from a terminal to set up this computer.
cd "$(dirname "$0")" || exit 1
./setup.sh "$@"
status=$?
read -r -p "Done (exit $status). Press Enter to close."
exit $status
