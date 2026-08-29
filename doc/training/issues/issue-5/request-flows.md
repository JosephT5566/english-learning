# Issue #5 Proposed Request Flows and Trust Boundaries

- Date: 2026-08-29
- Status: Approved MVP design; not implemented

## Runtime trust boundaries

```mermaid
flowchart LR
    USER[Authenticated user]

    subgraph BROWSER[Untrusted browser boundary]
        WEB[SvelteKit static frontend]
        INPUT[User content, resource IDs,<br/>decisions, versions, idempotency keys]
    end

    subgraph GOOGLE[External identity provider]
        GIS[Google Identity Services]
    end

    subgraph API[Backend security boundary]
        HTTP[FastAPI request validation]
        AUTH[Google token verification<br/>signature, issuer, audience,<br/>expiry, verified identity]
        OWNER[Owned resource lookup<br/>and authorization]
        DOMAIN[Domain validation and<br/>state-transition service]
        TX[Explicit transaction boundary]
    end

    subgraph DB[PostgreSQL integrity boundary]
        DATA[Owned learning data]
        CONSTRAINTS[FKs, checks, uniqueness,<br/>versions, immutable history]
    end

    LOGS[Structured logs<br/>safe metadata only]

    USER --> WEB
    INPUT --> WEB
    WEB -->|Bearer token and untrusted request| HTTP
    WEB <-->|Google sign-in| GIS
    AUTH -->|Verify token claims and keys| GIS
    HTTP --> AUTH
    AUTH --> OWNER
    OWNER --> DOMAIN
    DOMAIN --> TX
    TX --> DATA
    DATA --> CONSTRAINTS
    HTTP --> LOGS
    AUTH --> LOGS
    TX --> LOGS
```

Interpretation:

- Browser visibility and validation are user experience, not authorization.
- Resource IDs, content, decisions, versions, and idempotency keys are untrusted input.
- Google establishes identity; the backend separately authorizes owned resources.
- PostgreSQL constraints remain the final integrity boundary.
- Logs contain safe operational metadata rather than tokens or full private card content.

## Owned resource mutation flow

```mermaid
sequenceDiagram
    actor User
    participant Web as SvelteKit browser
    participant API as FastAPI
    participant Auth as Auth dependency
    participant Service as Domain service
    participant DB as PostgreSQL

    User->>Web: Create or modify resource
    Web->>API: Token and validated-shaped request
    API->>Auth: Verify Google token
    Auth-->>API: Internal current user
    API->>Service: Command and current user
    Service->>DB: Begin transaction

    alt Create deck or card
        Service->>DB: Resolve creation idempotency key
        Service->>DB: Insert owned resource
        opt Create card
            Service->>DB: Insert initial review state
        end
    else PATCH
        Service->>DB: Load owned resource with If-Match version
        Service->>DB: Validate state and apply changes
    else Archive or restore
        Service->>DB: Lock owned resource
        Service->>DB: Apply desired archival state
    else Tag attach, unlink, or delete
        Service->>DB: Verify common ownership
        Service->>DB: Lock affected cards in deterministic order
        Service->>DB: Apply association and version changes
    end

    alt All checks and constraints succeed
        Service->>DB: Commit
        Service-->>API: Committed resource or result
        API-->>Web: Stable success response
    else Validation, ownership, stale state, or conflict
        Service->>DB: Roll back
        API-->>Web: Stable error envelope
    else Temporary database failure
        Service->>DB: Roll back
        API-->>Web: Retryable error and request ID
    end
```

This flow makes authentication, ownership, transaction scope, constraint handling, and recovery
explicit. Card creation and initial review state are one atomic operation.

## Atomic review batch and retry flow

```mermaid
sequenceDiagram
    actor User
    participant Web as SvelteKit browser
    participant API as FastAPI
    participant Auth as Auth dependency
    participant Review as Review service
    participant DB as PostgreSQL

    User->>Web: Submit 1-10 review decisions
    Web->>API: POST /v1/reviews with token and Idempotency-Key
    API->>Auth: Verify Google token
    Auth-->>API: Internal current user
    API->>Review: Validated batch and current user
    Review->>DB: Find batch by owner and idempotency key

    alt Same key and hash already committed
        DB-->>Review: Stored batch and events
        Review-->>API: Reconstruct original result
        API-->>Web: 200 original committed response
    else Same key with different request hash
        Review-->>API: Idempotency conflict
        API-->>Web: 409 idempotency_key_reused
    else New logical batch
        Review->>DB: Begin transaction
        Review->>DB: Insert review_batches row
        Review->>DB: Lock cards and states in sorted card-ID order
        Review->>DB: Verify ownership and active card/deck state
        Review->>DB: Compare every expected_version

        alt Any card missing or inaccessible
            Review->>DB: Roll back
            API-->>Web: Non-disclosing 404
        else Any card inactive or stale
            Review->>DB: Roll back
            API-->>Web: Safe 409 conflict
        else All items valid
            Review->>Review: Capture one backend reviewed_at
            Review->>Review: Calculate corrected transitions
            Review->>DB: Insert immutable review_events
            Review->>DB: Update all review_states
            Review->>DB: Commit batch, events, and states
            API-->>Web: 200 before and after transition results
        end
    end

    opt Response lost after commit
        Web->>API: Retry same key and exact body
        API->>Review: Resolve committed batch
        Review->>DB: Read original events
        API-->>Web: 200 original committed response
    end
```

This flow supports the claim that a retried or concurrent review batch cannot produce partial
history, duplicate events, or silently overwrite a newer scheduling state.

## Deliberate exclusions

These diagrams do not present AI provider calls, queues, deployment infrastructure, or migration
execution as current runtime behavior. The future AI draft lifecycle receives a separate conceptual
flow after its states and failure behavior are finalized.
