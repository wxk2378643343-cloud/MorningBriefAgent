---
applyTo: "core/agent/**/*.py"
---

# Agent-boundary instructions

- Keep Provider adapters small and replaceable.
- Return structured contracts where the business workflow needs structured
  data.
- Preserve provider usage metadata without exposing credentials.
- Never let an Agent response alone mark a Feishu, SQLite, or Obsidian side
  effect as successful.
- Keep prompt construction and response validation separate where practical.
