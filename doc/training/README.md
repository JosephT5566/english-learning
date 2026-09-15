# Training Documentation

This directory is the persistent learning context for turning English Learning into a
production-style multilingual full-stack application.

## Start here

1. Read [`project-memory.md`](project-memory.md) to identify the active milestone, issue, evidence
   level, and single next action.
2. Read the active issue index or ticket when it affects the task.
3. Read only the relevant section of [`full-stack-backend-plan.md`](full-stack-backend-plan.md) when
   roadmap scope, sequencing, milestone criteria, or the definition of done matters.
4. Choose one acceptance boundary and define its requirements, invariants, failure behavior, and
   verification path.

Prompt recipes and the optional GitHub automation path are in
[`session-workflow.md`](session-workflow.md). They are not startup context.

## Document roles

- [`project-memory.md`](project-memory.md): bounded current-state index, active issue, remaining gaps,
  and one next action
- [`full-stack-backend-plan.md`](full-stack-backend-plan.md): roadmap, scope, milestones, and completion
  criteria; load by section
- [`evidence.md`](evidence.md): verified implementation evidence for interviews and later resume work;
  load only for evidence tasks
- [`current-state-flow-trace.md`](current-state-flow-trace.md): Issue #4 legacy auth, vocabulary,
  review, Sheet contract, and trust-boundary baseline
- [`issues/`](issues/): canonical per-ticket design, implementation, verification, and milestone
  artifacts
- [`logs/`](logs/): chronological learning archive, searched on demand rather than loaded at startup
- [`decisions/`](decisions/): records for consequential architectural choices
- [`fixtures/`](fixtures/): sanitized synthetic contract and migration datasets

Inactive product proposals live under [`../product/`](../product/).

## Source and update rules

- Treat implementation and test results as authoritative; plans and memory can become stale.
- Update the plan only when scope or sequencing changes.
- Keep project memory concise. Summarize completed milestones in one or two lines and link to their
  issue indexes instead of copying detailed history.
- Distinguish `repository-verified`, `operator-reported`, and `unverified` production claims.
- Keep one active milestone, one set of remaining gaps, and one next action in project memory.
- Use one log per ISO week. Add a concise checkpoint only for a completed acceptance boundary or a
  material decision, failure, correction, or uncertainty.
- Do not load weekly logs at startup. Search the smallest relevant excerpt for explicit history,
  retrospectives, unresolved conflicts, or otherwise unavailable evidence.
- Add evidence only after implementation exists and relevant verification has run. Link it to code,
  tests, issues, pull requests, reports, or measurements.
- Create an architecture decision record only for a consequential choice with credible alternatives.
- Keep private career notes, credentials, tokens, and private learning data out of the repository.

## End a training session

1. Run checks proportional to the change and record actual results.
2. If warranted, append one concise checkpoint after inspecting only the relevant log tail or entry.
3. Update project memory when the active state or next action changed.
4. Add evidence only for outcomes that are implemented, verified, and defensible.
