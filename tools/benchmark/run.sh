#!/usr/bin/env bash
set -euo pipefail

# FaceDeep Benchmark Harness Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

# Activate virtualenv if available
if [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

exec "${PYTHON_BIN}" -m tools.benchmark.runner "$@"
