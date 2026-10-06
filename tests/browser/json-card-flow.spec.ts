import { expect, test, type Page } from '@playwright/test';

const enDeck = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const jaDeck = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
async function signIn(page: Page) {
	await page.addInitScript(() => {
		const encode = (value: object) =>
			btoa(JSON.stringify(value)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
		const exp = Math.floor(Date.now() / 1000) + 3600;
		localStorage.setItem(
			'gid_id_token',
			`${encode({ alg: 'none' })}.${encode({ sub: 'browser-test-management', email: 'browser-test@example.com', email_verified: true, exp })}.test`,
		);
		localStorage.setItem('gid_exp', String(exp));
	});
}

async function mockJsonApi(page: Page, language: 'en' | 'ja', ambiguous = false) {
	const writes: { body: string }[] = [];
	let first = true;
	const defaults = {
		reading: null,
		romanization: null,
		pronunciation: null,
		target_language_definition: null,
		example_sentence: null,
		example_translation: null,
		example_source: null,
		synonyms: [],
		antonyms: [],
		part_of_speech: null,
		part_of_speech_detail: null,
		note: null,
		supplementary_note: null,
		learned_on: null,
	};
	await page.route('**/v1/decks/*/card-drafts/validate', async (route) => {
		const payload = route.request().postDataJSON();
		await route.fulfill({
			json: { cards: payload.cards.map((fields: object) => ({ ...defaults, ...fields })) },
		});
	});
	await page.route('**/v1/decks/*/cards/bulk', async (route) => {
		if (route.request().method() !== 'POST') return route.continue();
		const request = route.request();
		writes.push({ body: request.postData()! });
		if (ambiguous && first) {
			first = false;
			return route.fulfill({ status: 201, json: { unclear: true } });
		}
		const payload = request.postDataJSON();
		await route.fulfill({
			status: 201,
			json: {
				cards: payload.cards.map(
					(item: { idempotency_key: string; fields: object }, index: number) => ({
						idempotency_key: item.idempotency_key,
						card: {
							...defaults,
							...item.fields,
							id: `abababab-abab-4bab-8bab-${String(index + 1).padStart(12, '0')}`,
							deck: {
								id: language === 'ja' ? jaDeck : enDeck,
								title: 'Words',
								target_language: language,
								explanation_language: 'zh-TW',
								archived_at: null,
							},
							version: 1,
							archived_at: null,
							created_at: '2026-10-06T00:00:00Z',
							updated_at: '2026-10-06T00:00:00Z',
							tags: [],
							review_state: {
								review_stage: 1,
								ease_factor: '2.50',
								interval_days: 0,
								last_reviewed_at: null,
								next_review_at: '2026-10-06T00:00:00Z',
								version: 1,
							},
						},
					}),
				),
			},
		});
	});
	return writes;
}

async function openJson(page: Page, language: 'en' | 'ja') {
	await page.goto(`/decks/${language === 'ja' ? jaDeck : enDeck}?language=${language}`);
	await page.getByRole('button', { name: 'New card' }).click();
	await expect(page.getByRole('tab', { name: 'Manual', exact: true })).toHaveAttribute(
		'aria-selected',
		'true',
	);
	await page.getByRole('tab', { name: 'Manual', exact: true }).focus();
	await page.keyboard.press('ArrowRight');
	await expect(page.getByRole('tab', { name: 'JSON', exact: true })).toHaveAttribute(
		'aria-selected',
		'true',
	);
}

test('English JSON authoring previews and confirms one card without changing manual creation', async ({
	page,
}) => {
	await signIn(page);
	const writes = await mockJsonApi(page, 'en');
	await openJson(page, 'en');
	await page.getByText('View prompt', { exact: true }).click();
	await expect(page.locator('.prompt-details pre')).toContainText('Target language: English');
	await expect(page.locator('.prompt-details pre')).toContainText('Traditional Chinese');
	await page.getByLabel('Card JSON').fill('{"cards":[{"term":"steady","meaning":"穩定的"}]}');
	await page.getByRole('button', { name: 'Validate and preview' }).click();
	await expect(page.getByText('steady', { exact: true })).toBeVisible();
	expect(writes).toHaveLength(0);
	await page.getByRole('button', { name: 'Add selected cards (1)' }).click();
	await expect(page.getByText('1 added · 0 selected')).toBeVisible();
	expect(JSON.parse(writes[0].body).cards[0].fields).toMatchObject({ term: 'steady' });
	expect(writes).toHaveLength(1);
});

test('Japanese multiple-card preview edits and selects before creation on a mobile viewport', async ({
	page,
}) => {
	await signIn(page);
	await page.setViewportSize({ width: 390, height: 844 });
	const writes = await mockJsonApi(page, 'ja');
	await openJson(page, 'ja');
	await page.getByLabel('Card JSON').fill(
		JSON.stringify({
			cards: [
				{ term: '読む', meaning: '閱讀', reading: 'よむ' },
				{ term: '書く', meaning: '書寫', reading: 'かく' },
			],
		}),
	);
	await page.getByRole('button', { name: 'Validate and preview' }).click();
	await expect(page.getByText('よむ', { exact: true })).toBeVisible();
	await page.getByRole('button', { name: 'Edit card 1' }).click();
	await page.locator('.json-authoring').getByLabel('Meaning', { exact: true }).fill('閱讀文字');
	await page.getByRole('button', { name: 'Apply draft edits' }).click();
	await page.getByRole('checkbox', { name: 'Card 2' }).uncheck();
	await page.getByRole('button', { name: 'Add selected cards (1)' }).click();
	await expect(page.getByText('1 added · 0 selected')).toBeVisible();
	expect(writes).toHaveLength(1);
	expect(JSON.parse(writes[0].body).cards[0].fields).toMatchObject({
		reading: 'よむ',
		meaning: '閱讀文字',
	});
	expect(
		await page.locator('.json-authoring').evaluate((node) => node.scrollWidth <= node.clientWidth),
	).toBe(true);
});

test('unconfirmed multi-card bulk create survives reload and retries the identical command', async ({
	page,
}) => {
	await signIn(page);
	const writes = await mockJsonApi(page, 'en', true);
	await openJson(page, 'en');
	await page.getByLabel('Card JSON').fill(
		JSON.stringify({
			cards: [
				{ term: 'retry', meaning: '再試一次' },
				{ term: 'second', meaning: '第二' },
			],
		}),
	);
	await page.getByRole('button', { name: 'Validate and preview' }).click();
	await page.getByRole('button', { name: 'Add selected cards (2)' }).click();
	await expect(page.getByRole('button', { name: 'Retry unchanged cards' })).toBeVisible();
	await page.reload();
	await expect(page.getByRole('button', { name: 'Retry unchanged cards' })).toBeVisible();
	await expect(page.getByRole('tab', { name: 'Manual', exact: true })).toBeDisabled();
	await page.getByRole('button', { name: 'Retry unchanged cards' }).click();
	await expect(page.getByText('2 added · 0 selected')).toBeVisible();
	expect(writes).toHaveLength(2);
	expect(writes[1]).toEqual(writes[0]);
});

test('JSON field validates locally after paste and recovers after correction without network calls', async ({
	page,
}) => {
	await signIn(page);
	const writes = await mockJsonApi(page, 'en');
	const validationCalls: string[] = [];
	page.on('request', (request) => {
		if (request.url().includes('/card-drafts/validate')) validationCalls.push(request.url());
	});
	await openJson(page, 'en');
	const input = page.getByLabel('Card JSON');
	await input.fill('{"cards":[{"term":"learn"}]}');
	await expect(page.getByText('Card 1 · meaning: This field is required.')).toBeVisible();
	await expect(input).toHaveAttribute('aria-invalid', 'true');
	await expect(page.getByRole('button', { name: 'Validate and preview' })).toBeDisabled();
	expect(validationCalls).toHaveLength(0);
	await input.fill('{"cards":[{"term":"learn","meaning":"學習"}]}');
	await expect(
		page.getByText('JSON format looks valid. Preview to check it with your deck.'),
	).toBeVisible();
	await expect(page.getByRole('button', { name: 'Validate and preview' })).toBeEnabled();
	expect(validationCalls).toHaveLength(0);
	await page.getByRole('button', { name: 'Validate and preview' }).click();
	await expect(page.getByText('learn', { exact: true })).toBeVisible();
	expect(validationCalls).toHaveLength(1);
	expect(writes).toHaveLength(0);
});

test('two selected drafts are confirmed by a single bulk request', async ({ page }) => {
	await signIn(page);
	const writes = await mockJsonApi(page, 'en');
	await openJson(page, 'en');
	await page.getByLabel('Card JSON').fill(
		JSON.stringify({
			cards: [
				{ term: 'one', meaning: 'first' },
				{ term: 'two', meaning: 'second' },
			],
		}),
	);
	await page.getByRole('button', { name: 'Validate and preview' }).click();
	await page.getByRole('button', { name: 'Add selected cards (2)' }).click();
	await expect(page.getByText('2 added · 0 selected')).toBeVisible();
	expect(writes).toHaveLength(1);
	expect(
		JSON.parse(writes[0].body).cards.map((item: { fields: { term: string } }) => item.fields.term),
	).toEqual(['one', 'two']);
});
