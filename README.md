# MorningBriefAgent

一个 Windows 优先的本地知识库与行动闭环 Agent：把飞书、Obsidian、本地消息、新闻和可选领域数据串成可定时执行的工作流。

项目目前适合个人自托管、二次开发和自动化方案参考；它不是开箱即用的 SaaS，也尚未达到面向多租户的生产级服务标准。源码不包含任何特定用户的目标、作息、学校、职业或生活规划。

> 本项目与飞书、Obsidian、微信或 Google Antigravity 均无官方隶属关系。涉及本地聊天数据库的功能只应处理你有权访问的数据，并遵守所在地法律、平台条款和他人隐私。

## 为什么做这个项目

多数“晨报机器人”只负责把内容发出去。MorningBriefAgent 更关注完整闭环：

```text
本地数据与公开信息
        ↓
解析、筛选、生成计划
        ↓
飞书卡片 / 日历 / 任务
        ↓
用户回复、确认、打卡
        ↓
Obsidian 日记、周报、月报
```

它的开源价值主要在于：

- 展示个人数据、本地知识库与飞书 OpenAPI 的组合方式；
- 提供“晨间计划—白天执行—晚间复盘—周期汇总”的工作流骨架；
- 展示 Windows 计划任务、长连接机器人和本地智能体桥接的工程实践；
- 可按需拆用飞书客户端、日历同步、复盘级联或定时脚本。

项目的差异点不是某个单独的 AI 模型，而是把多个本地数据源收敛为统一入口，并把目标、偏好和计划交给 Agent 从本地知识库推断。没有配置上下文时，系统不会猜测用户的生活规划，而是返回通用结果或请求补充信息。

## 功能概览

| 能力 | 命令 | 主要依赖 | 当前状态 |
| --- | --- | --- | --- |
| 知识库与晨间简报 | `python main.py brief` | Obsidian、可选本地 Agent、飞书 | 可用，目录结构需适配 |
| 微信沟通复盘 | `python main.py chat` | 合法取得的本地解密库、可选 zstd | 实验性，微信数据库结构可能变化 |
| 国内外与技术资讯 | `python main.py news` | 网络、飞书 | 可用，外部源可能失效 |
| 可选活动与饮食建议 | `python main.py fitness` | Obsidian、飞书 | 可用，内容来自本地数据 |
| 市场与基金摘要 | `python main.py fund` | 网络、飞书 | 实验性，不构成投资建议 |
| 早晚待办闭环 | `todo-morning` / `todo-evening` | 本地上下文、飞书任务与日历 | 可用，计划由 Agent 生成 |
| 双向飞书机器人 | `python main.py bot` | 飞书长连接、本地 AGY 桥接 | 实验性，仅建议单用户自托管 |

## 环境要求

- Windows 10/11；
- Python 3.10 或更高版本；
- 一个已启用机器人能力的飞书企业自建应用；
- 可写入的 Obsidian Vault（使用相关功能时）；
- Google Antigravity 本地 `language_server`（仅双向智能问答需要，属于非标准本地集成）；
- 本地微信解密数据库（仅聊天复盘需要，本项目不提供解密工具或绕过访问控制的方法）。

## 快速开始

```powershell
git clone <your-repository-url>
cd MorningBriefAgent

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
python main.py --help
```

