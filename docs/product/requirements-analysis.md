# MorningBriefAgent 需求分析（产品经理视角）

- 版本：v0.1
- 日期：2026-11-05
- 分析对象：`README.md`、`AGENTS.md`、`docs/`（含 ADR）、`demo/`，并与 `core/`、`services/`、`storage/`、`server/`、`desktop/` 代码交叉验证
- 方法：只读分析。所有结论标注证据位置；未实际运行验证的内容标记为「待验证」，不作为验收依据

---

## 0. 结论摘要

1. 这个产品已经完成了一次**形态切换**：从「一组定时脚本 + 飞书推送」变成「本地优先的桌面产品 + 同一套 Python 业务核心」。但文档只记录了切换的**意图**，没有记录切换的**完成状态**。
2. 当前最突出的问题不是功能缺失，而是**三层事实不一致**：
   - 文档层说 A（PySide6 优先、desktop 规划中、api/ 目录）
   - 代码层是 B（Tauri 2 已落地、`core/application/` 承载 API）
   - 用户可达层是 C（导航只剩 4 个分区，多个已实现页面无入口）
3. `#86`「core reduction and minimal workspace layout」是一次**有意的产品收缩**（导航 5 → 4），方向正确；但入口、文档、发布说明没有同步收缩，留下了"死链 + 功能不可达"。
4. 建议本轮**不新增功能**，先做三件对齐：入口对齐、文档对齐、能力口径对齐。之后再用 PRD 驱动新增需求。

---

## 1. 文档盘点：谁说了算

| 文档 | 角色 | 最后更新 | 与代码一致性 | 判断 |
| --- | --- | --- | --- | --- |
| `README.md` | 对外说明书 / 用户上手 | 2026-10-17 | 中 | 功能表仍是 CLI 时代，未包含桌面端 |
| `AGENTS.md` | 工程规范 / 验收纪律 | 2026-10-21 | 高 | 最可靠，可作为流程基准 |
| `docs/architecture.md` | 整体架构与路线 | 2026-10-15 | 低 | 桌面端技术路线已过期 |
| `docs/desktop-architecture.md` | 桌面端决策 | 2026-10-17 | 中 | 决策正确，但把"骨架"写成"稳定边界" |
| `docs/adr/0001` | 单一会话决策 | 2026-10-14 | 高 | Accepted，仍然成立 |
| `docs/adr/0002` | 桌面端与知识库路线 | 2026-10-15 | 低 | 仍为 `Proposed`，但已被实际决策超越 |
| `docs/provider-evaluation.md` | Provider 评测方法 | 2026-10-15 | 中 | 方法可复用，数据是单次快照 |

**核心问题：文档之间没有仲裁机制。** ADR 只有 2 篇，其中 1 篇仍停在 Proposed；`architecture.md` 的路线图与 `desktop-architecture.md` 的决策直接冲突，读者无法判断哪份为准。文档最后更新集中在 10-14 ~ 10-17，而代码此后还有 3 次提交（最新 11-05）。

---

## 2. 产品定位复核

### 2.1 文档里的三种自我描述

| 出处 | 描述 | 隐含用户 |
| --- | --- | --- |
| `README.md:19-21` | 本地知识库与行动闭环 Agent，个人自托管、二次开发参考，不是 SaaS | 开发者本人 / 技术型个人用户 |
| `docs/architecture.md:5` | Windows 优先、面向个人业务流程的本地 Agent 工作流平台 | 平台使用者 |
| `desktop-architecture.md:5-9` | 发布版由 NSIS/MSI 安装，用户不需要单独装 Python | 非技术终端用户 |

这三者是**递进关系而非矛盾**：先自用 → 再平台化 → 再可分发给非技术用户。但产品当前实际只走到第一层的末端、第二层的开头。文档却已经按第三层的措辞在写（"用户不需要单独安装 Python"）。

**产品判断**：现阶段应明确对外表述为「可自托管的个人 Agent 工作台（开发中）」，避免用分发级产品的承诺描述一个尚未跑通首次体验的产品。

### 2.2 核心价值闭环与断点

```text
本地资料/公开信息 → Agent 理解与规划 → 质量门禁 → 用户确认 → 飞书提醒/本地投影 → 执行 → 复盘归档
        ✅                    ✅              ✅          ⚠️            ✅                  ⚠️        ⚠️
```

