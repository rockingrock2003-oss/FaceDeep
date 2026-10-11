#!/usr/bin/env bash
set -euo pipefail

# FaceDeep Benchmark Harness Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_ROOT}"

# Generate the tiny local fixture dataset on demand. The generated face images
# are intentionally not tracked by git.
"${PROJECT_ROOT}/.venv/bin/python" -m tools.benchmark.fixtures.generate_fixtures 2>/dev/null || python3 -m tools.benchmark.fixtures.generate_fixtures

# Activate virtualenv if available
if [ -d ".venv" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

exec "${PYTHON_BIN}" -m tools.benchmark.runner "$@"
