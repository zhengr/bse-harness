#!/bin/bash
# bse-harness 一键环境（2026 Intel Mac / Ivy Bridge 实测路径）
# 产物布局：~/src/harness2（上游 harness2 + opencode + bun），本项目只含 BSE 适配层
set -euo pipefail

H2=~/src/harness2
PROJ="$(cd "$(dirname "$0")" && pwd)"

# 1) harness2 源码 + venv（uv 自带；需要 python3.12，pyenv 缺则 uv 会自动拉）
if [ ! -d "$H2" ]; then
  git clone https://github.com/google-research/harness2 "$H2"
fi
cd "$H2"
[ -x .venv/bin/python ] || uv venv --python 3.12
uv pip install -e '.[render]'

# 2) bun 1.4.4 baseline（Ivy Bridge 机器 1.3.x 全变体 SIGILL；npm postinstall 也装不上，手动解包）
mkdir -p dependencies/tools/bun-bin dependencies/tools/node_modules/.bin
if [ ! -x dependencies/tools/bun-bin/bun ]; then
  npm pack @oven/bun-darwin-x64-baseline@1.4.4
  tar -xzf oven-bun*.tgz -C dependencies/tools/bun-bin --strip-components=1
  rm -f oven-bun-*.tgz
fi
ln -sf ../bun-bin/bun dependencies/tools/node_modules/.bin/bun

# 3) opencode substrate（用 harness2 自带 install 模块，绕开会拉 JobBench 数据集的 harness2-setup）
export PATH="$H2/dependencies/tools/node_modules/.bin:$PATH"
.venv/bin/python - <<'PY'
from harness2 import config
from harness2.dependencies import install
install.opencode(config.DEPENDENCIES, config.OPENCODE_DIR)  # clone + 打 opencode-compat.diff
PY
cd dependencies/opencode && bun install --frozen-lockfile --ignore-scripts && cd "$H2"

# 4) 冒烟（应打印版本号）
"$H2/dependencies/tools/bun-bin/bun" run --cwd "$H2/dependencies/opencode/packages/opencode" \
  --conditions=browser src/index.ts --version < /dev/null

echo "== 环境就绪。跑法见 ./run.sh =="
