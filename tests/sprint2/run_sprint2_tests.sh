#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="/opt/conda/envs/sentinel-env/bin/python"
ARTIFACT_DIR="$ROOT_DIR/tests/sprint2/artifacts"

mkdir -p "$ARTIFACT_DIR"

"$PYTHON_BIN" -m unittest -v \
  tests.sprint2.test_manifest_schema \
  tests.sprint2.test_manifest_coverage | tee "$ARTIFACT_DIR/unittest_sprint2.log"
