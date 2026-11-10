---
name: ui-design-gate
description: Propose UI options for this SvelteKit learning app and wait for the owner to choose one before implementation. Use when a change affects layout, visual design, copy hierarchy, or interaction in src/routes or src/lib/components.
---

# UI design gate

Do not implement a visible UI change until the owner selects one option. Record that selection in the issue decision log. A missing selection stops the work.

This app is a personal study surface, not a dashboard. Read `DESIGN.md` and the affected route or component before proposing anything. The north star there is "The Calm Card Table": cool study blue, translucent paper surfaces, one clear task, and tactile flip-and-swipe cards.

## Look at this repository

- Routes live in `src/routes` (`+page`, review, decks, cards, search) inside the shell in `src/routes/+layout.svelte` and `src/routes/Header.svelte`.
- Feature UI lives in `src/lib/components` (`SwipeCards`, `QuestionCard`, `OwnedReview`, `GuestReview`, `CardForm`, `DeckForm`, `Modal`, `Drawer`, `ConfirmDialog`, `AccountMenu`). Shared bits under `src/lib/components/ui/` are the button, alert-dialog, and sheet already in the repo.
- Newer components use Svelte 5 runes. Review and auth state use the stores in `src/lib/stores`. Styling is Tailwind utilities plus component-local CSS. Icons use `@iconify/svelte`.
- Links and navigation go through `$app/paths.resolve()` so `paths.base` / `BASE_PATH` keep working.
- Review stays flip-before-answer: the person flips a card before swiping or using the yes/no actions. English and Japanese share those screens.
- `DESIGN.md` uses one centered column (`64rem` max; search narrows to `46rem`). The review card reaches `90vw` and caps at `400px`. Two-column forms collapse at `640px`. Study Blue is the workspace color. Signal orange stays rare. Danger red is for destructive actions and errors. Shadows are for selected, actionable, or overlay surfaces. One serif heading per page; operational text stays plain.

## What to propose

Offer two or three options. Each option names:

- Which existing component or route it changes, and which existing component it reuses.
- Whether the styling stays in Tailwind utilities, component-local CSS, or both, matching the file it edits.
- How flip-before-answer, shared English/Japanese screens, `resolve()` links, and the `640px` collapse stay intact.
- What the owner would see at the review-card width and at a desktop width.

Do not introduce another visual system, component library, or icon set. Do not pick an option on the owner's behalf. Non-visual work (API, persistence, tests, docs) does not use this gate.
