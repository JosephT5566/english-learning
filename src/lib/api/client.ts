import type { components } from "./generated";
import { env } from "$env/dynamic/public";
import { getTokenIfValid, isCurrentToken, signOut } from "$lib/auth";
import {
  isCardDraft,
  type CardDraft,
  JSON_CARD_LIMIT,
} from "$lib/management/json-cards";
import {
  isApiErrorEnvelope,
  isCardDetail,
  isCardSummaryPage,
  isDeck,
  isDeckPage,
  isDueCardPage,
  isReviewResult,
  isSemanticSearchResponse,
  type ArchiveStatus,
  type ApiErrorBody,
  type CardDetail,
  type CardCreate,
  type CardBulkCreate,
  type CardSummary,
  type CardSort,
  type CardUpdate,
  type Deck,
  type DeckCreate,
  type DeckUpdate,
  type DueCard,
  type Page,
  type ReviewResult,
  type ReviewSubmission,
  type SemanticSearchRequest,
  type SemanticSearchResponse,
  type TargetLanguage,
} from "./contracts";

type ApiFailureKind =
  | "configuration"
  | "authentication"
  | "network"
  | "api"
  | "invalid_response";

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly kind: ApiFailureKind,
    readonly retryable: boolean,
    readonly status?: number,
    readonly code?: string,
    readonly requestId?: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

function endpoint(path: string): string {
  const base = (env.PUBLIC_API_BASE_URL ?? "").trim().replace(/\/+$/, "");
  if (!base) {
    throw new ApiClientError(
      "The API is not configured.",
      "configuration",
      false,
    );
  }
  return `${base}${path}`;
}

async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function authenticatedResponse(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = getTokenIfValid();
  if (!token) {
    throw new ApiClientError(
      "Please sign in again.",
      "authentication",
      false,
      401,
    );
  }

  const url = endpoint(path);
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {
        ...init.headers,
        Authorization: `Bearer ${token}`,
      },
    });
  } catch (cause) {
    if (init.signal?.aborted) throw cause;
    throw new ApiClientError(
      "We could not reach the service. The result is not confirmed yet.",
      "network",
      true,
    );
  }

  if (!response.ok) {
    const data = await parseJson(response);
    const error: ApiErrorBody = isApiErrorEnvelope(data)
      ? data.error
      : {
          code: "invalid_error_response",
          message: "The review service returned an unexpected error response.",
          retryable: response.status >= 500,
          request_id: response.headers.get("X-Request-ID") ?? "",
        };
    if (response.status === 401 && isCurrentToken(token)) signOut();
    throw new ApiClientError(
      error.message,
      response.status === 401 ? "authentication" : "api",
      error.retryable || response.status >= 500,
      response.status,
      error.code,
      error.request_id,
      error.details,
    );
  }
  return response;
}

async function authenticatedRequest(
  path: string,
  init?: RequestInit,
): Promise<unknown> {
  return parseJson(await authenticatedResponse(path, init));
}

export type AssistantMessage = components["schemas"]["Message"];
type AssistantStop = components["schemas"]["AssistantResponse"]["stop_reason"];
export type AssistantTool = Pick<
  components["schemas"]["ToolCallSummary"],
  "name" | "status"
>;

export type AssistantPart = {
  id: string;
  type: "card_list";
  payload: {
    purpose: "due" | "search";
    items: { id: string; deck_id: string; term: string; meaning: string }[];
  };
};

