#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="/opt/conda/envs/sentinel-env/bin/python"
ARTIFACT_DIR="$ROOT_DIR/tests/sprint0/artifacts"

mkdir -p "$ARTIFACT_DIR"

"$PYTHON_BIN" -m unittest -v tests.sprint0.test_sprint0_smoke | tee "$ARTIFACT_DIR/unittest_sprint0.log"
