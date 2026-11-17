import http from "node:http";
import { randomBytes, randomUUID } from "node:crypto";

const mode = process.env.MOCK_REVIEW_MODE ?? "ambiguous";
const port = Number(process.env.MOCK_REVIEW_PORT ?? 8001);
const origin = "http://127.0.0.1:4173";
const cardId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const japaneseCardId = "ffffffff-ffff-4fff-8fff-ffffffffffff";
const englishDeckId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const japaneseDeckId = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const requestId = "99999999-9999-4999-8999-999999999999";
const ownerData = new Map();

const sessions = new Map();
const accessTokens = new Map();
const refreshTokens = new Map();
const blockedEmails = new Set();
const reuseGraceMs = 10_000;

function fixtureUserId(subject) {
  let hash = 2166136261;
  for (const character of subject)
    hash = Math.imul(hash ^ character.charCodeAt(0), 16777619) >>> 0;
  return (hash % 2147483646) + 1;
}

function issueTokens(session) {
  const access_token = `ela_${randomBytes(32).toString("base64url")}`;
  const refresh_token = `elr_${randomBytes(32).toString("base64url")}`;
  const expiresAt = Date.now() + 900_000;
  session.idleExpiresAt = Math.min(
    session.absoluteExpiresAt,
    Date.now() + 604_800_000,
  );
  accessTokens.set(access_token, { session, expiresAt });
  refreshTokens.set(refresh_token, {
    session,
    rotatedAt: null,
    generation: session.refreshRotations,
  });
  session.currentRefresh = refresh_token;
  return {
    access_token,
    access_expires_at: new Date(expiresAt).toISOString(),
    refresh_token,
    refresh_expires_at: new Date(session.idleExpiresAt).toISOString(),
    user: { id: session.id, email: session.email },
    profile: { name: session.name, picture: session.picture },
  };
}

function revokeSession(session) {
  session.revoked = true;
  for (const [token, value] of accessTokens)
    if (value.session === session) accessTokens.delete(token);
}

function invalidAuth(response, code = "invalid_authentication", status = 401) {
  error(response, status, code, "Authentication credentials are invalid.");
}

function modeFor(request) {
  const token = request.headers.authorization?.slice("Bearer ".length) ?? "";
  return accessTokens.get(token)?.session.mode ?? "unauthorized";
}