- **确认环节**：只有饮食热量有显式确认流程（`pending → confirmed`），待办与日程没有"计划预览 → 采纳"的界面化确认，用户只能在生成后去改。
- **执行环节**：桌面端不能标记完成后的回流（飞书任务完成状态不会回写），闭环在"提醒"处断开。
- **复盘环节**：日复盘有页面；周/月复盘有服务（`services/planning/review_weekly.py`、`review_monthly.py`）但无入口。

---

## 3. 能力矩阵：承诺 vs 实现 vs 可达

成熟度口径：**可用**（有实现且用户可达）/ **半可用**（有实现无入口或仅 CLI）/ **骨架**（有表或协议，无业务闭环）/ **未实现**

| 能力 | 文档承诺 | 代码实现 | 用户可达 | 成熟度 |
| --- | --- | --- | --- | --- |
| 首次引导（workspace→provider→channel→profile） | 是 | `desktop/src/components/onboarding/` + `storage/onboarding.py` | 桌面端 | 可用 |
| 工作区绑定 / 只读探针 / 503 映射 | 是 | `storage/workspace.py` + `local_api` | 自动 | 可用 |
| 今日视图（今日待办 + 今日日程） | 是 | `main.jsx` `TodayView` | 桌面端 | 可用 |
| 待办 CRUD 与状态流转 | 是 | `storage/planning.py` + `/api/v1/todos` | 桌面端 | 可用（缺流转校验，见 §4-D） |
| 日程查看 / 创建 | 是 | `schedule_records` + `/schedules` | 桌面端 | 可用 |
| 复盘（日） | 是 | `ReviewView` + `/audit-logs` | 桌面端 | 可用（仅统计+留痕） |
| 复盘（周/月） | 是 | `review_weekly.py` / `review_monthly.py` | 无 | 半可用 |
| Agent 计划生成（早/晚） | 是 | `services/planning/plan_generation.py` | 今日页两个按钮 | 可用（依赖 AGY） |
| 飞书任务/日历同步 | 是 | `task_sync.py` / `calendar_sync.py` | 后台 | 可用（依赖 `.env` 凭据） |
| 飞书双向对话机器人 | 是 | `server/feishu_bot_server.py` | 飞书侧 | 可用 |
| 新闻 / 简报 / 微信 / 健身 / 基金 | 是（标注实验性） | `services/content` `communications` `lifestyle` `finance` | **仅 CLI** | 半可用 |
| 文件工作台（知识库读写/重命名/恢复删除/文件夹同步） | 架构文档要求「桌面端内置文件管理器」 | `components/file-workspace/*` 完整 | **无入口** | 半可用 |
| 工作流调度中心（定时开关/执行记录/日志） | 架构文档列为桌面端职责 | `pages/WorkflowPage.jsx` + `/workflows` | **无入口** | 半可用 |
| 数据库浏览器 | 无明确承诺 | `pages/DatabasePage.jsx` + `/database/*` | **无入口** | 半可用 |
| Agent 运行监控 | 架构文档提到运行状态 | `/api/v1/agent/status` + `agent_status.py` | **无入口** | 半可用 |
| 子任务（并发/深度/超时/取消） | `architecture.md:127-136` 明确要求 | `services/subtasks.py` + `agent_subtasks` 表 | 仅 API | 骨架（无调度器，`max_retries`/`timeout` 未执行） |
| Provider 抽象（AGY/DeepSeek/...） | `architecture.md:109-125`，`desktop-architecture.md:14` 称"稳定边界" | `core/agent/runtime.py` 协议 + `deepseek_provider.py` | 业务仍直连 `provider.ask_text` | 骨架（Protocol 无生产实现，契约与 `contracts.py` 重复） |
| Channel 抽象（飞书/其他） | `desktop-architecture.md:15` 称"稳定边界" | `core/integrations/channel.py` 仅协议 | 无 | 骨架 |
| 版本化 Schema 迁移 | `AGENTS.md` 第七节明确要求 | `storage/sqlite.py` 仅 `IF NOT EXISTS` + 版本号 | — | 部分实现 |

---

## 4. 偏差清单（按性质分类，不按严重度）

### A. 决策冲突：同一问题两份结论

