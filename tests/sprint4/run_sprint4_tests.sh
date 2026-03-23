#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="/opt/conda/envs/sentinel-env/bin/python"
ARTIFACT_DIR="$ROOT_DIR/tests/sprint4/artifacts"

mkdir -p "$ARTIFACT_DIR"

"$PYTHON_BIN" -m unittest -v \
  tests.sprint4.test_manager_cache_hit \
  tests.sprint4.test_manager_cache_miss \
  tests.sprint4.test_manager_locking \
  tests.sprint4.test_manager_corrupt_artifact | tee "$ARTIFACT_DIR/unittest_sprint4.log"
