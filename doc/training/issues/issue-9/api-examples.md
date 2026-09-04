# Issue #9 API Examples

These examples show the stable shape; UUIDs and cursor strings are illustrative. Until Issue #10,
the API reads only the explicit temporary owner configured in code.

## Decks

```http
GET /v1/decks?target_language=ja&status=active&limit=20
```

```json
{
  "items": [
    {
      "id": "10000000-0000-0000-0000-000000000002",
      "title": "Japanese fixture deck",
      "target_language": "ja",
      "explanation_language": "zh-TW",
      "archived_at": null,
      "version": 1,
      "created_at": "2026-09-01T00:00:00Z",
      "updated_at": "2026-09-01T00:00:00Z"
    }
  ],
  "next_cursor": null
}
```

```http
GET /v1/decks/10000000-0000-0000-0000-000000000002
```

The detail response uses the same deck object without a collection wrapper.

## Cards

```http
GET /v1/cards?target_language=en&tag_id=30000000-0000-0000-0000-000000000001&limit=20
```

Card lists return compact summaries. `GET /v1/cards/{card_id}` adds the complete content, sorted tag
summaries, related-word arrays, embedded example, and current review state. English and Japanese use
the same fields; language-specific values such as `pronunciation` or `reading` are nullable.

To continue a list, resend the exact filters and limit:

```http
GET /v1/cards?target_language=en&tag_id=30000000-0000-0000-0000-000000000001&limit=20&cursor=eyJ...
```

## Due review

Repeated `deck_id` parameters define an optional deck scope:

```http
GET /v1/reviews/due?target_language=ja&deck_id=10000000-0000-0000-0000-000000000002&limit=10
```

Each item is a complete card with a non-null `review_state`. Results are earliest-due first and the
cursor retains the first page's server `as_of` instant.

## Stable failures

```http
GET /v1/decks?cursor=not-base64
```

```json
{
  "error": {
    "code": "invalid_cursor",
    "message": "The pagination cursor is invalid for this request.",
    "retryable": false,
    "request_id": "00000000-0000-0000-0000-000000000000"
  }
}
```

Database failures use `503` and code `database_unavailable` with `retryable: true`. Internal SQL,
driver exceptions, credentials, and connection details are never returned.