先验证无需私人数据的入口：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q .
python main.py doctor
```

默认测试不会访问真实飞书。需要验证本机凭据和只读任务接口时，可显式运行：

```powershell
$env:RUN_LIVE_INTEGRATION="1"
python -m unittest discover -s tests -v
```

真实集成检查只读取任务列表，不创建任务、日历事件或消息。

再按需执行单个服务。建议先运行前台命令观察输出，确认配置正确后再接入 Windows 计划任务。

## 配置

项目根目录的 `.env` 会在导入配置时自动加载，已经存在的系统环境变量优先级更高。`.env` 被 Git 忽略；只提交 `.env.example`。

### 必需的飞书配置

```dotenv
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=replace_me
FEISHU_USER_OPEN_ID=ou_xxx
FEISHU_CHAT_ID=oc_xxx
FEISHU_ALLOWED_OPEN_IDS=ou_xxx
```

`FEISHU_ALLOWED_OPEN_IDS` 是可以触发本地工具的发送者白名单，多个 Open ID 用英文逗号分隔。未配置时默认只允许 `FEISHU_USER_OPEN_ID`；不要为了省事设置成公共范围。

在飞书开发者后台启用长连接事件订阅，并按实际使用的消息、日历和任务 API 申请最小权限。权限名称可能随平台版本变化，以飞书官方控制台提示为准。

### 本地数据路径

```dotenv
VAULT_ROOT=D:\path\to\your\obsidian-vault
EMAIL_INBOX_DIRS=D:\path\to\mail\inbox;D:\path\to\another\mail\inbox
TECH_NEWS_DIR=D:\path\to\technical\digest
NEWS_DOMESTIC_URLS=https://example.com/domestic.json;https://example.com/domestic-live.json
NEWS_WORLD_URLS=https://example.com/world.rss;https://example.com/another-world.rss
NEWS_FALLBACK_LINK=https://example.com/news
WECHAT_TOOLS_DIR=D:\path\to\wechat-decrypt
WECHAT_MSG_DB=D:\path\to\decrypted\message\message_0.db
WECHAT_CONTACT_DB=D:\path\to\decrypted\contact\contact.db
```

`EMAIL_INBOX_DIRS` 是邮件 Markdown 收件目录列表，`TECH_NEWS_DIR` 是可选的技术摘要目录，均使用分号分隔（邮件目录可配置多个）。解析器不会假设任何特定的 Vault 子目录名称；未配置时不会扫描对应数据。

`NEWS_DOMESTIC_URLS` 和 `NEWS_WORLD_URLS` 是可替换的新闻源列表，使用分号分隔；新闻抓取器不再把具体 RSS/API 地址写死在源码中。

外部写入使用稳定幂等键。默认状态文件为 `data/idempotency.sqlite3`（已被 Git 忽略），也可以显式设置：

```dotenv
IDEMPOTENCY_STORE_PATH=D:\path\to\runtime\data\idempotency.json
```

任务按“日期 + 标题”复用，日历按“日期 + 时间槽 + 摘要”复用；同步计划不会删除目标日期中用户手动创建的其他日程。
任务、日历和卡片共用同一个 `execute_once` 幂等执行入口。

如果检测到旧版 `idempotency.json`，程序会自动导入 SQLite，并保留
`idempotency.json.migrated` 作为迁移标记与备份。

待办输出路径也必须显式配置：

```dotenv
TODAY_TODO_PATH=D:\path\to\knowledge-base\daily-plan.md
TODO_ARCHIVE_DIR=D:\path\to\knowledge-base\plan-archive
REVIEW_DAILY_DIR=D:\path\to\knowledge-base\reviews\daily
REVIEW_WEEKLY_DIR=D:\path\to\knowledge-base\reviews\weekly
REVIEW_MONTHLY_DIR=D:\path\to\knowledge-base\reviews\monthly
FITNESS_PLAN_PATH=D:\path\to\knowledge-base\activity-plan.md
FITNESS_LOG_PATH=D:\path\to\knowledge-base\activity-log.md
FITNESS_ARCHIVE_DIR=D:\path\to\knowledge-base\activity-archive
CHAT_ARCHIVE_DIR=D:\path\to\knowledge-base\chat-reviews
```

未配置这些路径时，服务仍可生成 Agent 计划并同步飞书任务/日历，但不会擅自创建或猜测本地知识库目录。

### Agent 上下文与计划

个人目标、偏好、约束和计划只应放在本地知识库，不要写入公开源码。可以显式配置若干 Markdown 文件，或配置一个目录让程序递归读取：

```dotenv
AGENT_CONTEXT_FILES=D:\private\context\goals.md;D:\private\context\preferences.md
AGENT_CONTEXT_DIRS=D:\private\context
```

`AGENT_CONTEXT_FILES` 和 `AGENT_CONTEXT_DIRS` 使用分号分隔。系统会根据当前任务选择相关片段，并将其交给本地 Agent；源码不会假设你的学校、考试、作息、运动项目、投资目标或社交规则。未配置上下文时，待办和时间块不会凭空填充个人计划。

微信群筛选和联系人排除规则也应保留在本地：

```dotenv
WECHAT_GROUP_KEYWORDS=important-group
WECHAT_EXCLUDED_USERNAMES=wxid_example
WECHAT_EXCLUDED_NAME_KEYWORDS=self-notes
```

### 可选的本地 AGY 桥接

```dotenv
AGENTAPI_EXE=C:\path\to\language_server.exe
AGY_BRAIN_DIR=C:\path\to\antigravity\brain
AGY_CONVERSATION_ID=your-conversation-id
```

桥接会动态发现本地进程端口和临时令牌，不再在源码中保存兜底令牌。未配置该部分时，定时推送仍可按各自依赖运行，但机器人的智能问答不可用。

### 私人持仓数据

基金摘要不会从源码读取真实持仓。复制模板并只在本地维护：

```powershell
Copy-Item .\data\portfolio.example.json .\data\portfolio.json
```

`data/portfolio.json` 被 Git 忽略；如需放在其他位置，设置 `PORTFOLIO_FILE`。公开模板仅用于说明数据结构，不含真实持仓，服务也不会自动生成买卖指令。

如国际资讯源必须经过本地代理，可设置：

```dotenv
LOCAL_PROXY=http://127.0.0.1:7890
```

行情接口默认使用 `https://hq.sinajs.cn`，如需替换为其他兼容数据源，可设置 `MARKET_DATA_URL`。

