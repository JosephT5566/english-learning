---
name: implement-from-issue
description: Use when asked to implement an English Learning GitHub issue with agreed acceptance criteria.
---

# Implement from an issue

1. Read the issue, decision log, and linked dependencies. Verify that the current scope and acceptance criteria match the approved revision or the user's direct instruction. If material edits supersede that approval, resolve scope before editing. Use [issue enhance](../issue-enhance/SKILL.md) when the issue needs a spec.
2. In an interactive session, check for overlapping work and use an isolated branch or worktree as appropriate. Follow the current session's Git instructions. In the [AI Agent workflow](../../../doc/development.md#automated-issue-verification), leave the working tree for the job. The job owns branch, commit, push, and PR creation.
3. Implement the agreed scope using the context and constraints in [AGENTS.md](../../../AGENTS.md). Use the approved UI design when the issue records one.
4. Match each acceptance criterion to an observed result. Run the applicable repository checks and use [verify](../verify/SKILL.md) for affected browser journeys. Use the [project guide](../english-learning-guide/SKILL.md) to route documentation changes.
5. Summarize the issue, changes, evidence per criterion, checks run, and verification gaps. If the user authorized a PR, open a draft linked to the issue with that evidence. Post a separate issue update only when authorized.
