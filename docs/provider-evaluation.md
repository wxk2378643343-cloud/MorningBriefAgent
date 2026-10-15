# AGY 与 DeepSeek Provider 评测

MorningBriefAgent 的定位不是单纯的聊天机器人，而是一个业务导向型的个人 AI 协同助手：

```text
本地事实与知识库
        ↓
Agent 理解与结构化输出
        ↓
业务质量门禁与编排
        ↓
SQLite 真实状态
        ↓
飞书提醒 / Obsidian 投影 / 本地归档
```

因此，Provider 对比不能只看回复是否“像人”，还要看它是否可靠地完成业务。

## 两个 Provider 的职责定位

- AGY：适合结合本地上下文、知识库和个人工作习惯进行编排；
- DeepSeek：适合低延迟的结构化提取、批量摘要和简单分类；
- 业务层：负责校验来源、时间、事实和执行结果，不能把 Agent 的文字回复当作成功凭证。

## 运行评测

不要把 API Key 写入代码。PowerShell 中临时配置：

```powershell
$env:DEEPSEEK_API_KEY = "your-deepseek-api-key"
$env:DEEPSEEK_MODEL = "deepseek-chat"
$env:DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
python scripts/evaluate_providers.py
```

评测脚本使用固定的脱敏样本，覆盖待办、新闻和饮食三个场景。它会比较：

- 结构化输出成功率；
- 响应耗时；
- 输入、输出和总 Token；
- Provider 失败和无效 JSON；
- 业务质量门禁前后的有效结果。

DeepSeek 的 Token 使用 API 返回的真实值；AGY 当前使用本地估算值。
两者在 Token 统计口径完全一致前，只能比较趋势，不能直接比较成本。

## 当前实测结果

基于 8 个脱敏样本的本机测试：

| 指标 | DeepSeek | AGY |
| --- | ---: | ---: |
| 结构化成功率 | 8/8 | 8/8 |
| 平均响应时间 | 0.96 秒 | 10.16 秒 |
| 总 Token | 545，真实值 | 当前为估算值 |

结果不是永久基准，会受到网络、模型版本、提示词和上下文影响。

观察到的差异：

- AGY 更倾向于保留待办原始意图，回复更简洁；
- DeepSeek 会主动把“数据结构学习”等模糊任务拆成多个步骤；
- 新闻没有真实来源时，DeepSeek 通常会返回“未提供”，AGY 可能补写来源；
- 香蕉样本中，AGY 的热量结果与已确认 SQLite 事实一致；
- 两者都可能在缺少事实来源时生成看似合理的内容，因此必须经过质量门禁。

## 评测原则

1. 相同输入、相同上下文、相同结构化契约；
2. 不把个人隐私和完整知识库发送给外部 API；
3. 用已确认的 SQLite 事实作为饮食和业务结果的真值；
4. 新闻必须验证来源存在且发布时间有效；
5. 待办需要分别评估“保留原意”和“主动拆解”是否符合业务需求；
6. 最终以业务完成率和事实可靠性为主，速度和 Token 为辅。

完整离线回归测试：

```powershell
python -m unittest discover -s tests -q
```
