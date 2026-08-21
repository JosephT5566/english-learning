# ADR 001: Evolve the Existing Repository as a Modular Monolith

- Status: Accepted
- Date: 2026-08-21

## Context

The current repository contains a working SvelteKit English-learning frontend backed by Google Apps Script and Google Sheets. The training objective is to develop full-stack and backend ownership while preserving existing behavior, adding Japanese learning, and later introducing AI-assisted card authoring.

The main alternatives were:

1. build a separate marketplace training repository
2. build a separate backend repository for English Learning
3. evolve this repository with independently deployable frontend and backend applications

## Decision

Use this repository as a modular monolith. Keep the SvelteKit frontend and planned FastAPI backend in one repository while allowing independent builds and deployments.

## Reasons

- The existing application creates a real migration and backward-compatibility problem.
- One repository keeps API contracts, migrations, tests, documentation, and change history together.
- The product provides authentic full-stack ownership evidence without requiring distributed-system complexity.
- Independent deployment boundaries preserve operational separation without requiring separate repositories or microservices.

## Consequences

- CI must eventually run frontend and backend checks independently.
- Repository documentation and local startup commands must cover both runtimes.
- The Google Sheets cutover requires explicit reconciliation and rollback behavior.
- Marketplace-specific checkout and inventory evidence will not be part of this project.
- A separate focused backend exercise may still be useful later if target roles consistently require Go or marketplace concurrency.
