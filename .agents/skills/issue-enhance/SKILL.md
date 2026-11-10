---
name: issue-enhance
description: Use when an English Learning issue is still an idea, lacks testable acceptance criteria, or needs scope and approval before implementation.
---

# Refine an issue

1. Read the issue, related work, and the affected source. Use [AGENTS.md](../../../AGENTS.md) to select context and verification.
2. Resolve choices that change implementation. Check which languages and session types are affected, what data changes, and what should happen on failure. Keep AI-generated card content editable until the user confirms it.
3. Draft a spec with the user outcome, current behavior and file paths, scope, exclusions, observable acceptance criteria, dependencies, verification commands, and a decision log. Use the [UI design gate](../ui-design-gate/SKILL.md) when a UI decision needs selection.
4. Show the final spec and remaining decisions to the owner. If authorized to edit the issue, record the agreed spec and identify the approved revision and approver. Keep private cards, credentials, and real tokens out of the issue.
5. Apply `ai-ready` only when the owner explicitly authorizes the automation run for that revision. The label can start an Actions job that opens a draft PR. A request to refine the issue authorizes preparation of the spec. See [automated issue verification](../../../doc/development.md#automated-issue-verification).
