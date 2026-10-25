# bse-harness

北交所个股深度研究的自进化 agent 基座：把 [Harness²](https://arxiv.org/abs/2610.14224) 的
RSI（递归自我改进）循环接到真实投研任务上——agent 写研报，harness 层自己进化提示词/守则/记忆，
多代对比选择，产出「研究报告 + 进化后的 harness」两样东西。

## 是什么

```
┌────────────────────────────────────────────────────────────┐
│ harness2（~/src/harness2）  RSI 内核：base rollout →        │
│   inv/dom/agg 三阶段 harness 改进（由 proposer 生成）→       │
│   对比选择 adopted harness → 下一代                         │
├────────────────────────────────────────────────────────────┤
│ bse/（本项目）  BenchmarkAdapter：                          │
│   task=920029 开发科技深度研报 ≥2000字 带[来源]              │
│   base_harness=卖方研究员种子人格 + 数据抓取脚本             │
├────────────────────────────────────────────────────────────┤
│ OpenCode substrate（agent 执行器）                          │
│   工具循环：bash/read/write/edit；事件流 jsonl               │
├────────────────────────────────────────────────────────────┤
│ 模型：magpie 代理 http://127.0.0.1:3425/v1                  │
│   默认 magpie/9router/mixtao（128k，免费）                   │
└────────────────────────────────────────────────────────────┘
```

数据源（实测可用，纯公开接口）：东财行情快照/日K/财务指标 F10 + 公告列表，
抓取脚本在 `bse/base_harness/scripts/fetch_bse.py`（stdlib-only）。

## 快速开始

```bash
./setup.sh          # 一次性：clone harness2 + bun 1.4.4 baseline + opencode（见 NOTES.md 坑表）
./run.sh smoke      # dry-run：打印 task_stream，验证装配
./run.sh sweep --k 1            # 正式递归（4 rollout + 3 阶段改进 + 对比选择）
BSE_MODEL=magpie/<其它模型> ./run.sh sweep --k 1   # 换模型（oc.config.json 同步声明）
```

产物（都在 `~/src/harness2/runs/bse/`）：
- `library/` — 进化后的 harness（最终交付之一）
- `_store/920029/<label>/output/report.md` — 各代研报
- `_sweeps/bse-s0.json` — sweep 汇总

## 关键设计（为什么能跑在这台 2012 Intel Mac 上）

1. **launcher 全自管**：`bse/adapter.py::_launch` Popen 起进程组，退出条件三选一
   ——自然退出 / 事件静默 120s 且交付物在场（杀组）/ 硬超时。
2. **叙述即停的兜底**：opencode run 模式「纯文本回合=终止」，mixtao 常说完计划不调工具。
   回合纪律写进 systemprompt/instruction，外加 `--session <sid>` resume 循环（12×45s）。
3. **上游不稳的兜底**：9router 免费流会 mid-reply 崩（见 NOTES.md sweep2 数据），
   靠 resume 重试 + provider `timeout/chunkTimeout` 掐挂起流。根治要换稳定模型。
4. **auto-compaction 必须关**：否则注入合成 "Continue..." user 消息，弱模型死循环。

## 交换性

- **任务**：往 `bse/tasks/<股票代码>/` 放 instruction.md + domain.txt 即加任务
- **模型**：`BSE_MODEL` 环境变量 + oc.config.json 声明
- **基准**：adapter 只实现 harness2 `BenchmarkAdapter` 协议（tasks/execute/delivered/
  trajectory/base_harness/...），换领域=换 adapter

## 现状（2026-10-24）

- 端到端 POC ✅：`samples/920029-report.md`（46min 单 rollout，5 次会话接力产出）
- 正式 sweep ✅（2026-10-24）：12×45s resume + chunkTimeout 版跑通，base1/agg1 双双交付
  （`samples/920029-sweep3-*.md`），进化 harness 已入库
- 当前已知瓶颈：rollout 拉全量原始数据 → ~300K tokens 爆 128K 窗口 → 报告写到 2-3 节截断；
  下一轮改进方向 = fetch 脚本分页/摘要输出 + guardrails 禁止一次性拉全量
- magpie 目前只有 9router/mixtao 一个模型，上游稳定性靠 resume 重试兜底（BSE_MODEL 即插即换）

## 参考

- Harness² 论文：arXiv 2610.14224（harness 层 RSI，与 prime-agent 的有界 refine 互补）
- 排障战史：`NOTES.md`
