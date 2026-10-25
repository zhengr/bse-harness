"""北交所个股深度分析 adapter：tasks 来自 harness2/bse/tasks/，rollout 走 OpenCode substrate。

Protocol 实现（core/spec.py BenchmarkAdapter）。模型默认 magpie/9router/mixtao，
可用 BSE_MODEL 覆盖（必须 provider-prefixed）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from harness2 import config
from harness2.core import tree as HT
from harness2.core.spec import BenchPrompts, BenchSpec, resolve_channel_model
from harness2.substrate.base import Install, RunRequest
from harness2.substrate.opencode import OpencodeSubstrate

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks"
BASE_HARNESS = ROOT / "base_harness"
MODEL = os.environ.get("BSE_MODEL", "magpie/9router/mixtao")
TIMEOUT = int(os.environ.get("BSE_TIMEOUT", "2400"))

PROMPT = """=== 任务文件夹 ===
{ws}/task_folder

1. 阅读 task_folder/instruction.md，完成其中要求的全部工作。
2. 数据获取优先运行 scripts/ 下脚本（python3 scripts/<name>.py），也可自行扩展。
3. 最终交付只保存到 {ws}/output/（instruction.md 指定的文件），不要存中间文件。
"""

RESUME_PROMPT = """继续完成 task_folder/instruction.md 的任务：上次你的回合以纯文字结束导致会话提前中断。
先检查 output/ 现状，从中断处继续，不要重复已完成的工作。
规则：每个回复必须包含工具调用，直到 output/report.md 按 instruction.md 全部要求完成；
报告完成后，最后一条纯文字消息只写两个字：完成。
"""

BSE_PROMPTS = BenchPrompts(
    work=(
        "北交所上市公司深度投资研究。agent 在工作区拿到公司代码、任务说明书和数据抓取脚本，"
        "需要自行获取行情、K线、财务指标、公告等公开数据，独立完成计算与交叉验证，"
        "产出一份结构化、可溯源、可直接使用的研究报告。数据可溯源、计算可复现比辞藻重要。"
    ),
    domain_word="行业",
    inv_levers=(
        "- 先盘点能拿到哪些数据与口径（快照、日K、财务指标、公告），记录字段来源与单位\n"
        "- 结构化数据用脚本程序化提取与计算，保留中间结果与假设\n"
        "- 把任务拆成输出清单：报告每节需要哪些数据点；先写出可用的初稿再迭代\n"
        "- 交付前用工具重读产出文件，核对章节完整与数值口径一致"
    ),
    dom_levers=(
        "- 沉淀的是研究流程：数据源层级、计算方法、报告结构、质控检查，不是某只股票的数字\n"
        "- 区分权威输入与衍生数据，冲突来源显式裁决\n"
        "- 估值与结论必须可追溯到计算、来源位置或明示假设；不确定处显式标注"
    ),
    yardstick=(
        "报告是否覆盖完整数据面、计算可复现、结论可溯源、结构完整可直接使用、没有编造数据。"
    ),
    deliverable_word="研究报告",
)


def _channels() -> dict:
    ch = resolve_channel_model("opencode", MODEL, effort="", steps=120, timeout=3600)
    return {"proposer": ch, "selector": ch}


def make_spec() -> BenchSpec:
    return BenchSpec(
        name="bse",
        runs_root=config.RUNS / "bse",
        install_mode="workspace_agents_md",
        prompts=BSE_PROMPTS,
        channels=_channels(),
        domain_word="行业",
        allow_subagents=True,
        obs_trunc=50_000,
        proposer_deliverables="contents",
    )


def _label(run_id: str) -> str:
    return run_id.replace("/", "__")


@dataclass
class BseAdapter:
    spec: BenchSpec
    substrate: OpencodeSubstrate

    @property
    def timeout(self) -> int:
        return TIMEOUT

    # ---- tasks ----
    def tasks(self, split: str = "all") -> list[str]:
        return sorted(p.name for p in TASKS.iterdir() if (p / "instruction.md").is_file())

    def domain_of(self, task_id: str) -> str:
        f = TASKS / task_id / "domain.txt"
        return f.read_text(encoding="utf-8").strip() if f.is_file() else "北交所"

    def task_prompt(self, task_id: str) -> str:
        return (TASKS / task_id / "instruction.md").read_text(encoding="utf-8")

    def task_files(self, task_id: str) -> Path:
        return TASKS / task_id

    # ---- storage layout ----
    def _run_dir(self, task_id: str, run_id: str) -> Path:
        return self.spec.runs_root / "_store" / task_id / _label(run_id)

    def _traj_dir(self, task_id: str, run_id: str) -> Path:
        return self.spec.runs_root / "_store" / task_id / "traj" / _label(run_id)

    # ---- protocol ----
    def execute(self, task_id, harness_dir, run_id, *, timeout=None) -> Path:
        out, mark = self._run_dir(task_id, run_id), self._traj_dir(task_id, run_id)
        if (mark / "done.json").is_file() and self.delivered(out):
            return out
        shutil.rmtree(out, ignore_errors=True)
        shutil.rmtree(mark, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        mark.mkdir(parents=True, exist_ok=True)
        src = Path(harness_dir) if harness_dir is not None else self.base_harness()
        install = self.substrate.materialise(src, self.spec, {})
        try:
            dirs = self.substrate.execute(task_id, install, [run_id], int(timeout or TIMEOUT))
        finally:
            shutil.rmtree(install.staging_dir, ignore_errors=True)
        (mark / "done.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")
        return dirs[0]

    def delivered(self, run_dir) -> bool:
        f = Path(run_dir) / "output" / "report.md"
        try:
            return f.is_file() and len(f.read_text(encoding="utf-8", errors="replace")) >= 1000
        except OSError:
            return False

    def trajectory(self, run_dir, *, obs_trunc: int) -> str:
        mark = Path(run_dir).parent / "traj" / Path(run_dir).name
        files = sorted(mark.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if mark.is_dir() else []
        if not files:
            return f"(no trajectory for {run_dir})"
        return self.substrate.read_trajectory(files[0], obs_trunc=obs_trunc, max_chars=8_000_000)

    def deliverable_files(self, run_dir) -> dict[str, str]:
        d = Path(run_dir) / "output"
        if not d.is_dir():
            return {}
        return {
            p.name: p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(d.glob("*.md"))
        }

    def deliverable_text(self, run_dir) -> str:
        return "\n\n".join(self.deliverable_files(run_dir).values())

    def base_harness(self) -> Path:
        if not HT.is_tree(self.substrate.surface(), BASE_HARNESS):
            raise FileNotFoundError(f"BSE base harness missing/not a tree: {BASE_HARNESS}")
        return BASE_HARNESS

    def validate_tree(self, tree) -> None:
        return None

    def score(self, run_dir, task_id) -> dict | None:
        return None

    def preflight(self) -> None:
        self.substrate.preflight()
        if not TASKS.is_dir() or not self.tasks():
            raise RuntimeError(f"no tasks under {TASKS}")


# ---------------- launcher ----------------

def _launch(req: RunRequest, install: Install) -> list[Path]:
    task_id, run_id = req.task_ref, req.run_ids[0]
    ad: BseAdapter = _ADAPTER
    run_dir, mark = ad._run_dir(task_id, run_id), ad._traj_dir(task_id, run_id)
    ws = Path(tempfile.mkdtemp(prefix="bse_ws_", dir="/tmp"))
    from harness2.benchmarks.jobbench import render_opencode_tree
    render_opencode_tree(install.staging_dir, ws, {})
    (ws / "output").mkdir(parents=True, exist_ok=True)
    shutil.copytree(TASKS / task_id, ws / "task_folder")
    cmd = [
        str(config.BUN), "run", "--cwd",
        str(config.OPENCODE_DIR / "packages" / "opencode"),
        "--conditions=browser", "src/index.ts", "run",
        PROMPT.format(ws=ws), "--dir", str(ws),
        "--model", MODEL, "--title", _label(run_id), "--format", "json",
    ]
    env = os.environ.copy()
    env["PATH"] = str(config.DEPENDENCIES / "tools" / "node_modules" / ".bin") + ":" + env.get("PATH", "")
    env["OPENCODE_PERMISSION"] = json.dumps(
        {"external_directory": {"*": "deny", str(ws): "allow", f"{ws}/**": "allow",
                                "/tmp": "allow", "/tmp/**": "allow"}}
    )
    env["XDG_DATA_HOME"] = str(mark / "ocdata")
    env["XDG_STATE_HOME"] = str(mark / "ocstate")
    mark.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    stdout, rc = _run_oc(cmd, env, ws, req.timeout, ws / "output" / "report.md", errlog=mark / "stderr.log")
    (mark / "events.jsonl").write_text(stdout or "", encoding="utf-8")
    (mark / "rc.txt").write_text(str(rc), encoding="utf-8")
    outwsrc = ws / "output"
    if outwsrc.is_dir():
        shutil.copytree(outwsrc, run_dir / "output", dirs_exist_ok=True)
    shutil.copytree(ws / "task_folder", run_dir / "task_folder", dirs_exist_ok=True)

    # ponytail: mixtao ends turns with narration-only text -> run exits early.
    # Resume the same session (bounded) until the deliverable appears.
    # Upgrade: drop when a stronger model keeps its own tool loop alive.
    def _dv_ok() -> bool:
        try:
            return (outwsrc / "report.md").is_file() and (outwsrc / "report.md").stat().st_size > 1000
        except OSError:
            return False

    # ponytail: magpie/9router drops streams mid-reply; retry with backoff.
    # Upgrade: swap model/provider via BSE_MODEL if flakiness persists.
    for _ in range(12):
        if _dv_ok():
            break
        try:
            els = [json.loads(l) for l in (mark / "events.jsonl").read_text().splitlines() if l.strip()]
            sid = next(e["sessionID"] for e in reversed(els) if "sessionID" in e)
        except Exception:
            break
        time.sleep(45)
        resume_cmd = [
            str(config.BUN), "run", "--cwd",
            str(config.OPENCODE_DIR / "packages" / "opencode"),
            "--conditions=browser", "src/index.ts", "run",
            RESUME_PROMPT, "--dir", str(ws), "--model", MODEL,
            "--title", _label(run_id), "--format", "json", "--session", sid,
        ]
        with open(mark / "cmds.log", "a", encoding="utf-8") as cf:
            cf.write(" ".join(resume_cmd) + "\n")
        stdout2, rc2 = _run_oc(resume_cmd, env, ws, req.timeout, outwsrc / "report.md",
                               errlog=mark / "stderr.resume.log")
        (mark / "events.jsonl").write_text(((mark / "events.jsonl").read_text() + "\n" + stdout2) if (mark / "events.jsonl").is_file() else stdout2, encoding="utf-8")
        (mark / "rc.txt").write_text(str(rc2), encoding="utf-8")

    if outwsrc.is_dir():
        shutil.rmtree(run_dir / "output", ignore_errors=True)
        shutil.copytree(outwsrc, run_dir / "output", dirs_exist_ok=True)
    shutil.rmtree(ws, ignore_errors=True)
    return [run_dir]



# ---------------- opencode process runner ----------------
# ponytail: opencode (bun baseline on macOS) hangs at exit after the run completes.
# Exit paths: natural exit | 120s event silence + deliverable present | hard timeout.
# Upgrade: find the real hang (socket handle in src) and drop this lull heuristic.

def _run_oc(cmd, env, cwd: Path, wall: int, deliverable: Path, errlog: Path | None = None) -> tuple[str, int]:
    import signal, threading, time
    errfile = open(errlog, "w", encoding="utf-8", errors="replace") if errlog else subprocess.PIPE
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errfile,
        text=True, start_new_session=True,
    )
    lines: list[str] = []
    last_evt = time.time()
    started = time.time()

    def _pump(stream, sink):
        nonlocal last_evt
        for line in stream:
            last_evt = time.time()
            sink.append(line)
        stream.close()

    threads = [threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True)]
    if errfile is subprocess.PIPE:
        threads.append(threading.Thread(target=_pump, args=(proc.stderr, []), daemon=True))
    for t in threads:
        t.start()
    while True:
        time.sleep(5)
        if proc.poll() is not None:
            break
        now = time.time()
        dv_ok = False
        try:
            dv_ok = deliverable.is_file() and deliverable.stat().st_size > 400
        except OSError:
            pass
        if now - started > 180 and now - last_evt > 120 and dv_ok:
            break
        if now - started > wall:
            break
    rc = proc.poll()
    if rc is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            rc = proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            rc = proc.wait()
    for t in threads:
        t.join(timeout=5)
    return "".join(lines), rc

_ADAPTER: BseAdapter | None = None


def make_adapter() -> BseAdapter:
    global _ADAPTER
    sub = OpencodeSubstrate(launcher=_launch)
    _ADAPTER = BseAdapter(spec=make_spec(), substrate=sub)
    return _ADAPTER
