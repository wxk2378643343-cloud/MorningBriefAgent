# MorningBriefAgent Copilot Instructions

## Project positioning

MorningBriefAgent is a business-oriented personal AI collaboration assistant.
It integrates with Feishu, reads explicitly configured local knowledge sources,
uses SQLite for structured facts and execution state, and projects verified
results to Feishu and Obsidian.

The Agent is responsible for understanding input and producing structured
proposals. The business layer is responsible for validation, orchestration,
side effects, and reporting real success or failure.

## Architecture rules

- Follow DRY and single-responsibility principles.
- Keep provider-specific code behind the Agent provider boundary.
- Keep renderers pure: rendering must not call an Agent or external service.
- Treat SQLite as the local source of truth for structured facts and status.
- Treat Feishu and Obsidian as projections that can fail and be retried.
- Use stable idempotency keys for external side effects.
- Do not claim a task, calendar event, database write, or Markdown sync
  succeeded unless the provider or storage layer confirms it.
- Prefer small, composable modules over growing façade modules.

## Data and security

- Never read, print, commit, or expose `.env`, API keys, tokens, personal
  SQLite files, private Obsidian content, chat databases, email bodies,
  received images, or AGY transcripts.
- Tests must use synthetic data, mocks, and temporary directories by default.
- Do not send personal knowledge-base content to an external API unless the
  user explicitly requests it and the data is minimized and redacted.
- Keep demo data separate from real local data.

## Development and validation

- Add or update tests with every behavior change.
- Run `python -m unittest discover -s tests -q` before proposing a merge.
- Do not weaken an existing test merely to make a change pass.
- Preserve truthful partial-failure reporting.
- For Agent output, validate schema, provenance, freshness, and business
  constraints before persistence or external synchronization.

## Git workflow

- Work on a feature branch; do not push directly to `main`.
- Keep commits focused and explain architectural changes in the PR.
- A change is complete only after CI passes and the PR is merged.
- Never commit personal runtime files or generated databases.
