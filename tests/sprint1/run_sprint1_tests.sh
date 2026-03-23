#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="/opt/conda/envs/sentinel-env/bin/python"
ARTIFACT_DIR="$ROOT_DIR/tests/sprint1/artifacts"

mkdir -p "$ARTIFACT_DIR"

"$PYTHON_BIN" -m unittest -v \
  tests.sprint1.test_contracts \
  tests.sprint1.test_backward_compat | tee "$ARTIFACT_DIR/unittest_sprint1.log"
