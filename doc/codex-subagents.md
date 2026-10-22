# Use repository Codex subagents

This repository adapts the planner, worker, and reviewer roles from the sibling
`freelance` repository. Their definitions live in [`.codex/agents/`](../.codex/agents/).

| Agent      | Job                                                                                               |
| ---------- | ------------------------------------------------------------------------------------------------- |
| `planner`  | Read code and return scoped steps, dependencies, verification, and risks without edits or builds. |
| `worker`   | Implement the assigned task and run the checks required by `AGENTS.md`.                           |
| `reviewer` | Independently inspect the diff and affected behavior, then return PASS or FAIL with evidence.     |

[`.codex/config.toml`](../.codex/config.toml) enables agents and caps concurrently open
subagent threads at three, excluding the parent. Models and reasoning effort are omitted
so parent settings apply unless the spawn request or applicable defaults supply them.
Agents inherit the parent's permissions and MCP servers. Planner and reviewer instructions
prohibit source edits but do not create a separate read-only sandbox.

Start a new Codex chat in this trusted repository after changing the configuration.
Request the roles explicitly, for example:

```text
Use planner to investigate this task, then worker to implement the plan.
Before implementation, record the current commit as the review base.
After implementation finishes, use reviewer to check all assigned changes against that base.
Have reviewer use Chrome DevTools MCP to inspect the affected browser flow.
Wait for dependent steps and summarize the results. Do not commit or deploy.
```

Give each writer its own worktree or non-overlapping file ownership. Give the reviewer
the actual worktree, comparison base, acceptance criteria, and local test URL when relevant.
Coordinate browser use so agents do not control the same tab concurrently.

## Select the roles the task needs

Follow the current session's delegation permissions and any explicit user instructions.
The examples below guide role selection; they do not require every task to use subagents.

| Task                                                                                       | Suggested workflow                                                                           |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Small, well-understood change with a clear local check                                     | Let the parent implement and verify directly.                                                |
| Unclear scope, competing approaches, or changes across domain or API boundaries            | Use planner before implementation.                                                           |
| Bounded implementation with known acceptance criteria                                      | Assign worker directly; a planner is optional.                                               |
| Auth, ownership, persistence, concurrency, API contracts, or substantial user-flow changes | Arrange an independent reviewer after implementation.                                        |
| Documentation or routine configuration changes                                             | Parent verification is usually sufficient unless a separate review is requested or required. |

The parent owns scope, dispatch, dependency order, and the final report. It can also implement
the task itself and assign reviewer. Never count the implementer's self-check as independent review.
If an independent review is required but unavailable, report that blocker and do not claim the
change passed review. Passing tests alone does not satisfy a required independent review.

Keep planner, worker, and reviewer as the default role set. Add a specialized role only when
repeated tasks show a responsibility these roles cannot handle effectively.

## Provide a concrete handoff

Supply the following information in each dispatch. Use file paths and focused context instead
of copying the full repository history. The receiving agent can inspect missing observable facts;
unresolved scope or authorization questions go back to the parent.

### Planner handoff

Give planner the requested outcome, known constraints, relevant entry points, and unresolved
decisions. Its plan must identify affected files and symbols, dependencies, acceptance criteria,
and checks selected from `AGENTS.md`. State which steps can run independently and which must wait.
Separate observed behavior, assumptions, and questions that require the user's judgment.

### Worker handoff

Give worker the following information before it edits:

- The intended outcome and observable acceptance criteria.
- The absolute checkout path and assigned files or directories. Identify existing changes to preserve.
- The approved approach or planner output, when available, plus explicit exclusions.
- Dependencies that must finish first and any shared files another writer owns.
- Applicable verification requirements, available local services, and known environment limits.
- Whether commits or branch integration are assigned. Production actions retain their existing authorization requirements.

Assign separate worktrees or non-overlapping files to concurrent writers. Shared generated artifacts
also need an owner. Sequence dependent edits rather than allowing concurrent writes to the same file.

On completion, worker returns changed files, implemented acceptance criteria, exact checks and
results, skipped checks with reasons, and remaining risks. Identify the checkout, any commits,
and uncommitted changes, including untracked files. Do not describe incomplete or blocked checks as passed.

### Reviewer handoff

Give reviewer the following information before review:

- The absolute checkout path and a resolved comparison commit, plus the branch or commit under review.
- Whether the target includes committed, staged, unstaged, or untracked changes. Name the assigned scope and unrelated changes to exclude.
- The requested outcome and acceptance criteria, with relevant design decisions.
- The worker's changed-file summary, checks, results, and known limitations as context to verify independently.
- For affected browser flows, the local URL, server startup instructions, test-data setup, and required desktop and mobile scenarios.
- Available browser tools and ownership of the review tab. Use disposable fixtures for write flows.

Record the reviewed commit and any uncommitted target changes in the review report. Pause edits to
the target during review. If the target changes, identify what needs another review before relying
on the earlier verdict. A bare `HEAD` comparison does not include changes already committed at `HEAD`;
choose a base that includes the complete intended diff.

## Report review verdicts and follow-up

Start the report with `PASS` or `FAIL`.

- Use `PASS` when the assigned acceptance criteria and required checks are satisfied and no actionable defects remain.
- Use `FAIL` with reason `defect` when evidence shows incorrect behavior or an unmet requirement.
- Use `FAIL` with reason `blocked verification` when a required check cannot run or required evidence is missing.
- Report both reasons when defects and blocked verification coexist. A blocked check does not establish a code defect or a passing result.

For each defect, provide priority, file and line, evidence, and the required correction.
For each blocked check, name the check, blocker, and prerequisite for resuming it. An unavailable
database or browser tool does not need an invented source-code location. Report exact commands,
observed results, skipped checks with reasons, and remaining evidence limits for either verdict.

The parent assesses findings against the requirements, assigns corrections, and returns the changed
target for review when required. For environment blockers, restore the prerequisite and run the
missing check. Resolve routine local blockers within the authorized scope; ask the user only when
an unresolved product decision, missing access, or authorization requires their input.

## Reviewer browser access

The repository owner authorizes reviewer to use standalone Chrome DevTools MCP for
browser verification. This is an explicit exception to the Chrome plugin default for
that role. Worker retains the default Chrome plugin `browser-client` workflow.

Configure Chrome DevTools MCP in the parent Codex session and ensure its tools are
available before dispatching reviewer. This machine already had a user-level
`chrome-devtools` server at setup time on 2026-10-21. This repository does not duplicate
that machine-specific setup. Agent instructions do not install or enable an absent MCP.

For browser reviews, report observed behavior, console or network findings, and checks
that could not run. Use local fixtures or disposable test data for writes. Do not capture
tokens or private learning content in committed evidence. Apply the review verdict rules above
when a required check is blocked. Review does not authorize production writes, deployment, or merge.

See the [official custom-agent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)
for the file format and inheritance rules. Verification commands and their applicability
remain owned by [`AGENTS.md`](../AGENTS.md) and [`development.md`](development.md).
