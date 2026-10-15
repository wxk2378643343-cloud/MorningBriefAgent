---
applyTo: "tests/**/*.py"
---

# Test-specific instructions

- Prefer `unittest` and the existing project test helpers.
- Use mocks, temporary directories, and synthetic records.
- Do not call real Feishu, AGY, DeepSeek, email, news, or market services.
- Assert business outcomes and failure states, not implementation details.
- Include at least one partial-failure or invalid-output case for new
  external-provider behavior.
