---
name: review-pr
description: Use when asked to independently review an English Learning pull request for scope, regressions, or gaps in verification.
---

# Review a pull request

1. Read the linked issue and its acceptance criteria. Identify the exact PR base and head, then inspect the complete diff and affected callers.
2. Check changed behavior against [AGENTS.md](../../../AGENTS.md). When relevant, trace backend ownership, writes and retries, generated API contracts, and static subpath routing. For review UI changes, check flip-before-answer in guest and private sessions.
3. Inspect CI for the reviewed head and run the relevant checks. Mocked browser success establishes browser behavior against fixtures. Verify persistence and ownership with the applicable disposable PostgreSQL checks.
4. Follow the [repository review verdicts](../../../doc/codex-subagents.md#report-review-verdicts-and-follow-up). Lead with the verdict. For each actionable finding, give severity, file and line, reproduction or source evidence, and the needed correction. State checks blocked by missing prerequisites separately.
5. Return findings in chat by default. If authorized to publish a review, use GitHub's comment-only review.