function hasExactKeys(
  value: unknown,
  keys: string[],
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isAssistantPart(value: unknown): value is AssistantPart {
  if (
    !hasExactKeys(value, ["id", "type", "payload"]) ||
    typeof value.id !== "string" ||
    value.type !== "card_list"
  )
    return false;
  const payload = value.payload;
  return (
    hasExactKeys(payload, ["purpose", "items"]) &&
    (payload.purpose === "due" || payload.purpose === "search") &&
    Array.isArray(payload.items) &&
    payload.items.every(
      (item: unknown) =>
        hasExactKeys(item, ["id", "deck_id", "term", "meaning"]) &&
        typeof item.id === "string" &&
        typeof item.deck_id === "string" &&
        typeof item.term === "string" &&
        typeof item.meaning === "string",
    )
  );
}

function invalidAssistantStream(): ApiClientError {
  return new ApiClientError(
    "The assistant response was interrupted.",
    "invalid_response",
    true,
  );
}

export async function streamAssistantReply(
  messages: AssistantMessage[],
  onText: (text: string) => void,
  signal: AbortSignal,
  options?: {
    capabilities?: "parts.v1"[];
    onPart?: (part: AssistantPart) => void;
  },
): Promise<{ stop: AssistantStop; tools: AssistantTool[] }> {
  const response = await authenticatedResponse(
    "/v1/assistant/messages/stream",
    {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        messages,
        ...(options?.capabilities?.length
          ? { capabilities: options.capabilities }
          : {}),
      } satisfies Omit<
        components["schemas"]["AssistantStreamRequest"],
        "capabilities"
      > &
        Partial<
          Pick<components["schemas"]["AssistantStreamRequest"], "capabilities">
        >),
      signal,
    },
  );
  const contentType = response.headers
    .get("Content-Type")
    ?.split(";")[0]
    ?.trim();
  if (!response.body || contentType !== "text/event-stream")
    throw invalidAssistantStream();

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) throw invalidAssistantStream();
      buffer += value;
      let boundary = /\r?\n\r?\n/.exec(buffer);
      while (boundary) {
        const lines = buffer.slice(0, boundary.index).split(/\r?\n/);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        boundary = /\r?\n\r?\n/.exec(buffer);
        const event = lines
          .find((line) => line.startsWith("event:"))
          ?.slice(6)
          .trim();
        const data = lines
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n");
        if (!event || !data) continue;
        if (!["delta", "error", "done", "part"].includes(event)) continue;
        const payload: unknown = JSON.parse(data);
        if (typeof payload !== "object" || payload === null)
          throw invalidAssistantStream();

        if (event === "part") {
          if (!("type" in payload) || payload.type !== "card_list") continue;
          if (!isAssistantPart(payload)) throw invalidAssistantStream();
          options?.onPart?.(payload);
          continue;
        }
        if (
          event === "delta" &&
          "text" in payload &&
          typeof payload.text === "string"
        ) {
          onText(payload.text);
          continue;
        }
        if (
          event === "error" &&
          "code" in payload &&
          typeof payload.code === "string" &&
          "message" in payload &&
          typeof payload.message === "string" &&
          "retryable" in payload &&
          typeof payload.retryable === "boolean"
        ) {
          throw new ApiClientError(
            payload.message,
            "api",
            payload.retryable,
            undefined,
            payload.code,
          );
        }
        if (
          event === "done" &&
          "stop_reason" in payload &&
          "tool_calls" in payload &&
          (payload.stop_reason === "completed" ||
            payload.stop_reason === "max_steps" ||
            payload.stop_reason === "timeout") &&
          Array.isArray(payload.tool_calls)
        ) {
          const tools = payload.tool_calls.map((tool: unknown) => {
            if (
              typeof tool !== "object" ||
              tool === null ||
              !("name" in tool) ||
              typeof tool.name !== "string" ||
              !("status" in tool)
            )
              throw invalidAssistantStream();
            switch (tool.status) {
              case "ok":
              case "invalid_call":
              case "too_many_calls":
              case "tool_unavailable":
              case "tools_disabled":
              case "timeout":
                return { name: tool.name, status: tool.status };
              default:
                throw invalidAssistantStream();
            }
          });
          return { stop: payload.stop_reason, tools };
        }
        throw invalidAssistantStream();
      }
    }
  } catch (cause) {
    if (signal.aborted || cause instanceof ApiClientError) throw cause;
    throw invalidAssistantStream();
  } finally {
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

function queryString(
  values: Record<string, string | number | null | undefined>,
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined) query.set(key, String(value));
  }
  return query.toString();
}

