import http from 'node:http';

const mode = process.env.MOCK_REVIEW_MODE ?? 'ambiguous';
const port = Number(process.env.MOCK_REVIEW_PORT ?? 8001);
const origin = 'http://127.0.0.1:4173';
const cardId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const japaneseCardId = 'ffffffff-ffff-4fff-8fff-ffffffffffff';
const englishDeckId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const japaneseDeckId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
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

function deck(language, archived = false) {
	const japanese = language === 'ja';
	return {
		id: japanese ? japaneseDeckId : englishDeckId,
		title: japanese ? '日本語の基礎' : 'English foundations',
		target_language: language,
		explanation_language: 'zh-TW',
		archived_at: archived ? '2026-09-11T02:00:00Z' : null,
		version: archived ? 4 : 3,
		created_at: '2026-09-01T00:00:00Z',
		updated_at: '2026-09-11T02:00:00Z',
	};
}

function card(language, detailed = false, archived = false) {
	const japanese = language === 'ja';
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
		term: japanese ? '学ぶ' : 'resilient',
		meaning: japanese ? 'to learn' : '有復原力的',
		reading: japanese ? 'まなぶ' : null,
		pronunciation: japanese ? null : '/rɪˈzɪliənt/',
		romanization: japanese ? 'manabu' : null,
		part_of_speech: 'verb',
		archived_at: archived ? '2026-09-11T02:00:00Z' : null,
		version: 2,
		updated_at: '2026-09-11T01:00:00Z',
	};
	if (!detailed) return summary;
	return {
		...summary,
		target_language_definition: japanese ? '知識や技能を身につける' : 'able to recover quickly',
		example_sentence: japanese ? '毎日、日本語を学びます。' : 'The service is resilient.',
		example_translation: japanese ? 'I study Japanese every day.' : null,
		example_source: null,
		synonyms: japanese ? [] : ['robust'],
		antonyms: japanese ? [] : ['fragile'],
		part_of_speech_detail: null,
		note: japanese ? '五段動詞' : null,
		supplementary_note: null,
		learned_on: '2026-09-11',
		created_at: '2026-09-01T00:00:00Z',
		tags: [
			{
				id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
				display_name: 'foundation',
			},
		],
		review_state: reviewState,
	};
}

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
		error: {
			code,
			message,
			retryable,
			request_id: requestId,
			...(details ? { details } : {}),
		},
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
	if (requestMode === 'management-unauthorized') {
		error(response, 401, 'invalid_authentication', 'Authentication credentials are invalid.');
		return;
	}
	if (requestMode === 'management-retryable') {
		error(response, 503, 'database_unavailable', 'The database is temporarily unavailable.', true);
		return;
	}
	if (requestMode === 'management-server-error') {
		error(response, 500, 'internal_error', 'An unexpected error occurred.');
		return;
	}

	const parsedUrl = new URL(request.url ?? '/', `http://127.0.0.1:${port}`);
	if (request.method === 'GET' && parsedUrl.pathname === '/v1/decks') {
		if (requestMode === 'management-empty') {
			json(response, 200, { items: [], next_cursor: null });
			return;
		}
		const language = parsedUrl.searchParams.get('target_language') === 'ja' ? 'ja' : 'en';
		const archived = parsedUrl.searchParams.get('status') === 'archived';
		const sendDecks = () =>
			json(response, 200, {
				items: [deck(language, archived)],
				next_cursor: null,
			});
		if (requestMode === 'management-slow') setTimeout(sendDecks, 300);
		else sendDecks();
		return;
	}
	if (request.method === 'GET' && parsedUrl.pathname.startsWith('/v1/decks/')) {
		if (requestMode === 'management-not-found') {
			error(response, 404, 'deck_not_found', 'The requested deck was not found.');
			return;
		}
		const id = parsedUrl.pathname.split('/').at(-1);
		json(response, 200, deck(id === japaneseDeckId ? 'ja' : 'en'));
		return;
	}
	if (request.method === 'GET' && parsedUrl.pathname === '/v1/cards') {
		const japanese = parsedUrl.searchParams.get('deck_id') === japaneseDeckId;
		const archived = parsedUrl.searchParams.get('status') === 'archived';
		json(response, 200, {
			items: [card(japanese ? 'ja' : 'en', false, archived)],
			next_cursor: null,
		});
		return;
	}
	if (request.method === 'GET' && parsedUrl.pathname.startsWith('/v1/cards/')) {
		if (requestMode === 'management-not-found') {
			error(response, 404, 'card_not_found', 'The requested card was not found.');
			return;
		}
		const id = parsedUrl.pathname.split('/').at(-1);
		json(response, 200, card(id === japaneseCardId ? 'ja' : 'en', true));
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
						tags: [
							{
								id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
								display_name: 'backend',
							},
						],
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
					},
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
						true,
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
