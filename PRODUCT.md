# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Joseph is the sole current user. He uses the app as a private, personal tool for daily English and
Japanese learning and review.

The product may eventually be shared with a small number of Joseph's friends. That is a future
possibility, not a current requirement for public onboarding, broad multi-user support, or growth.

## Product Purpose

The app makes recurring vocabulary review and personal learning-card management fast, focused, and
pleasant. Success means Joseph can return each day, understand what is due, complete a review with
low friction, and maintain useful English and Japanese learning material in one place.

## Positioning

This is a personal learning workspace centered on Joseph's own vocabulary, review history, and
study habits. English and Japanese share one language-aware model and workflow rather than behaving
like separate products.

## Operating Context

- The primary ritual is a short daily review of due cards.
- A card starts on its front face and must be flipped before it can be answered by swiping or using
  the yes/no controls.
- Joseph manages decks and cards, searches English cards by meaning, and uses the same app boundary
  for English and Japanese material.
- Google sign-in establishes the identity used for private, owner-scoped learning data.
- AI-assisted authoring, when introduced, must produce a validated and editable draft rather than a
  confirmed learning card.

## Capabilities and Constraints

- Preserve the existing English review flow while the product expands into multilingual learning.
- English and Japanese share a language-aware domain model and backend.
- The current product includes daily due-card review, deck and card management, and English semantic
  search.
- Review scheduling and important state transitions are backend-owned and validated.
- Private learning data is owner-scoped. Identity, ownership, validation, and state transitions are
  enforced by the backend.
- Static deployment compatibility, including GitHub Pages-style base paths, must be retained.
- The current app is deliberately optimized for one person. Future sharing with friends remains an
  open product decision and must not silently introduce public-product complexity.

## Brand Commitments

Future refinement should preserve and improve the current interface rather than discard it. The
incumbent identity includes a calm blue atmosphere, a soft layered background, tactile card-based
interaction, editorial-style headings, and a lightweight personal tone. Specific visual-system
rules belong in the design record, not this product record.

## Evidence on Hand

- The working SvelteKit application and its current interface under `src/`.
- Product behavior and migration context in `doc/project-memory.md`.
- Architecture and integration constraints in `doc/architecture.md`.
- Existing English and Japanese learning data in the authenticated backend.
- No testimonials, public customer claims, growth metrics, or public-brand proof are established;
  future design work must not fabricate them.

## Product Principles

1. Make the daily review easy to begin and satisfying to finish.
2. Protect the established review behavior while improving its clarity and craft.
3. Keep English and Japanese inside one coherent learning product.
4. Treat personal learning data and generated content with explicit ownership and validation.
5. Add complexity only when Joseph's real use or deliberate sharing requires it.

