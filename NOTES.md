# 运行记录与战史

## 2026-10-22~23 环境战（已全部攻克）

| 坑 | 症状 | 修法 |
|---|---|---|
| bun 1.3.x on Ivy Bridge | 全变体 SIGILL（无 AVX2/FMA）；npm postinstall 依赖 baseline 变体装不上 | `npm pack @oven/bun-darwin-x64-baseline@1.4.4` 手动解包；实测 1.4.4 baseline 可跑 |
| harness2-setup | 顺带拉 JobBench 数据集 | 直接用 `harness2.dependencies.install` 模块装 opencode substrate |
| opencode auto-compaction | 小会话也反复触发 → 注入 "Continue if you have next steps" 合成 user 消息 → 弱模型死循环（smoke 卡 900s+） | oc.config.json 加 `"compaction": {"auto": false}`；rollout 900s→95.6s 自然退出 |
| mixtao 叙述即停 | opencode run = 纯文本回合即终止；mixtao 常说完计划不调工具 | a) systemprompt/instruction「回合纪律」；b) launcher resume 循环：`--session <sid>` 续跑，最多 12 次，45s 退避 |
| resume_cmd 拼接 | `cmd[:-2]` 保留原 `--dir` 又加一遍 → "ws,ws" → opencode chdir 失败 | resume_cmd 全新构造 |
| magpie/9router 流崩 | `connection lost mid-reply (INTERNAL_ERROR)` / Cloudflare 502/504，每 rollout 8~10 次 | resume 重试 + provider `timeout=600000, chunkTimeout=90000`（oc.config.json）；根本解：换稳定上游 |

## 端到端 POC（已通过）

resume-smoke：单 rollout 46min，5 次 opencode 会话接力，产出 2179 字带 [来源] 标注的 920029 完整研究报告 → `samples/920029-report.md`。

## 正式 sweep 记录

- **sweep1**（10-23 05:19–09:09 UTC）：4 rollout 全部无报告。死因=叙述即停 + resume 代码有 dup `--dir` bug。selection failed: no base fallback。
- **sweep2**（10-23 09:28–14:35 UTC，重试 8×30s）：4 rollout 重跑（base1 114ev/31 tools，inv1 155ev/45，dom1 141ev/40，agg1 107ev/36），全部被 9router 流崩打死（每 rollout 8~10 次 INTERNAL_ERROR）。**结论：基础设施 OK，瓶颈=免费上游稳定性。**
- 下一步：resume 12×45s + chunkTimeout 版重跑；若仍崩，需要 magpie 侧加稳定模型（BSE_MODEL 即插即换）。

## sweep 产物地图（都在 ~/src/harness2/runs/bse/）

- `_store/920029/<label>/output/report.md` — 各 rollout 交付
- `_store/920029/traj/<label>/events.jsonl|stderr*.log|cmds.log|rc.txt` — 轨迹与排障现场
- `_sweeps/bse-s0.json` — 每次 sweep 汇总记录
- `library/` — 进化 harness 库；`_audit/` — proposer 调用审计

## 调试速查

- opencode 事件流：`step_start/tool_use/step_finish/text/error`，error 事件带 `error.data.message`
- session 续跑：`--session <sid>`（sessionID 从 events.jsonl 任意事件取）
- stdout 事件静默 120s + 交付物在场 → launcher 杀进程组（`_run_oc`）
- 排障入口：先看 traj/<label>/events.jsonl 尾部 + stderr.resume.log