export async function getDecks(
  targetLanguage: TargetLanguage,
  status: ArchiveStatus = "active",
  limit = 20,
  cursor?: string,
): Promise<Page<Deck>> {
  const query = queryString({
    target_language: targetLanguage,
    status,
    limit,
    cursor,
  });
  const data = await authenticatedRequest(`/v1/decks?${query}`);
  if (!isDeckPage(data)) {
    throw new ApiClientError(
      "The deck list response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function getDeck(deckId: string): Promise<Deck> {
  const data = await authenticatedRequest(
    `/v1/decks/${encodeURIComponent(deckId)}`,
  );
  if (!isDeck(data)) {
    throw new ApiClientError(
      "The deck response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function getCards(
  deckId: string,
  status: ArchiveStatus = "active",
  limit = 20,
  cursor?: string,
  sort: CardSort = "updated_at",
): Promise<Page<CardSummary>> {
  const query = queryString({
    deck_id: deckId,
    status,
    limit,
    cursor,
    sort: sort === "updated_at" ? undefined : sort,
  });
  const data = await authenticatedRequest(`/v1/cards?${query}`);
  if (!isCardSummaryPage(data)) {
    throw new ApiClientError(
      "The card list response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function keywordSearch(
  queryText: string,
  limit = 100,
): Promise<Page<CardSummary>> {
  const query = queryString({ query: queryText, status: "active", limit });
  const data = await authenticatedRequest(`/v1/cards?${query}`);
  if (!isCardSummaryPage(data)) {
    throw new ApiClientError(
      "The search response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function getCard(cardId: string): Promise<CardDetail> {
  const data = await authenticatedRequest(
    `/v1/cards/${encodeURIComponent(cardId)}`,
  );
  if (!isCardDetail(data)) {
    throw new ApiClientError(
      "The card response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function createDeck(
  payload: DeckCreate,
  idempotencyKey: string,
): Promise<Deck> {
  const data = await authenticatedRequest("/v1/decks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!isDeck(data))
    throw new ApiClientError(
      "The created deck response was invalid.",
      "invalid_response",
      true,
    );
  return data;
}

export async function updateDeck(
  deckId: string,
  payload: DeckUpdate,
): Promise<Deck> {
  const data = await authenticatedRequest(
    `/v1/decks/${encodeURIComponent(deckId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!isDeck(data))
    throw new ApiClientError(
      "The updated deck response was invalid.",
      "invalid_response",
      true,
    );
  return data;
}

export async function archiveDeck(deckId: string): Promise<void> {
  await authenticatedRequest(`/v1/decks/${encodeURIComponent(deckId)}`, {
    method: "DELETE",
  });
}

export async function createCard(
  payload: CardCreate,
  idempotencyKey: string,
): Promise<CardDetail> {
  const data = await authenticatedRequest("/v1/cards", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!isCardDetail(data))
    throw new ApiClientError(
      "The created card response was invalid.",
      "invalid_response",
      true,
    );
  return data;
}

export async function createCards(
  deckId: string,
  payload: CardBulkCreate,
): Promise<CardDetail[]> {
  const data = await authenticatedRequest(
    `/v1/decks/${encodeURIComponent(deckId)}/cards/bulk`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (
    !data ||
    typeof data !== "object" ||
    !("cards" in data) ||
    !Array.isArray(data.cards) ||
    data.cards.length !== payload.cards.length ||
    !data.cards.every(
      (item, index) =>
        item &&
        typeof item === "object" &&
        item.idempotency_key === payload.cards[index].idempotency_key &&
        isCardDetail(item.card) &&
        item.card.deck.id === deckId,
    ) ||
    new Set(data.cards.map((item) => item.card.id)).size !== data.cards.length
  )
    throw new ApiClientError(
      "The created cards response was invalid.",
      "invalid_response",
      true,
    );
  return data.cards.map((item) => item.card);
}

export async function validateCardDrafts(
  deckId: string,
  payload: unknown,
): Promise<CardDraft[]> {
  const data = await authenticatedRequest(
    `/v1/decks/${encodeURIComponent(deckId)}/card-drafts/validate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  const requestCards =
    payload && typeof payload === "object" && "cards" in payload
      ? payload.cards
      : null;
  if (
    !Array.isArray(requestCards) ||
    !data ||
    typeof data !== "object" ||
    !("cards" in data) ||
    !Array.isArray(data.cards) ||
    data.cards.length < 1 ||
    data.cards.length > JSON_CARD_LIMIT ||
    data.cards.length !== requestCards.length ||
    !data.cards.every(isCardDraft)
  ) {
    throw new ApiClientError(
      "The draft response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data.cards;
}

export async function updateCard(
  cardId: string,
  payload: CardUpdate,
): Promise<CardDetail> {
  const data = await authenticatedRequest(
    `/v1/cards/${encodeURIComponent(cardId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  if (!isCardDetail(data))
    throw new ApiClientError(
      "The updated card response was invalid.",
      "invalid_response",
      true,
    );
  return data;
}

export async function archiveCard(cardId: string): Promise<void> {
  await authenticatedRequest(`/v1/cards/${encodeURIComponent(cardId)}`, {
    method: "DELETE",
  });
}

export async function getDueReviews(
  targetLanguage: TargetLanguage,
  limit = 10,
): Promise<Page<DueCard>> {
  const query = new URLSearchParams({
    target_language: targetLanguage,
    limit: String(limit),
  });
  const data = await authenticatedRequest(`/v1/reviews/due?${query}`);
  if (!isDueCardPage(data)) {
    throw new ApiClientError(
      "The due-review response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function submitReviews(
  payload: ReviewSubmission,
  idempotencyKey: string,
): Promise<ReviewResult> {
  const data = await authenticatedRequest("/v1/reviews", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(payload),
  });
  if (!isReviewResult(data)) {
    throw new ApiClientError(
      "The review result was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

export async function semanticSearch(
  payload: SemanticSearchRequest,
): Promise<SemanticSearchResponse> {
  const data = await authenticatedRequest("/v1/cards/semantic-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!isSemanticSearchResponse(data)) {
    throw new ApiClientError(
      "The search response was invalid.",
      "invalid_response",
      true,
    );
  }
  return data;
}

type GenAIConsent = components["schemas"]["GenAIConsentResponse"];

async function requestGenAIConsent(
  method: "GET" | "PUT" | "DELETE",
): Promise<GenAIConsent> {
  const data = await authenticatedRequest("/v1/me/genai-consent", { method });
  if (
    !data ||
    typeof data !== "object" ||
    !("genai_consent_at" in data) ||
    !(
      data.genai_consent_at === null ||
      (typeof data.genai_consent_at === "string" &&
        Number.isFinite(Date.parse(data.genai_consent_at)))
    )
  ) {
    throw new ApiClientError(
      "The consent response was invalid.",
      "invalid_response",
      true,
    );
  }
  return { genai_consent_at: data.genai_consent_at };
}

export function getGenAIConsent(): Promise<GenAIConsent> {
  return requestGenAIConsent("GET");
}

export function grantGenAIConsent(): Promise<GenAIConsent> {
  return requestGenAIConsent("PUT");
}

export function withdrawGenAIConsent(): Promise<GenAIConsent> {
  return requestGenAIConsent("DELETE");
}
