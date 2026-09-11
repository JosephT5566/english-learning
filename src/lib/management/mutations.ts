import { ApiClientError } from '$lib/api/client';

export interface MutationErrorCopy {
	title: string;
	message: string;
	requestId?: string;
	retryable: boolean;
	conflict: boolean;
}

export function mutationErrorCopy(error: unknown): MutationErrorCopy {
	if (!(error instanceof ApiClientError)) {
		return {
			title: 'Result not confirmed',
			message: 'Keep this page open and try the action again.',
			retryable: true,
			conflict: false,
		};
	}
	if (error.status === 409 && error.code === 'version_conflict') {
		return {
			title: 'A newer version is available',
			message: 'Your edits are still here. Reload the latest version to discard them.',
			requestId: error.requestId,
			retryable: false,
			conflict: true,
		};
	}
	if (error.status === 422) {
		return {
			title: 'Check the highlighted information',
			message: 'Some values were not accepted. Review the form and save again.',
			requestId: error.requestId,
			retryable: false,
			conflict: false,
		};
	}
	if (error.status === 401 || error.kind === 'authentication') {
		return {
			title: 'Sign in required',
			message: 'Sign in again. Your values remain on this page.',
			requestId: error.requestId,
			retryable: false,
			conflict: false,
		};
	}
	return {
		title: error.retryable ? 'Result not confirmed' : 'Changes were not saved',
		message: error.retryable
			? 'The service did not confirm the result. Try the same action again.'
			: error.message,
		requestId: error.requestId,
		retryable: error.retryable,
		conflict: false,
	};
}
