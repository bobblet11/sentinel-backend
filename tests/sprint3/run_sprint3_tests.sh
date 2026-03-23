#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="/opt/conda/envs/sentinel-env/bin/python"
ARTIFACT_DIR="$ROOT_DIR/tests/sprint3/artifacts"

mkdir -p "$ARTIFACT_DIR"

"$PYTHON_BIN" -m unittest -v \
  tests.sprint3.test_env_resolution \
  tests.sprint3.test_compose_volume_mounts | tee "$ARTIFACT_DIR/unittest_sprint3.log"
