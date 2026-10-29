#!/usr/bin/env bash
# Git Bash / POSIX entry point; configuration is parsed as data, never sourced.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${PYTHON:-python}" "$ROOT/tools/port.py" "$@"
