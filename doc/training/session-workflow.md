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

Adding the `ai-ready` label triggers `.github/workflows/ai-agent.yml`. It asks Codex to implement the
entire issue, commit the result, push a branch, and open a pull request.

Use `ai-ready` only when intentionally delegating a well-understood task or boilerplate. It is not
the default training path because it reduces the design and implementation work Joseph performs.

Before using the workflow, commit and push `AGENTS.md`, `.agents/skills/`, and `doc/training/`; the
remote agent cannot read local-only files.
