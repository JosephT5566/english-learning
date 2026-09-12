import { ApiClientError } from '$lib/api/client';

export interface ReadErrorCopy {
	title: string;
	message: string;
	requestId?: string;
	retryable: boolean;
}

export function readErrorCopy(
	error: unknown,
	resource: 'decks' | 'deck' | 'cards' | 'card',
): ReadErrorCopy {
	if (!(error instanceof ApiClientError)) {
		return {
			title: 'Unexpected server response',
			message: 'The latest data could not be confirmed. Try again.',
			retryable: true,
		};
	}

	if (error.status === 401 || error.kind === 'authentication') {
		return {
			title: 'Sign in required',
			message: 'Sign in again before viewing your learning library.',
			requestId: error.requestId,
			retryable: false,
		};
	}

	if (error.status === 404) {
		return {
			title: `${resource === 'deck' ? 'Deck' : 'Card'} not found`,
			message: 'It may have moved, or you may not have access to it.',
			requestId: error.requestId,
			retryable: false,
		};
	}

	return {
		title: error.retryable ? 'Service temporarily unavailable' : 'Data could not be loaded',
		message: error.retryable ? 'Your data has not changed. Try loading it again.' : error.message,
		requestId: error.requestId,
		retryable: error.retryable,
	};
}