## 飞书机器人

前台调试：

```powershell
python main.py bot
```

后台启动：

```powershell
wscript.exe .\run_bot_silent.vbs
```

VBS 脚本会从自身位置推导项目目录，并调用 `PATH` 中的 `pythonw.exe` 启动服务。若使用虚拟环境，Windows 计划任务中更稳妥的方式是直接把“程序”设为虚拟环境的 `python.exe`，参数设为项目绝对路径下的 `main.py bot`，并把“起始于”设为仓库根目录。

根目录的 `启动飞书机器人.bat` 与 `停止飞书机器人.bat` 会管理匹配的后台进程。停止脚本会强制结束进程，运行前请确认没有其他同名服务。

## Windows 计划任务

`scripts/` 中提供了各服务的批处理入口。创建任务时建议：

1. 使用当前仓库的绝对路径作为“起始于”目录；
2. 使用虚拟环境中的 Python；
3. 勾选“仅在用户登录时运行”开始调试；
4. 先手动运行一次并检查 `logs/`；
5. 不要把 `.env` 内容写入任务参数或日志。

计划任务属于本机状态，不会随 Git 仓库同步。

## 目录结构

```text
MorningBriefAgent/
├─ core/                 # 配置、飞书 API、日历、邮件解析、AGY 桥接
├─ services/             # 晨报、聊天、资讯、健身、基金、待办与复盘
├─ server/               # 飞书 WebSocket 长连接机器人
├─ scripts/              # Windows 调度与后台启动脚本
├─ tests/                # 离线单元测试与显式运行的手工集成检查
├─ data/                 # 本地运行状态，仅提交 .gitkeep
├─ logs/                 # 本地日志，仅提交 .gitkeep
├─ received_images/      # 飞书图片缓存，仅提交 .gitkeep
├─ .env.example          # 脱敏配置模板
├─ requirements.txt
└─ main.py               # 统一 CLI
```

`tests/manual_*.py` 和 `tests/check_*.py` 会访问本地服务、数据库或真实 Vault，只能手动运行，不属于默认单元测试。

## 安全与隐私

- `.env`、日志、运行时 JSON/数据库和接收图片均被 `.gitignore` 拦截；
- 源码不提供任何真实飞书凭据或个人 ID 的默认值；
- 飞书入站消息在调用本地工具前执行 Open ID 白名单校验；
- 日志不记录完整消息正文，但运行过程中仍会处理私人数据；
- 本项目没有为本地数据库、图片和 Obsidian 内容提供加密存储；
- 删除本地运行数据前，请自行确认备份与数据保留要求。

开源前仍应执行：

```powershell
git check-ignore -v .env logs\example.log data\example.json received_images\example.png
git grep -n -I -E "FEISHU_APP_SECRET=.+|cli_[A-Za-z0-9]{12,}|ou_[A-Za-z0-9]{12,}|oc_[A-Za-z0-9]{12,}"
```

如果凭据曾出现在源码、终端分享、聊天或截图中，仅仅删除字符串不够；请在飞书后台轮换 App Secret。

## 已知限制

- 部分业务模块仍依赖 Obsidian、微信和飞书的数据格式，需要按本地环境适配；
- 微信数据库模式并非稳定公共接口，版本升级后可能失效；
- 新闻和行情依赖第三方公开源，缺少缓存、重试和数据源健康监控；
- AGY 桥接依赖本地进程与转录日志，不是稳定的公开 SDK；
- 当前测试主要覆盖配置与泄密防线，核心业务缺少隔离后的单元测试；
- 缺少容器化、结构化配置校验、持久化迁移和完整的故障恢复机制；
- 采用 MIT License，可自由使用、修改与分发，但需保留版权与许可声明。

## 适合贡献的方向

- 继续将数据目录、时间规则和领域模块抽象为可替换配置；
- 为飞书、新闻和行情接口增加 mock 测试；
- 把微信数据读取封装为可替换适配器；
- 增加配置诊断命令，例如 `python main.py doctor`；
- 增加失败重试、指标、健康检查与结构化日志；
- 补充 Linux/macOS 调度方式，降低 Windows 绑定。

## 免责声明

健身、营养和投资相关输出仅用于个人信息整理，不构成医疗、营养或投资建议。任何自动创建、修改或删除飞书任务、日历和 Obsidian 文件的功能，都应先在测试账号和备份数据上验证。

## License

本项目采用 [MIT License](LICENSE)。
