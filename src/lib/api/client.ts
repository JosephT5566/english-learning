import { env } from '$env/dynamic/public';
import { getTokenIfValid, signOut } from '$lib/auth';
import {
	isApiErrorEnvelope,
	isDueCardPage,
	isReviewResult,
	type ApiErrorBody,
	type DueCard,
	type Page,
	type ReviewResult,
	type ReviewSubmission,
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
		readonly details?: Record<string, unknown>
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
			'We could not reach the review service. Your answers are not confirmed yet.',
			'network',
			true
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
			error.details
		);
	}
	return data;
}

export async function getDueReviews(
	targetLanguage: TargetLanguage,
	limit = 10
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
	idempotencyKey: string
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
