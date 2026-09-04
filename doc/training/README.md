# Training Documentation

This directory is the persistent learning context for turning English Learning into a production-style multilingual full-stack application.

## Documents

- [Full-stack backend plan](full-stack-backend-plan.md): roadmap, scope, weekly milestones, and completion criteria
- [Project memory](project-memory.md): concise current state, active milestone, decisions, blockers, and next action
- [Evidence ledger](evidence.md): verified implementation evidence for interviews and future resume work
- [Current-state flow trace](current-state-flow-trace.md): issue #4 auth, vocabulary, review, Sheet contract, trust-boundary, and baseline evidence
- [`issues/`](issues/): per-ticket design and implementation artifacts grouped to keep the training root concise
- [Issue #5 multilingual backend design](issues/issue-5/README.md): completed MVP domain, API, schema, recovery, trust-boundary, AI-safety, and alternatives index
- [Issue #8 multilingual domain schema](issues/issue-8/README.md): active implementation design,
  invariants, index rationale, fixtures, and PostgreSQL verification plan
- [Issue #10 backend authentication and authorization](issues/issue-10/README.md): verified token
  boundary, internal-user mapping, owner-scoped writes, and tested authorization matrix
- [Issue #11 transactional review submissions](issues/issue-11/README.md): atomic event/state
  transitions, idempotent replay, deterministic locking, and timeout recovery
- [Issue #12 Weeks 0-3 retrospective](issues/issue-12/README.md): exit-criteria audit, final local
  verification, five-minute explanation, remaining risks, and evidence-based Weeks 4-8 tickets
- [`fixtures/`](fixtures/): sanitized synthetic datasets for future contract and migration tests
- [`logs/`](logs/): chronological weekly learning records
- [`decisions/`](decisions/): architecture decision records for consequential choices

Product proposals that are not active training priorities live under [`../product/`](../product/).

## Update rules

- Update the plan only when scope or sequencing changes.
- Update project memory after a material milestone or change of direction.
- Use one log file per ISO week; append concise session entries rather than creating one file per session.
- Record failures and corrected misunderstandings in logs because they are useful learning evidence.
- Add an evidence entry only after the implementation exists and relevant verification has run.
- Link evidence to files, tests, issues, pull requests, reports, or measurements.
- Keep private career assessments, credentials, tokens, and personal learning data out of the repository.

## Starting a training session

1. Read the project memory and the active week in the plan.
2. Choose one issue or acceptance boundary.
3. State requirements, invariants, trust boundaries, and failure behavior before coding.
4. Define how the result will be verified.

## Using GitHub tickets with Codex

Work on one training ticket at a time. The recommended path is interactive coaching, where Joseph owns the critical reasoning and implementation.

### 1. Start a ticket in design mode

Open a Codex session from this repository and explicitly invoke the training and GitHub skills:

```text
$full-stack-training-coach $github

Open issue #4:
https://github.com/JosephT5566/english-learning/issues/4

Start in design mode. Do not edit files yet. Help me work through the issue one acceptance criterion at a time, and ask one substantial question at a time.
```

Replace the issue number and URL for later tickets. If the training skill does not appear, restart Codex so it rescans `.agents/skills`.

### 2. Implement with coaching

Ask for the next bounded step while retaining ownership of the risk-heavy work:

```text
$full-stack-training-coach

Continue issue #4. Give me the next smallest implementation step. Let me write the critical part, then review my changes.
```

When delegating a well-understood portion, constrain it explicitly:

```text
$full-stack-training-coach

We have completed the design for issue #4. Implement only [specific acceptance criterion], run the relevant checks, and explain the decisions I need to defend.
```

### 3. Request a review before fixes

```text
$full-stack-training-coach

Review my current changes against issue #4. Do not modify files yet. Identify correctness gaps, missing evidence, and unverified acceptance criteria.
```

### 4. Verify and publish

```text
$full-stack-training-coach $github

Verify issue #4, update project memory and the weekly log, add evidence only for verified outcomes, and create a draft PR that closes #4.
```

### Automated `ai-ready` mode

Adding the `ai-ready` label triggers `.github/workflows/ai-agent.yml`. That workflow asks Codex to implement the entire issue, commit the result, push a branch, and open a pull request.

Use `ai-ready` only when intentionally delegating a well-understood task or boilerplate. It is not the default training path because it reduces the design and implementation work Joseph performs personally.

Before using the GitHub Action, commit and push `AGENTS.md`, `.agents/skills/`, and `doc/training/`; the remote agent cannot read local-only files.

## Ending a training session

1. Run the relevant checks.
2. Record what changed, what failed, and what remains uncertain in the weekly log.
3. Update project memory if the repository state or next action changed.
4. Add verified evidence only when the work is complete enough to defend.