- `docs/architecture.md:166-178`：第一阶段推荐 **PySide6**，Tauri 作为第二阶段候选。
- `docs/desktop-architecture.md:3-10`：桌面端采用 **Tauri 2 + React**。
- `docs/adr/0002`：仍是 `Proposed`，内容支持 PySide6 优先。

**影响**：新加入的开发者/代理会按 architecture.md 走错方向；也无法从文档判断"为什么最终选了 Tauri"。
**建议**：新增 `ADR-0003` 记录 Tauri 决策与 PySide6 放弃理由，把 ADR-0002 标为 `Superseded`，并在 `architecture.md` 桌面端章节顶部加一行指向 ADR。

### B. 骨架被写成"稳定边界"

`desktop-architecture.md:12-18` 列出的 5 条稳定边界中，有 3 条在代码里没有生产接线：

| 声明为稳定边界 | 实际状态 |
| --- | --- |
| `core.agent.runtime.AgentProvider` | 无任何生产实现；业务直连 `core/agent/provider.py` → `agy_bridge`；`DeepSeekProvider` 也不实现该 Protocol |
| `core.integrations.channel.ChannelAdapter` | 仅协议定义，无实现 |
| `services.subtasks` | 仅 API + 测试，主链路未使用，无超时/重试调度 |

**影响**：文档把"计划中的抽象"表述成"已稳定的契约"，会让后续需求误以为可以直接扩展。这是比代码 bug 更贵的债。
**建议**：文档中为每条边界增加状态列（`已接线` / `仅协议`），或直接降级措辞为"目标边界"。

### C. 能力清单过期

- `README.md:231-240` 功能表 7 项全是 CLI 命令，**没有任何桌面端能力**（引导、今日、待办、日程、复盘）。
- `docs/architecture.md:54-55`：`desktop/（规划中）`、`api/（规划中）`。实际 `desktop/` 已实现，API 在 `core/application/local_api.py`（不存在 `api/` 目录）。
- `README.md` 未提及 `desktop/`、"文件工作台"、"工作流调度"，但仓库已有可运行实现。

### D. 产品收缩未回写（本轮最关键）

`#86`（`88cbd62`）把导航从 5 个分区收缩为 4 个：

```diff
- 工作台 / 文件与数据 / 工作流 / 数据库 / Agent 运行
+ 今天 / 待办 / 日程 / 复盘
```

收缩本身是对的（聚焦最小可用工作区），但留下两处未清理：

1. **入口残留**：`AppTopbar.jsx:25,42` 仍 `onNavigate("文件与数据")`，`AppTopbar.jsx:83` 仍 `onNavigate("工作流")`。`main.jsx` 的路由只认 4 个分区 + 设置，点击后**静默回落到今日视图**，标题却显示成"工作流"。
2. **触发链路被短路**：`DesktopMenuBar.jsx:124-138` 的 `runWorkflow` 只要 `onQuickRun` 存在就 `return`；而 `main.jsx:264,273` 传入的正是 `() => setActiveSection("今天")`。结果：菜单「立即执行工作流」**只跳首页，不发起请求**。收缩前 `onQuickRun` 承担真实执行，收缩后退化成"回首页"，属于**收缩引入的回归**。

此外还有三个已完成但未挂载的页面，仅被测试文件引用，未被任何组件 import：

| 页面 | 文件 | 引用情况 |
| --- | --- | --- |
| 数据库浏览器 | `desktop/src/pages/DatabasePage.jsx` | 仅 `truthfulStatus.test.js` 读取源码 |
| 工作流中心 | `desktop/src/pages/WorkflowPage.jsx` | 无任何引用 |
| 文件工作台 | `desktop/src/components/file-workspace/FileWorkspace.jsx` | 仅自身测试 |

**判断**：这不是"功能没做"，是"做完了没交付"。属于**范围决策与交付物未对齐**，应作为产品决策问题处理，而不是当作 bug 逐个修。

---

## 5. 用户旅程断点

