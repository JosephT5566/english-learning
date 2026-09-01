# Project Memory

Last updated: 2026-09-01

## Product

This is Joseph's personal English learning/review app. The primary workflow is:

1. User lands on the home page.
2. User signs in with Google if not already authenticated.
3. User starts a daily review.
4. App fetches due words from a Google Sheet through a Google Apps Script endpoint.
5. User reviews swipe cards, marking remembered cards to the right and forgotten cards to the left.
6. App submits review updates back to the sheet.

The app is optimized for a small, personal learning flow rather than a public multi-user product.

An independently runnable FastAPI foundation now exists under `apps/api/`, with liveness and typed,
secret-safe startup configuration. It is not connected to the frontend or PostgreSQL yet, so the
current user experience and Google Apps Script runtime path are unchanged.

## Current User Experience

- `/` shows today's date, a welcome message, and either a Google sign-in button or a `Start` button.
- `/review` loads up to 10 words from the sheet, shuffles them, and renders `SwipeCards`.
- Cards show an English-to-Chinese direction by default.
- A card starts on the front face. The user clicks to flip it, then can drag/swipe or use action buttons on the back face.
- Review completion shows a `Submit Results` button that posts accumulated update fields to the sheet.

## Important Behavior To Preserve

- Use `$app/paths.resolve()` for route navigation so GitHub Pages base paths keep working.
- Google sign-in is client-side and stores the Google ID token plus expiration in `localStorage`.
- Sheet update requests require a valid ID token from `getTokenIfValid()`.
- Review stages are clamped between 1 and 5.
- A forgotten card decreases stage; a remembered card increases stage.

## Repo Memory Maintenance

Update this file when the product workflow changes. Update `architecture.md` when data flow, routes, module ownership, or integration contracts change. Update `decisions.md` when a durable decision or known issue is added/resolved.
