# M1 PRD：让产品「诚实」

- 版本：v1.0
- 状态：待确认后实施
- 依据：`docs/product/requirements-analysis.md` §4-D、`docs/product/product-definition.md` §6/§8
- 范围性质：**缺陷修复 + 文档对齐**。不含新功能。

---

## 1. 背景

`#86`（提交 `88cbd62`）把桌面导航从 5 个分区收缩为 4 个（今天 / 待办 / 日程 / 复盘），收缩方向正确。但入口层、触发链路、文档层没有同步收缩，导致三类"看起来有、实际没有"的落差：

1. 顶栏仍有指向已移除分区的入口，点击后静默回落到今日视图；
2. 菜单「立即执行工作流」被 `onQuickRun` 短路，只跳首页、不发请求；
3. 文档仍在描述收缩前的形态与已被推翻的技术路线。

信任损耗与功能多少无关：一次"点了没反应"就足以让人不再打开。

## 2. 目标

| # | 目标 | 度量 |
| --- | --- | --- |
| G1 | 桌面端不存在任何"点了没反应 / 跳错地方"的入口 | 全量点击走查，0 处异常 |
| G2 | 两个工作流可从菜单与顶栏正确触发，且有明确反馈 | 手动触发 2 次，均出现成功或失败提示 |
| G3 | 文档中的能力描述与代码实现一致 | 能力状态表 100% 有据可查 |

## 3. 非目标

- 不挂载 `DatabasePage` / `WorkflowPage` / `FileWorkspace`（M2 处理）。
- 不新增页面、不调整视觉风格、不改路由结构。
- 不修 `storage/` 层状态机与迁移问题（M2/M3 处理）。
- 不改飞书侧行为。

## 4. 用户故事

1. 作为唯一用户，我点菜单里的「立即执行：早间计划与日程」时，希望它**真的开始跑**，并告诉我成功还是失败。
2. 作为唯一用户，我看到顶栏的搜索框和知识库标签时，不希望点下去跳到别的地方，或者什么都不发生。
3. 作为三个月后回看这个仓库的人，我希望文档能告诉我"哪些能力真的能用"。

## 5. 需求明细

### R1 入口一致性

| 编号 | 现状 | 期望 | 决策 |
| --- | --- | --- | --- |
| R1.1 | `AppTopbar.jsx:22-28` 搜索框回车 `onNavigate("文件与数据")`，该分区已不存在，静默回落今日 | 不出现"搜索了却跳首页" | **M1 隐藏搜索胶囊**（保留组件代码与样式，加注释标明 M2 随文件工作台恢复）。理由：一个不能搜索的搜索框比没有搜索框更伤信任 |
| R1.2 | `AppTopbar.jsx:42` 知识库 chip 可点击跳「文件与数据」死链 | 点击要么有真实去处，要么不可点 | 改为**纯展示**（保留 `title` 显示完整路径），移除 `onClick` 与箭头图标 |
| R1.3 | `AppTopbar.jsx:81-84` 闪电按钮 `onQuickRun()` 无参；若接上真实执行函数会请求 `/workflows/undefined/run` | 无参调用不得臆造工作流 | 无参时**跳转「今天」**，`title` 改为「前往今日行动」；有参时才执行工作流 |
| R1.4 | `DesktopMenuBar.jsx:124-129` 只要 `onQuickRun` 存在就 `return`；`main.jsx:264,273` 传入的却是 `() => setActiveSection("今天")` | 菜单触发真实执行 | **把 `TodayView` 内的 `quickRun`（`main.jsx:379-399`）上提到 `App` 层**，作为唯一实现，同时传给 `ApplicationShell`、`AppTopbar`、菜单 |

**关键约束**：`quickRun` 必须只有一份实现。上提后 `TodayView` 通过 props 接收，不得复制第二份。

### R2 工作流触发反馈

| 现状 | 期望 |
| --- | --- |
| 失败时仅 `console.error`（`DesktopMenuBar.jsx:135-137`） | 菜单触发失败必须给出可见提示，与今日页文案口径一致 |

**提示口径**：成功 = 「已成功启动 [名称]，全流程后台执行中」；失败 = 「触发 [名称] 失败：<原因>」。沿用 `main.jsx:388-394` 的现有文案，不新造。

### R3 文档对齐

| 编号 | 动作 |
| --- | --- |
| R3.1 | 新增 `docs/adr/0003-desktop-tauri-over-pyside6.md`（状态 Accepted），记录为什么最终选 Tauri 而非 `architecture.md` 推荐的 PySide6 |
| R3.2 | `docs/adr/0002-...md` 顶部加注：桌面端技术路线部分已被 ADR-0003 取代，知识库存储部分仍有效；状态改为 `Superseded (桌面端部分)` |
| R3.3 | `docs/architecture.md`：删除「桌面端技术路线评估」中已被推翻的推荐结论，改为一行指向 ADR-0003；`desktop/（规划中）`、`api/（规划中）` 改为实际状态（`desktop/` 已实现；本地 API 位于 `core/application/`，不存在 `api/`） |
| R3.4 | `README.md`：功能概览表增补桌面端能力行；新增「当前能力状态」小节，链接 R4 的能力状态表 |
| R3.5 | `docs/product/product-definition.md` 与 `requirements-analysis.md` 在 README 中加一行指引（可选，二者不重复内容） |