| 阶段 | 期望 | 现状 | 断点等级 |
| --- | --- | --- | --- |
| 安装 | 双击安装包即可用 | 需 `build_local_api_sidecar.ps1` 产出 sidecar；`binaries/` 当前不存在，`tauri:dev` 直接报错 | 开发者友好，终端用户不可用 |
| 首次启动 | 引导配置工作区 | 4 步引导 + 可跳过 | 正常 |
| 配置 Provider | 选模型 / 填 Key | 仅探测本地 AGY 进程，无外部 Provider 填入路径 | 弱 |
| 创建第一条待办 | 3 秒内完成 | 今日页可创建 | 正常 |
| 生成计划 | 点一下就出计划 | 今日页两个按钮可用；**菜单入口失效** | 中 |
| 飞书接收 | 自动推送 | 依赖 `.env`，桌面端无完整配置页（仅引导期填写） | 中 |
| 执行回流 | 飞书完成任务后本地状态同步 | 无回写链路 | 高（闭环断点） |
| 复盘 | 日/周/月 | 仅日 | 中 |
| 知识库维护 | 桌面内管理文件 | 功能已实现但无入口 | 中 |

---

## 6. 需求池与优先级

评估口径：用户价值（1-5）、实现成本（S/M/L）、风险、建议批次

| # | 需求 | 价值 | 成本 | 风险 | 批次 |
| --- | --- | --- | --- | --- | --- |
| R1 | 清理入口残留：移除或补齐「文件与数据」「工作流」导航，保证不出现死链与静默回落 | 5 | S | 低 | **M1** |
| R2 | 修复菜单工作流触发：`runWorkflow` 不再被 `onQuickRun` 短路，补充成功/失败反馈 | 5 | S | 低 | **M1** |
| R3 | 文档对齐：新增 ADR-0003（Tauri 决策）、ADR-0002 置 Superseded、更新 architecture.md 桌面章节、README 增补桌面端能力表 | 4 | S | 极低 | **M1** |
| R4 | 能力状态表进文档：每条能力标注 `可用/半可用/骨架/未实现`，作为验收口径 | 4 | S | 低 | **M1** |
| R5 | 交付已完成的三个页面（工作流中心优先，其次文件工作台，数据库浏览器可放开发者模式） | 4 | M | 中（需补挂载后的测试） | **M2** |
| R6 | 复盘闭环：周/月复盘入口与卡片 | 3 | M | 中 | **M2** |
| R7 | 状态机收紧：`update_todo_status` 校验合法流转路径，实体不存在返回 404 | 3 | S | 低（有回归风险，需测试） | **M2** |
| R8 | 版本化迁移框架（按版本执行 ALTER，支持存量库升级） | 3 | L | 高（涉及用户数据） | **M3** |
| R9 | Provider 收敛：统一到单一契约，接入第二个真实 Provider | 3 | L | 高（跨模块） | **M3** |
| R10 | 执行回流：飞书任务完成状态回写本地 | 4 | L | 高（外部事件） | **M3** |

---

## 7. 需要产品决策的 5 个问题

以下问题会直接改变 M2/M3 的范围，建议先定，再写 PRD：

1. **产品形态**：继续做「个人自用 + 开源样板」，还是转向「可分发给非技术用户的安装包」？后者意味着首次体验、错误提示、数据迁移都要按产品级标准做。
2. **主入口**：桌面端优先，还是飞书优先？当前代码是桌面优先、飞书为可选投影；但 README 的叙事仍是飞书优先。二者投入结构不同。
3. **文件工作台是否回归**：它是「本地知识库」这个定位的唯一直接体现（差异化卖点），但也是维护成本最高的一块（文件树 + 编辑器 + 恢复删除 + 文件夹同步）。
4. **Provider 策略**：短期只支持本地 AGY（零 Key、隐私好、但 10s 级延迟），还是必须支持外部 API（快、但要处理密钥与隐私边界）？
5. **文档治理**：是否接受「ADR + 能力状态表」作为唯一事实源？否则下次收缩还会重复 `#86` 的残留问题。

---

## 8. 建议的下一阶段产出物

按产品经理流程，本轮之后应产出（尚未开始）：

1. **PRD（M1 范围）**：只覆盖 R1–R4，含背景、目标、非目标、交互说明、验收标准。
2. **验收矩阵**：沿用 `AGENTS.md` 第二节格式（验收标准 / 实现位置 / 回归测试 / 验证命令 / 状态）。
3. **Issue 拆分**：R1、R2 各一个 Issue（含复现路径），R3、R4 合并为一个"文档对齐" Issue。
4. **发布口径**：README 增加"当前能力状态"小节，避免对外承诺超出实现。

> 本文档只做分析，不含实施结论。M1 是否启动、范围是否调整，待产品决策后再定。
