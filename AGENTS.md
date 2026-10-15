# Agent instructions

## Before changing code

Read the relevant README and module tests first. Identify the business
workflow, its source of truth, its external projections, and its failure
recovery path before editing.

## Boundaries

- `core/agent/`: Agent context, provider adapters, contracts, and evaluation.
- `services/`: Business workflows and orchestration.
- `storage/`: SQLite schema, migrations, repositories, and audit state.
- `core/integrations/`: Feishu and other external provider adapters.
- `services/knowledge/`: Deterministic Obsidian projections only.
- `tests/`: Offline regression and integration-mock tests.

Do not move business decisions into renderers, transport handlers, or storage
helpers. Do not make external calls from tests unless the test is explicitly
marked as a live read-only integration.

## Completion checklist

1. Add a regression test for the changed behavior.
2. Run the full unittest suite.
3. Check `git diff --check`.
4. Review the diff for secrets and personal data.
5. Report what was changed, what was tested, and any remaining limitation.