### R4 能力状态表

新建 `docs/product/capability-status.md`，为 §3 能力矩阵的持续维护版，每条能力必须有四列：能力 / 状态（可用·半可用·骨架·未实现）/ 代码位置 / 用户入口。

**状态判定规则（防止自我美化）**：

- 可用：有实现 + 用户可达 + 有回归测试
- 半可用：有实现，但无入口或仅 CLI
- 骨架：只有表 / 协议 / API，无业务闭环
- 未实现：文档提到但代码不存在

## 6. 验收矩阵

| 验收标准 | 实现位置 | 回归测试 | 验证命令 | 状态 |
| --- | --- | --- | --- | --- |
| 顶栏不存在指向「文件与数据」「工作流」的可点击入口 | `desktop/src/components/AppTopbar.jsx` | `desktop/src/components/appTopbarEntrypoints.test.js`（源码断言，禁止出现该两处 `onNavigate`） | `npm test -- --run` | 未实现 |
| 知识库 chip 不可点击且保留路径提示 | `AppTopbar.jsx` | 同上 | `npm test -- --run` | 未实现 |
| 闪电按钮无参时跳「今天」 | `AppTopbar.jsx` + `main.jsx` | `desktop/src/components/workflowTrigger.test.js` | `npm test -- --run` | 未实现 |
| 菜单工作流触发真实请求 `/api/v1/workflows/{key}/run` | `DesktopMenuBar.jsx` + `main.jsx`（上提的 `quickRun`） | `workflowTrigger.test.js` 覆盖请求构造；源码断言 `main.jsx` 的 `onQuickRun` 不是 `setActiveSection` 包装 | `npm test -- --run` | 未实现 |
| 触发成功/失败均有可见提示 | `main.jsx` `quickRun` | 手动走查 + 文案断言 | 手动 | 未实现 |
| `quickRun` 只有一份实现 | `main.jsx` | 源码断言：`main.jsx` 中 `/workflows/` 仅出现 1 次 | `npm test -- --run` | 未实现 |
| ADR-0003 存在且为 Accepted；ADR-0002 已标注被取代 | `docs/adr/` | 无（文档） | 人工核对 | 未实现 |
| `architecture.md` 无「推荐 PySide6」结论、无「规划中」的 desktop/api | `docs/architecture.md` | 无（文档） | 人工核对 | 未实现 |
| README 含桌面端能力行与能力状态指引 | `README.md` | 无（文档） | 人工核对 | 未实现 |
| 能力状态表每条含状态、代码位置、入口 | `docs/product/capability-status.md` | 无（文档） | 人工核对 | 未实现 |
| 桌面端测试与构建通过 | — | — | `npm test -- --run`、`npm run build` | 未实现 |
| Python 测试与编译无回归 | — | — | `python -m unittest discover -s tests -p "test_*.py"`、`python -m compileall -q .` | 未实现 |
| 无空白错误 | — | — | `git diff --check` | 未实现 |

## 7. 技术约束

- **不新增依赖**。`vitest` 当前为 node 环境，无 jsdom；R2 的回归测试只能覆盖纯函数与源码断言，不得为此引入 `@testing-library`（需单独授权）。
- 纯逻辑抽到 `desktop/src/components/workflowTrigger.js`（`buildWorkflowRequest(key)` 返回 `{ url, method }`；`isWorkflowKey(key)` 白名单校验 `todo-morning` / `todo-evening`），保证可在 node 环境测试。
- 隐藏搜索胶囊时保留组件内部实现与样式类，不删除 CSS，便于 M2 恢复。

## 8. 风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 上提 `quickRun` 影响今日页按钮 | 今日页两条主路径失效 | 今日页保留原按钮，改为接收 props；手动走查两个入口各一次 |
| 移除搜索框被视为功能回退 | 用户感知下降 | 在 PR 描述中说明"M2 随文件工作台恢复"，并写入能力状态表 |
| 文档改动与后续 M2 再次冲突 | 重复返工 | R3 只描述"当前实现"，不预测 M2；M2 落地时再更新 ADR 与状态表 |

## 9. 交付与回滚

- 单 PR，提交信息建议：`fix(desktop): align entrypoints with reduced navigation and truthful docs`
- 文档与代码同一 PR，避免"代码改了文档没改"再次发生。
- 回滚：仅前端与文档改动，`git revert` 即可，无数据迁移、无 Schema 变更。
