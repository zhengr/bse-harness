"""BSE 适配层入口：python -m bse.run --k 1 [--dry-run] [--only-tasks 920029]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from harness2 import config
from harness2.core import schedule
from harness2.core.proposer import Proposer
from .adapter import make_adapter

ROOT = Path(__file__).resolve().parents[1]  # bse-harness 项目根


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bse.run")
    p.add_argument("--k", type=int, default=1)
    p.add_argument("--modes", default="agg")
    p.add_argument("--max-tasks", type=int, default=None)
    p.add_argument("--only-tasks", default="")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    # 干净的 opencode 配置（只带 magpie provider，不带全局 MCP）
    os.environ["OPENCODE_CONFIG"] = str(ROOT / "bse" / "oc.config.json")

    ad = make_adapter()
    ad.preflight()
    if a.dry_run:
        print(json.dumps(schedule.task_stream(ad, split="all", seed=a.seed), ensure_ascii=False))
        return 0

    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    prop = Proposer(ad.spec.channels["proposer"], audit_dir=ad.spec.runs_root / "_audit")
    rep = schedule.run_sweep(
        a.k,
        adapter=ad,
        prop=prop,
        runs_root=ad.spec.runs_root,
        library_root=ad.spec.runs_root / "library",
        split="all",
        modes=modes,
        seed=a.seed,
        tag="",
        domain_parallel=1,
        max_tasks=a.max_tasks,
        only_tasks=tuple(t for t in a.only_tasks.split(",") if t),
    )
    rec = ad.spec.runs_root / "_sweeps" / f"bse-s{a.seed}.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("record:", rec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
