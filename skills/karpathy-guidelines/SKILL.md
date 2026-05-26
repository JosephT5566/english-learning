---
name: karpathy-guidelines
description: Behavioral guidelines for this SvelteKit English-learning app. Use when writing, reviewing, or refactoring code to avoid overcomplication, keep changes surgical, surface assumptions, and verify with project checks.
license: MIT
---

# Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

This project is a SvelteKit 2 / Svelte 5 English-learning app. Apply these guidelines with the existing app structure in mind:
- Routes live in `src/routes`.
- Shared UI lives in `src/lib/components`.
- API-facing helpers live in `src/lib/api`.
- Shared state lives in `src/lib/stores`.
- Shared types live in `src/lib/types.ts`.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them; don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

For this project:
- Check whether the requested behavior belongs in a route, a reusable component, a store, or an API helper before editing.
- Treat English-learning quiz/review flows as user-facing behavior. Confirm ambiguous scoring, card ordering, or progress rules before changing them.
- Preserve existing data contracts in `src/lib/types.ts` unless the task explicitly requires a model change.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

For this project:
- Prefer Svelte's built-in reactivity and existing stores over adding new state machinery.
- Keep component changes local when a route-only fix is enough.
- Reuse existing utilities, components, and styling patterns before introducing new ones.
- Avoid new dependencies unless the task clearly needs them.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it; don't delete it.

When your changes create orphans:
- Remove imports, variables, functions, or components that your changes made unused.
- Don't remove pre-existing dead code unless asked.

For this project:
- Do not rewrite unrelated Svelte components while fixing a single interaction.
- Keep API changes in `src/lib/api` compatible with the calling routes/components.
- Respect existing workflow files, deployment setup, and static adapter configuration unless the task is about deployment.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" -> "Write or identify checks for invalid inputs, then make them pass."
- "Fix the bug" -> "Reproduce the failure, then make the same path pass."
- "Refactor X" -> "Ensure behavior and project checks pass before and after."

For multi-step tasks, state a brief plan:
```
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Use the project's verification commands based on risk:
- `npm run check` for Svelte and TypeScript correctness.
- `npm run lint` for formatting and lint rules.
- `npm run build` for production build and adapter behavior.

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
