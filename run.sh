#!/bin/bash
# 用法：./run.sh sweep | ./run.sh sweep --k 1 | ./run.sh smoke
set -euo pipefail
H2=~/src/harness2
PROJ="$(cd "$(dirname "$0")" && pwd)"
export OPENCODE_CONFIG="$PROJ/bse/oc.config.json"
export PATH="$H2/dependencies/tools/node_modules/.bin:$PATH"
export PYTHONPATH="$PROJ"
# 可换模型：BSE_MODEL=magpie/xxx ./run.sh sweep（须 provider 前缀，且在 oc.config.json 声明）
CMD="${1:-sweep}"; shift || true
case "$CMD" in
  smoke) cd "$H2" && .venv/bin/python -m bse.run --dry-run "$@" ;;
  sweep) cd "$H2" && .venv/bin/python -m bse.run --modes agg --only-tasks 920029 "$@" ;;
  *) echo "usage: $0 sweep|smoke [args]"; exit 2 ;;
esac