function handleAuth(request, response) {
  const pathname = new URL(request.url ?? "/", `http://127.0.0.1:${port}`)
    .pathname;
  if (
    request.method !== "POST" ||
    (!pathname.startsWith("/v1/auth/") &&
      !pathname.startsWith("/__test__/auth/"))
  )
    return false;
  readJson(request, (body) => {
    if (pathname === "/v1/auth/session") {
      let claims;
      try {
        claims = JSON.parse(
          Buffer.from(
            String(body.credential).split(".")[1],
            "base64url",
          ).toString(),
        );
      } catch {
        invalidAuth(response);
        return;
      }
      if (
        !claims.sub ||
        !claims.email ||
        claims.iss !== "https://accounts.google.com" ||
        claims.aud !== "browser-contract-test" ||
        claims.email_verified !== true ||
        claims.exp <= Date.now() / 1000
      ) {
        invalidAuth(response);
        return;
      }
      const requestMode =
        mode === "by-subject"
          ? String(claims.sub).replace("browser-test-", "")
          : mode;
      if (
        claims.email !== "browser-test@example.com" ||
        blockedEmails.has(claims.email) ||
        requestMode === "allowlist-rejected"
      ) {
        invalidAuth(response, "account_not_allowed", 403);
        return;
      }
      const id = fixtureUserId(claims.sub);
      if (!ownerData.has(id)) ownerData.set(id, { mutableCards: new Map() });
      const session = {
        data: ownerData.get(id),
        id,
        email: claims.email,
        name: claims.name ?? "Browser Test",
        picture: claims.picture ?? null,
        mode: requestMode,
        revoked: false,
        refreshRotations: 0,
        refreshRequests: [],
        refreshBarrier: null,
        accessExpired: 0,
        accountDenied: 0,
        absoluteExpiresAt: Date.now() + 2_592_000_000,
      };
      sessions.set(randomUUID(), session);
      json(response, 200, issueTokens(session));
      return;
    }
    const record = refreshTokens.get(body.refresh_token);
    const bearerToken =
      request.headers.authorization?.slice("Bearer ".length) ?? "";
    if (pathname === "/v1/auth/logout") {
      const session = record?.session ?? accessTokens.get(bearerToken)?.session;
      if (session) revokeSession(session);
      response.writeHead(204, headers({ "Cache-Control": "no-store" }));
      response.end();
      return;
    }
    if (pathname.startsWith("/__test__/auth/")) {
      if (!record) {
        invalidAuth(response);
        return;
      }
      const session = record.session;
      if (pathname.endsWith("reset-data")) {
        const data = { mutableCards: new Map() };
        ownerData.set(session.id, data);
        for (const value of sessions.values())
          if (value.id === session.id) value.data = data;
      } else if (pathname.endsWith("expire-access")) {
        for (const value of accessTokens.values())
          if (value.session === session) value.expiresAt = Date.now() - 1;
      } else if (pathname.endsWith("revoke")) revokeSession(session);
      else if (pathname.endsWith("allowlist")) {
        session.allowed = body.allowed !== false;
        if (session.allowed) blockedEmails.delete(session.email);
        else blockedEmails.add(session.email);
      } else if (pathname.endsWith("reuse-outside-grace"))
        record.rotatedAt = Date.now() - reuseGraceMs - 1;
      else if (pathname.endsWith("refresh-barrier"))
        session.refreshBarrier = [];
      else if (pathname.endsWith("release-refresh")) {
        const waiting =
          session.refreshBarrier?.splice(0, body.count ?? 1) ?? [];
        for (const release of waiting) release();
        if (body.finish) session.refreshBarrier = null;
      } else if (!pathname.endsWith("session")) {
        error(response, 404, "endpoint_not_found", "Unknown test hook.");
        return;
      }
      json(response, 200, {
        id: session.id,
        revoked: session.revoked,
        allowed: session.allowed !== false,
        refresh_rotations: session.refreshRotations,
        refresh_requests: session.refreshRequests,
        waiting_refreshes: session.refreshBarrier?.length ?? 0,
        access_expired: session.accessExpired,
        account_denied: session.accountDenied,
      });
      return;
    }
    if (pathname !== "/v1/auth/refresh") {
      error(response, 404, "endpoint_not_found", "Unknown auth endpoint.");
      return;
    }
    const attempt = record
      ? { generation: record.generation, status: null }
      : null;
    if (attempt) record.session.refreshRequests.push(attempt);
    const respond = () => {
      if (
        !record ||
        record.session.revoked ||
        record.session.idleExpiresAt <= Date.now() ||
        record.session.absoluteExpiresAt <= Date.now()
      ) {
        if (attempt) attempt.status = 401;
        invalidAuth(response, "refresh_invalid");
        return;
      }
      if (
        record.session.allowed === false ||
        blockedEmails.has(record.session.email)
      ) {
        attempt.status = 403;
        revokeSession(record.session);
        invalidAuth(response, "account_not_allowed", 403);
        return;
      }
      if (record.rotatedAt !== null) {
        if (Date.now() - record.rotatedAt <= reuseGraceMs) {
          attempt.status = 409;
          invalidAuth(response, "refresh_superseded", 409);
        } else {
          attempt.status = 401;
          revokeSession(record.session);
          invalidAuth(response, "refresh_reused");
        }
        return;
      }
      record.rotatedAt = Date.now();
      record.session.refreshRotations++;
      attempt.status = 200;
      const tokens = issueTokens(record.session);
      tokens.profile = { name: null, picture: null };
      json(response, 200, tokens);
    };
    if (record?.session.refreshBarrier)
      record.session.refreshBarrier.push(respond);
    else respond();
  });
  return true;
}

const reviewState = {
  review_stage: 1,
  ease_factor: "2.50",
  interval_days: 0,
  last_reviewed_at: null,
  next_review_at: "2026-09-10T00:00:00Z",
  version: 1,
};

function deck(language, archived = false) {
  const japanese = language === "ja";
  return {
    id: japanese ? japaneseDeckId : englishDeckId,
    title: japanese ? "日本語の基礎" : "English foundations",
    target_language: language,
    explanation_language: "zh-TW",
    archived_at: archived ? "2026-09-11T02:00:00Z" : null,
    version: archived ? 4 : 3,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-11T02:00:00Z",
  };
}

