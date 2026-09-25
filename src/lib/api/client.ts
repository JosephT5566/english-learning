import { env } from '$env/dynamic/public';
import { getTokenIfValid, signOut } from '$lib/auth';
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
	type CardSummary,
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
} from './contracts';

type ApiFailureKind = 'configuration' | 'authentication' | 'network' | 'api' | 'invalid_response';

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
		this.name = 'ApiClientError';
	}
}

function endpoint(path: string): string {
	const base = (env.PUBLIC_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
	if (!base) {
		throw new ApiClientError('The API is not configured.', 'configuration', false);
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

async function authenticatedRequest(path: string, init: RequestInit = {}): Promise<unknown> {
	const token = getTokenIfValid();
	if (!token) {
		throw new ApiClientError('Please sign in again.', 'authentication', false, 401);
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
	} catch {
		throw new ApiClientError(
			'We could not reach the service. The result is not confirmed yet.',
			'network',
			true,
		);
	}

	const data = await parseJson(response);
	if (!response.ok) {
		const error: ApiErrorBody = isApiErrorEnvelope(data)
			? data.error
			: {
					code: 'invalid_error_response',
					message: 'The review service returned an unexpected error response.',
					retryable: response.status >= 500,
					request_id: response.headers.get('X-Request-ID') ?? '',
				};
		if (response.status === 401) signOut();
		throw new ApiClientError(
			error.message,
			response.status === 401 ? 'authentication' : 'api',
			error.retryable || response.status >= 500,
			response.status,
			error.code,
			error.request_id,
			error.details,
		);
	}
	return data;
}

function queryString(values: Record<string, string | number | null | undefined>): string {
	const query = new URLSearchParams();
	for (const [key, value] of Object.entries(values)) {
		if (value !== null && value !== undefined) query.set(key, String(value));
	}
	return query.toString();
}

export async function getDecks(
	targetLanguage: TargetLanguage,
	status: ArchiveStatus = 'active',
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
		throw new ApiClientError('The deck list response was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function getDeck(deckId: string): Promise<Deck> {
	const data = await authenticatedRequest(`/v1/decks/${encodeURIComponent(deckId)}`);
	if (!isDeck(data)) {
		throw new ApiClientError('The deck response was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function getCards(
	deckId: string,
	status: ArchiveStatus = 'active',
	limit = 20,
	cursor?: string,
): Promise<Page<CardSummary>> {
	const query = queryString({ deck_id: deckId, status, limit, cursor });
	const data = await authenticatedRequest(`/v1/cards?${query}`);
	if (!isCardSummaryPage(data)) {
		throw new ApiClientError('The card list response was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function getCard(cardId: string): Promise<CardDetail> {
	const data = await authenticatedRequest(`/v1/cards/${encodeURIComponent(cardId)}`);
	if (!isCardDetail(data)) {
		throw new ApiClientError('The card response was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function createDeck(payload: DeckCreate, idempotencyKey: string): Promise<Deck> {
	const data = await authenticatedRequest('/v1/decks', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Idempotency-Key': idempotencyKey,
		},
		body: JSON.stringify(payload),
	});
	if (!isDeck(data))
		throw new ApiClientError('The created deck response was invalid.', 'invalid_response', true);
	return data;
}

export async function updateDeck(deckId: string, payload: DeckUpdate): Promise<Deck> {
	const data = await authenticatedRequest(`/v1/decks/${encodeURIComponent(deckId)}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload),
	});
	if (!isDeck(data))
		throw new ApiClientError('The updated deck response was invalid.', 'invalid_response', true);
	return data;
}

export async function archiveDeck(deckId: string): Promise<void> {
	await authenticatedRequest(`/v1/decks/${encodeURIComponent(deckId)}`, {
		method: 'DELETE',
	});
}

export async function createCard(payload: CardCreate, idempotencyKey: string): Promise<CardDetail> {
	const data = await authenticatedRequest('/v1/cards', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Idempotency-Key': idempotencyKey,
		},
		body: JSON.stringify(payload),
	});
	if (!isCardDetail(data))
		throw new ApiClientError('The created card response was invalid.', 'invalid_response', true);
	return data;
}

export async function updateCard(cardId: string, payload: CardUpdate): Promise<CardDetail> {
	const data = await authenticatedRequest(`/v1/cards/${encodeURIComponent(cardId)}`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload),
	});
	if (!isCardDetail(data))
		throw new ApiClientError('The updated card response was invalid.', 'invalid_response', true);
	return data;
}

export async function archiveCard(cardId: string): Promise<void> {
	await authenticatedRequest(`/v1/cards/${encodeURIComponent(cardId)}`, {
		method: 'DELETE',
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
		throw new ApiClientError('The due-review response was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function submitReviews(
	payload: ReviewSubmission,
	idempotencyKey: string,
): Promise<ReviewResult> {
	const data = await authenticatedRequest('/v1/reviews', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'Idempotency-Key': idempotencyKey,
		},
		body: JSON.stringify(payload),
	});
	if (!isReviewResult(data)) {
		throw new ApiClientError('The review result was invalid.', 'invalid_response', true);
	}
	return data;
}

export async function semanticSearch(
	payload: SemanticSearchRequest,
): Promise<SemanticSearchResponse> {
	const data = await authenticatedRequest('/v1/cards/semantic-search', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(payload),
	});
	if (!isSemanticSearchResponse(data)) {
		throw new ApiClientError('The search response was invalid.', 'invalid_response', true);
	}
	return data;
}
