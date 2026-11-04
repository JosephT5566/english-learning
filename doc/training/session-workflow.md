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

`.github/workflows/ai-agent.yml` remains in the repository. Its automatic issue-label trigger is
disabled. `ai-ready` currently only means the issue is approved for an agent to read and implement.
Adding the label does not automatically trigger any workflow. Manual `workflow_dispatch`, the job
guards, and the verification steps stay in the file. See
[`../development.md`](../development.md#automated-issue-verification). Agents do not merge without explicit maintainer authorization
([`../../AGENTS.md`](../../AGENTS.md#issue-first)).

Add `ai-ready` only through [issue-enhance](../../.agents/skills/issue-enhance/SKILL.md) after the
maintainer confirms the spec. It is not the default training path because it reduces the design and
implementation work Joseph performs.

Commit and push `AGENTS.md`, `.agents/skills/`, and `doc/training/` before a remote agent reads
those instruction changes. The remote agent cannot read local-only files.
