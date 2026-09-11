import http from 'node:http';

const mode = process.env.MOCK_REVIEW_MODE ?? 'ambiguous';
const port = Number(process.env.MOCK_REVIEW_PORT ?? 8001);
const origin = 'http://127.0.0.1:4173';
const cardId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const requestId = '99999999-9999-4999-8999-999999999999';
let firstCommand;

function modeFor(request) {
	if (mode !== 'by-subject') return mode;
	try {
		const token = request.headers.authorization?.slice('Bearer '.length) ?? '';
		const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
		return String(payload.sub).replace('browser-test-', '');
	} catch {
		return 'unauthorized';
	}
}

const reviewState = {
	review_stage: 1,
	ease_factor: '2.50',
	interval_days: 0,
	last_reviewed_at: null,
	next_review_at: '2026-09-10T00:00:00Z',
	version: 1,
};

function headers(extra = {}) {
	return {
		'Access-Control-Allow-Origin': origin,
		'Access-Control-Allow-Headers': 'Authorization, Content-Type, Idempotency-Key',
		'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
		'Content-Type': 'application/json',
		...extra,
	};
}

function json(response, status, body) {
	response.writeHead(status, headers({ 'X-Request-ID': requestId }));
	response.end(JSON.stringify(body));
}

function error(response, status, code, message, retryable = false, details) {
	json(response, status, {
		error: { code, message, retryable, request_id: requestId, ...(details ? { details } : {}) },
	});
}

const server = http.createServer((request, response) => {
	if (request.url === '/health') {
		json(response, 200, { ok: true });
		return;
	}
	if (request.method === 'OPTIONS') {
		response.writeHead(204, headers());
		response.end();
		return;
	}

	if (!request.headers.authorization?.startsWith('Bearer ')) {
		error(response, 401, 'authentication_required', 'Authentication is required.');
		return;
	}
	const requestMode = modeFor(request);
	if (requestMode === 'unauthorized') {
		error(response, 401, 'invalid_authentication', 'Authentication credentials are invalid.');
		return;
	}

	if (request.method === 'GET' && request.url?.startsWith('/v1/reviews/due')) {
		if (requestMode === 'empty') {
			json(response, 200, { items: [], next_cursor: null });
			return;
		}
		const sendDueCards = () =>
			json(response, 200, {
				items: [
					{
						id: cardId,
						deck: {
							id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
							title: 'English',
							target_language: 'en',
							explanation_language: 'zh-TW',
							archived_at: null,
						},
						term: 'resilient',
						meaning: '有復原力的',
						reading: null,
						pronunciation: '/rɪˈzɪliənt/',
						romanization: null,
						part_of_speech: 'adjective',
						archived_at: null,
						version: 1,
						updated_at: '2026-09-10T00:00:00Z',
						target_language_definition: 'able to recover quickly',
						example_sentence: 'The service is resilient to retries.',
						example_translation: null,
						example_source: null,
						synonyms: ['robust'],
						antonyms: ['fragile'],
						part_of_speech_detail: null,
						note: null,
						supplementary_note: null,
						learned_on: '2026-09-01',
						created_at: '2026-09-01T00:00:00Z',
						tags: [{ id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', display_name: 'backend' }],
						review_state: reviewState,
					},
				],
				next_cursor: null,
			});
		if (requestMode === 'slow') setTimeout(sendDueCards, 300);
		else sendDueCards();
		return;
	}

	if (request.method === 'POST' && request.url === '/v1/reviews') {
		let raw = '';
		request.on('data', (chunk) => (raw += chunk));
		request.on('end', () => {
			const key = request.headers['idempotency-key'];
			if (requestMode === 'submit-unauthorized') {
				error(response, 401, 'invalid_authentication', 'Authentication credentials are invalid.');
				return;
			}
			if (requestMode === 'validation') {
				error(response, 422, 'validation_failed', 'The request did not pass validation.');
				return;
			}
			if (requestMode === 'not-found') {
				error(response, 404, 'card_not_found', 'The requested card was not found.');
				return;
			}
			if (requestMode === 'server-error') {
				error(response, 500, 'internal_error', 'An unexpected error occurred.');
				return;
			}
			if (requestMode === 'invalid-response') {
				json(response, 200, { unexpected: true });
				return;
			}
			if (requestMode === 'conflict') {
				error(
					response,
					409,
					'stale_review_state',
					'A review state changed since it was read.',
					false,
					{
						item_index: 0,
						card_id: cardId,
						expected_version: 1,
						current_version: 2,
					}
				);
				return;
			}
			if ((requestMode === 'ambiguous' || requestMode === 'retryable') && !firstCommand) {
				firstCommand = { key, raw };
				if (requestMode === 'retryable') {
					error(
						response,
						503,
						'database_unavailable',
						'The database is temporarily unavailable.',
						true
					);
					return;
				}
				request.socket.destroy();
				return;
			}
			if (firstCommand && (firstCommand.key !== key || firstCommand.raw !== raw)) {
				error(response, 409, 'idempotency_key_reused', 'Retry changed the logical command.');
				return;
			}
			const payload = JSON.parse(raw);
			json(response, 200, {
				batch_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
				reviewed_at: '2026-09-11T00:00:00Z',
				algorithm_version: 'srs-v1',
				items: payload.items.map((item, index) => ({
					event_id: index + 1,
					card_id: item.card_id,
					decision: item.decision,
					quality: item.decision === 'yes' ? 5 : 0,
					previous_state: reviewState,
					resulting_state: {
						...reviewState,
						review_stage: item.decision === 'yes' ? 2 : 1,
						interval_days: 3,
						last_reviewed_at: '2026-09-11T00:00:00Z',
						next_review_at: '2026-09-14T00:00:00Z',
						version: 2,
					},
				})),
			});
		});
		return;
	}

	error(response, 404, 'endpoint_not_found', 'The requested endpoint was not found.');
});

server.listen(port, '127.0.0.1', () => {
	process.stdout.write(`mock review API listening on ${port} in ${mode} mode\n`);
});
