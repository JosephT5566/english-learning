# Training Session Workflow

This optional guide contains reusable prompts for working on training tickets with Codex. The
behavioral rules and current state remain in the training skill and
[`project-memory.md`](project-memory.md).

## Interactive coaching

Work on one ticket and one acceptance boundary at a time. The recommended path keeps the critical
design and implementation reasoning with Joseph.

### Start a ticket in design mode

```text
$full-stack-training-coach $github

Open issue #4:
https://github.com/JosephT5566/english-learning/issues/4

Start in design mode. Do not edit files yet. Help me work through the issue one acceptance
criterion at a time, and ask one substantial question at a time.
```

Replace the issue number and URL for the current ticket. If the training skill does not appear,
restart Codex so it rescans `.agents/skills`.

### Continue with implementation coaching

```text
$full-stack-training-coach

Continue issue #4. Give me the next smallest implementation step. Let me write the critical part,
then review my changes.
```

For a well-understood delegated boundary:

```text
$full-stack-training-coach

We have completed the design for issue #4. Implement only [specific acceptance criterion], run the
relevant checks, and explain the decisions I need to defend.
```

### Request review before fixes

```text
$full-stack-training-coach

Review my current changes against issue #4. Do not modify files yet. Identify correctness gaps,
missing evidence, and unverified acceptance criteria.
```

### Verify and publish

```text
$full-stack-training-coach $github

Verify issue #4, update project memory and the weekly log, add evidence only for verified outcomes,
and create a draft PR that closes #4.
```

## Automated `ai-ready` mode

`.github/workflows/ai-agent.yml` is in the repository and is not enabled. The maintainer reports
that `OPENAI_API_KEY` is not configured, so adding `ai-ready` does not start a run. After that
secret is configured, the file applies as documented in
[`../development.md`](../development.md#automated-issue-verification): Codex would implement the
issue, the workflow would guard the output, verify a candidate commit, and open a draft pull
request. An empty diff would create no PR. Failure or cancellation would be recorded in the Actions
summary without claiming issue completion. Human acceptance review and any pending PR workflow
approval would still be required. Agents do not merge without explicit maintainer authorization
([`../../AGENTS.md`](../../AGENTS.md#issue-first)).

Add `ai-ready` only through [issue-enhance](../../.agents/skills/issue-enhance/SKILL.md) after the
maintainer confirms the spec. It is not the default training path because it reduces the design and
implementation work Joseph performs.

Before a future enabled run can see local instruction changes, commit and push `AGENTS.md`,
`.agents/skills/`, and `doc/training/`. The remote agent cannot read local-only files.
