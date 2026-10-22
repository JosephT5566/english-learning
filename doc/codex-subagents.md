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
After implementation finishes, use reviewer to check the diff against HEAD.
Have reviewer use Chrome DevTools MCP to inspect the affected browser flow.
Wait for dependent steps and summarize the results. Do not commit or deploy.
```

Give each writer its own worktree or non-overlapping file ownership. Give the reviewer
the actual worktree, comparison base, acceptance criteria, and local test URL when relevant.
Coordinate browser use so agents do not control the same tab concurrently.

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
tokens or private learning content in committed evidence. A blocked required check yields
FAIL with the blocker. Review does not authorize production writes, deployment, or merge.

See the [official custom-agent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents)
for the file format and inheritance rules. Verification commands and their applicability
remain owned by [`AGENTS.md`](../AGENTS.md) and [`development.md`](development.md).
