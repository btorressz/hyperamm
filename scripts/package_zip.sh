#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
rm -f hyperamm.zip
zip -qr hyperamm.zip hyperamm \
  -x 'hyperamm/.git/*' 'hyperamm/.env' 'hyperamm/**/.venv/*' 'hyperamm/**/node_modules/*' \
     'hyperamm/**/__pycache__/*' 'hyperamm/**/.pytest_cache/*' 'hyperamm/**/node_modules/*' 'hyperamm/frontend/dist/*' \
     'hyperamm/**/.mypy_cache/*' 'hyperamm/**/*.egg-info/*' 'hyperamm/**/*.tsbuildinfo' 'hyperamm/**/build/*'
echo "$ROOT/hyperamm.zip"
