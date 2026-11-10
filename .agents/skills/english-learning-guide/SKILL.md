---
name: english-learning-guide
description: Use when explaining how English Learning works, tracing a study flow, or updating repository documentation after an implementation change.
---

# English Learning guide

1. Find the current behavior in [project memory](../../../doc/project-memory.md). Use the [source map](../../../doc/architecture.md) to locate the implementation.
2. Trace the user entry point through the route, component or store, and data boundary. For example, follow `/review` to the guest snapshot or through the authenticated client to the FastAPI review service. Check scheduling in the backend. Cite source files for each claim.
3. Distinguish what the repository verifies, what an operator reported, and what still needs verification. Use the [training skill](../full-stack-training-coach/SKILL.md) for training milestones and evidence.
4. If implementation changes documented behavior, update the owning document. Use project memory for current behavior, architecture for integration contracts, [development memory](../../../doc/development.md#instruction-ownership) for commands, and [decisions](../../../doc/decisions.md) for durable decisions. If auth or API contracts change, update architecture and decisions.
5. Check the changed links, file references, and formatting. When docs and implementation disagree, describe the discrepancy and the evidence.