function card(language, detailed = false, archived = false) {
  const japanese = language === "ja";
  const parent = deck(language);
  const summary = {
    id: japanese ? japaneseCardId : cardId,
    deck: {
      id: parent.id,
      title: parent.title,
      target_language: parent.target_language,
      explanation_language: parent.explanation_language,
      archived_at: parent.archived_at,
    },
    term: japanese ? "学ぶ" : "resilient",
    meaning: japanese ? "to learn" : "有復原力的",
    reading: japanese ? "まなぶ" : null,
    pronunciation: japanese ? null : "/rɪˈzɪliənt/",
    romanization: japanese ? "manabu" : null,
    part_of_speech: "verb",
    archived_at: archived ? "2026-09-11T02:00:00Z" : null,
    version: 2,
    updated_at: "2026-09-11T01:00:00Z",
  };
  if (!detailed) return summary;
  return {
    ...summary,
    target_language_definition: japanese
      ? "知識や技能を身につける"
      : "able to recover quickly",
    example_sentence: japanese
      ? "毎日、日本語を学びます。"
      : "The service is resilient.",
    example_translation: japanese ? "I study Japanese every day." : null,
    example_source: null,
    synonyms: japanese ? [] : ["robust"],
    antonyms: japanese ? [] : ["fragile"],
    part_of_speech_detail: null,
    note: japanese ? "五段動詞" : null,
    supplementary_note: null,
    learned_on: "2026-09-11",
    created_at: "2026-09-01T00:00:00Z",
    tags: [
      {
        id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        display_name: "foundation",
      },
    ],
    review_state: reviewState,
  };
}

function headers(extra = {}) {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Headers":
      "Authorization, Content-Type, Idempotency-Key",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Content-Type": "application/json",
    "Access-Control-Expose-Headers": "Retry-After, X-Request-ID",
    ...extra,
  };
}

function json(response, status, body) {
  response.writeHead(
    status,
    headers({ "X-Request-ID": requestId, "Cache-Control": "no-store" }),
  );
  response.end(JSON.stringify(body));
}

function error(response, status, code, message, retryable = false, details) {
  json(response, status, {
    error: {
      code,
      message,
      retryable,
      request_id: requestId,
      ...(details ? { details } : {}),
    },
  });
}

function readJson(request, callback) {
  let raw = "";
  request.on("data", (chunk) => (raw += chunk));
  request.on("end", () => callback(JSON.parse(raw || "{}"), raw));
}

const server = http.createServer((request, response) => {
  if (request.url === "/health") {
    json(response, 200, { ok: true });
    return;
  }
  if (request.method === "OPTIONS") {
    response.writeHead(204, headers());
    response.end();
    return;
  }

  if (handleAuth(request, response)) return;

  if (!request.headers.authorization?.startsWith("Bearer ")) {
    error(
      response,
      401,
      "authentication_required",
      "Authentication is required.",
    );
    return;
  }
  const token = request.headers.authorization.slice("Bearer ".length);
  const access = token.startsWith("ela_") ? accessTokens.get(token) : null;
  if (
    !access ||
    access.session.revoked ||
    access.session.idleExpiresAt <= Date.now() ||
    access.session.absoluteExpiresAt <= Date.now()
  ) {
    invalidAuth(response);
    return;
  }
  if (
    access.session.allowed === false ||
    blockedEmails.has(access.session.email)
  ) {
    access.session.accountDenied++;
    revokeSession(access.session);
    invalidAuth(response, "account_not_allowed", 403);
    return;
  }
  if (access.expiresAt <= Date.now()) {
    access.session.accessExpired++;
    invalidAuth(response, "access_token_expired");
    return;
  }
  if (request.method === "GET" && request.url === "/v1/me") {
    json(response, 200, { id: access.session.id, email: access.session.email });
    return;
  }
  const requestMode = modeFor(request);
  if (requestMode === "unauthorized") {
    error(
      response,
      401,
      "invalid_authentication",
      "Authentication credentials are invalid.",
    );
    return;
  }
  if (requestMode === "management-unauthorized") {
    error(
      response,
      401,
      "invalid_authentication",
      "Authentication credentials are invalid.",
    );
    return;
  }
  if (requestMode === "management-retryable") {
    error(
      response,
      503,
      "database_unavailable",
      "The database is temporarily unavailable.",
      true,
    );
    return;
  }
  if (requestMode === "management-server-error") {
    error(response, 500, "internal_error", "An unexpected error occurred.");
    return;
  }

  const parsedUrl = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  if (
    request.method === "GET" &&
    parsedUrl.pathname === "/v1/me/genai-consent"
  ) {
    json(response, 200, { genai_consent_at: "2026-11-08T00:00:00Z" });
    return;
  }
  if (
    request.method === "POST" &&
    parsedUrl.pathname === "/v1/assistant/messages/stream"
  ) {
    readJson(request, () => {
      response.writeHead(200, headers({ "Content-Type": "text/event-stream" }));
      response.end(
        `event: delta\ndata: ${JSON.stringify({ text: "Recovered assistant reply." })}\n\n` +
          `event: done\ndata: ${JSON.stringify({ tool_calls: [], stop_reason: "completed", usage: null })}\n\n`,
      );
    });
    return;
  }
  if (
    requestMode === "management-write-forbidden" &&
    ["POST", "PATCH", "DELETE"].includes(request.method ?? "")
  ) {
    error(
      response,
      404,
      "card_not_found",
      "The requested resource was not found.",
    );
    return;
  }
  if (
    request.method === "POST" &&
    parsedUrl.pathname === "/v1/cards/semantic-search"
  ) {
    readJson(request, (body) => {
      json(response, 200, {
        items: [
          {
            id: cardId,
            deck_id: englishDeckId,
            term: "resilient",
            meaning: "有復原力的",
            reading: null,
            pronunciation: "/rɪˈzɪliənt/",
            romanization: null,
            part_of_speech: "adjective",
            distance: body.query === "recover after difficulty" ? 0.08 : 0.3,
            score: body.query === "recover after difficulty" ? 0.92 : 0.7,
          },
        ],
        index_status: "partial",
        eligible_count: 3,
        indexed_count: 2,
      });
    });
    return;
  }
  if (request.method === "GET" && parsedUrl.pathname === "/v1/decks") {
    if (requestMode === "management-empty") {
      json(response, 200, { items: [], next_cursor: null });
      return;
    }
    const language =
      parsedUrl.searchParams.get("target_language") === "ja" ? "ja" : "en";
    const archived = parsedUrl.searchParams.get("status") === "archived";
    const sendDecks = () =>
      json(response, 200, {
        items: [
          deck(language, archived),
          ...(access.session.data.createdDeck &&
          access.session.data.createdDeck.target_language === language &&
          !archived
            ? [access.session.data.createdDeck]
            : []),
        ],
        next_cursor: null,
      });
    if (requestMode === "management-slow") setTimeout(sendDecks, 1000);
    else sendDecks();
    return;
  }
  if (request.method === "GET" && parsedUrl.pathname.startsWith("/v1/decks/")) {
    if (requestMode === "management-not-found") {
      error(
        response,
        404,
        "deck_not_found",
        "The requested deck was not found.",
      );
      return;
    }
    const id = parsedUrl.pathname.split("/").at(-1);
    if (access.session.data.createdDeck?.id === id) {
      json(response, 200, access.session.data.createdDeck);
      return;
    }
    json(response, 200, deck(id === japaneseDeckId ? "ja" : "en"));
    return;
  }
  if (request.method === "GET" && parsedUrl.pathname === "/v1/cards") {
    const japanese = parsedUrl.searchParams.get("deck_id") === japaneseDeckId;
    const archived = parsedUrl.searchParams.get("status") === "archived";
    const dynamic = [...access.session.data.mutableCards.values()].filter(
      (item) =>
        item.deck.id === parsedUrl.searchParams.get("deck_id") &&
        Boolean(item.archived_at) === archived,
    );
    json(response, 200, {
      items: [card(japanese ? "ja" : "en", false, archived), ...dynamic],
      next_cursor: null,
    });
    return;
  }
  if (request.method === "GET" && parsedUrl.pathname.startsWith("/v1/cards/")) {
    if (requestMode === "management-not-found") {
      error(
        response,
        404,
        "card_not_found",
        "The requested card was not found.",
      );
      return;
    }
    const id = parsedUrl.pathname.split("/").at(-1);
    if (access.session.data.mutableCards.has(id)) {
      json(response, 200, access.session.data.mutableCards.get(id));
      return;
    }
    json(response, 200, card(id === japaneseCardId ? "ja" : "en", true));
    return;
  }

  if (request.method === "POST" && parsedUrl.pathname === "/v1/decks") {
    readJson(request, (payload) => {
      if (requestMode === "management-validation") {
        error(
          response,
          422,
          "validation_failed",
          "The request did not pass validation.",
        );
        return;
      }
      access.session.data.createdDeck ??= {
        ...deck(payload.target_language),
        id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        title: payload.title,
        explanation_language: payload.explanation_language,
        version: 1,
      };
      json(response, 201, access.session.data.createdDeck);
    });
    return;
  }

  if (
    request.method === "PATCH" &&
    parsedUrl.pathname.startsWith("/v1/decks/")
  ) {
    readJson(request, (payload) => {
      if (requestMode === "management-conflict") {
        error(
          response,
          409,
          "version_conflict",
          "The resource changed since it was read.",
        );
        return;
      }
      const current = deck(
        parsedUrl.pathname.endsWith(japaneseDeckId) ? "ja" : "en",
      );
      json(response, 200, {
        ...current,
        ...payload,
        version: current.version + 1,
      });
    });
    return;
  }

  if (
    request.method === "DELETE" &&
    parsedUrl.pathname.startsWith("/v1/decks/")
  ) {
    response.writeHead(204, headers());
    response.end();
    return;
  }

  if (request.method === "POST" && parsedUrl.pathname === "/v1/cards") {
    readJson(request, (payload, raw) => {
      if (requestMode === "management-validation") {
        error(
          response,
          422,
          "validation_failed",
          "The request did not pass validation.",
        );
        return;
      }
      const key = request.headers["idempotency-key"];
      if (
        requestMode === "management-ambiguous-create" &&
        !access.session.data.ambiguousCreate
      ) {
        access.session.data.ambiguousCreate = { key, raw };
      } else if (
        requestMode === "management-ambiguous-create" &&
        (access.session.data.ambiguousCreate.key !== key ||
          access.session.data.ambiguousCreate.raw !== raw)
      ) {
        error(response, 409, "idempotency_key_reused", "The retry changed.");
        return;
      }
      const japanese = payload.deck_id === japaneseDeckId;
      access.session.data.createdCard ??= {
        ...card(japanese ? "ja" : "en", true),
        id: "abababab-abab-4bab-8bab-abababababab",
        deck: card(japanese ? "ja" : "en", true).deck,
        ...payload,
        version: 1,
        created_at: "2026-09-12T00:00:00Z",
        updated_at: "2026-09-12T00:00:00Z",
        tags: [],
        review_state: reviewState,
        archived_at: null,
      };
      access.session.data.mutableCards.set(
        access.session.data.createdCard.id,
        access.session.data.createdCard,
      );
      if (
        requestMode === "management-ambiguous-create" &&
        access.session.data.ambiguousCreate.raw === raw &&
        access.session.data.ambiguousCreate.firstResponse !== false
      ) {
        access.session.data.ambiguousCreate.firstResponse = false;
        json(response, 201, { outcome: "unclear" });
        return;
      }
      json(response, 201, access.session.data.createdCard);
    });
    return;
  }

  if (
    request.method === "PATCH" &&
    parsedUrl.pathname.startsWith("/v1/cards/")
  ) {
    readJson(request, (payload) => {
      if (requestMode === "management-conflict") {
        error(
          response,
          409,
          "version_conflict",
          "The resource changed since it was read.",
        );
        return;
      }
      const id = parsedUrl.pathname.split("/").at(-1);
      const current =
        access.session.data.mutableCards.get(id) ??
        card(id === japaneseCardId ? "ja" : "en", true);
      const updated = { ...current, ...payload, version: current.version + 1 };
      access.session.data.mutableCards.set(id, updated);
      json(response, 200, updated);
    });
    return;
  }

  if (
    request.method === "DELETE" &&
    parsedUrl.pathname.startsWith("/v1/cards/")
  ) {
    const id = parsedUrl.pathname.split("/").at(-1);
    const current =
      access.session.data.mutableCards.get(id) ??
      card(id === japaneseCardId ? "ja" : "en", true);
    access.session.data.mutableCards.set(id, {
      ...current,
      archived_at: "2026-09-12T00:00:00Z",
      version: current.version + 1,
    });
    if (requestMode === "management-archive-ambiguous") response.destroy();
    else {
      response.writeHead(204, headers());
      response.end();
    }
    return;
  }

  if (request.method === "GET" && request.url?.startsWith("/v1/reviews/due")) {
    if (requestMode === "empty") {
      json(response, 200, { items: [], next_cursor: null });
      return;
    }
    const sendDueCards = () =>
      json(response, 200, {
        items: [
          {
            id: cardId,
            deck: {
              id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
              title: "English",
              target_language: "en",
              explanation_language: "zh-TW",
              archived_at: null,
            },
            term: "resilient",
            meaning: "有復原力的",
            reading: null,
            pronunciation: "/rɪˈzɪliənt/",
            romanization: null,
            part_of_speech: "adjective",
            archived_at: null,
            version: 1,
            updated_at: "2026-09-10T00:00:00Z",
            target_language_definition: "able to recover quickly",
            example_sentence: "The service is resilient to retries.",
            example_translation: null,
            example_source: null,
            synonyms: ["robust"],
            antonyms: ["fragile"],
            part_of_speech_detail: null,
            note: null,
            supplementary_note: null,
            learned_on: "2026-09-01",
            created_at: "2026-09-01T00:00:00Z",
            tags: [
              {
                id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                display_name: "backend",
              },
            ],
            review_state: reviewState,
          },
        ],
        next_cursor: null,
      });
    if (requestMode === "slow") setTimeout(sendDueCards, 1000);
    else sendDueCards();
    return;
  }

  if (request.method === "POST" && request.url === "/v1/reviews") {
    let raw = "";
    request.on("data", (chunk) => (raw += chunk));
    request.on("end", () => {
      const key = request.headers["idempotency-key"];
      if (requestMode === "submit-unauthorized") {
        error(
          response,
          401,
          "invalid_authentication",
          "Authentication credentials are invalid.",
        );
        return;
      }
      if (requestMode === "validation") {
        error(
          response,
          422,
          "validation_failed",
          "The request did not pass validation.",
        );
        return;
      }
      if (requestMode === "not-found") {
        error(
          response,
          404,
          "card_not_found",
          "The requested card was not found.",
        );
        return;
      }
      if (requestMode === "server-error") {
        error(response, 500, "internal_error", "An unexpected error occurred.");
        return;
      }
      if (requestMode === "invalid-response") {
        json(response, 200, { unexpected: true });
        return;
      }
      if (requestMode === "conflict") {
        error(
          response,
          409,
          "stale_review_state",
          "A review state changed since it was read.",
          false,
          {
            item_index: 0,
            card_id: cardId,
            expected_version: 1,
            current_version: 2,
          },
        );
        return;
      }
      if (
        (requestMode === "ambiguous" || requestMode === "retryable") &&
        !access.session.data.firstCommand
      ) {
        access.session.data.firstCommand = { key, raw };
        if (requestMode === "retryable") {
          error(
            response,
            503,
            "database_unavailable",
            "The database is temporarily unavailable.",
            true,
          );
          return;
        }
        request.socket.destroy();
        return;
      }
      if (
        (requestMode === "ambiguous" || requestMode === "retryable") &&
        access.session.data.firstCommand &&
        (access.session.data.firstCommand.key !== key ||
          access.session.data.firstCommand.raw !== raw)
      ) {
        error(
          response,
          409,
          "idempotency_key_reused",
          "Retry changed the logical command.",
        );
        return;
      }
      const payload = JSON.parse(raw);
      json(response, 200, {
        batch_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        reviewed_at: "2026-09-11T00:00:00Z",
        algorithm_version: "srs-v1",
        items: payload.items.map((item, index) => ({
          event_id: index + 1,
          card_id: item.card_id,
          decision: item.decision,
          quality: item.decision === "yes" ? 5 : 0,
          previous_state: reviewState,
          resulting_state: {
            ...reviewState,
            review_stage: item.decision === "yes" ? 2 : 1,
            interval_days: 3,
            last_reviewed_at: "2026-09-11T00:00:00Z",
            next_review_at: "2026-09-14T00:00:00Z",
            version: 2,
          },
        })),
      });
    });
    return;
  }

  error(
    response,
    404,
    "endpoint_not_found",
    "The requested endpoint was not found.",
  );
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(
    `mock review API listening on ${port} in ${mode} mode\n`,
  );
});
