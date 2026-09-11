import { expect, test, type Page } from '@playwright/test';

const japaneseDeckId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';
const japaneseCardId = 'ffffffff-ffff-4fff-8fff-ffffffffffff';

async function signIn(page: Page, mode = 'management') {
	await page.addInitScript((subjectMode) => {
		const encode = (value: object) =>
			btoa(JSON.stringify(value)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
		const exp = Math.floor(Date.now() / 1000) + 60 * 60;
		const token = `${encode({ alg: 'none' })}.${encode({
			iss: 'https://accounts.google.com',
			aud: 'browser-contract-test',
			exp,
			email: 'browser-test@example.com',
			email_verified: true,
			sub: `browser-test-${subjectMode}`,
		})}.test-signature`;
		localStorage.setItem('gid_id_token', token);
		localStorage.setItem('gid_exp', String(exp));
	}, mode);
}

test('missing language becomes English and normal reads never call Apps Script', async ({
	page,
}) => {
	await signIn(page);
	const runtimeRequests: string[] = [];
	page.on('request', (request) => {
		if (request.resourceType() === 'fetch' || request.resourceType() === 'xhr') {
			runtimeRequests.push(request.url());
		}
	});

	await page.goto('/decks');
	await expect(page).toHaveURL(/\/decks\?language=en&status=active$/);
	await expect(page.getByRole('heading', { name: 'English foundations' })).toBeVisible();
	await page.goto('/review');
	await expect(page.getByText('resilient', { exact: true })).toBeVisible();

	const apiContractRequests = runtimeRequests.filter((url) =>
		new URL(url).pathname.startsWith('/v1/'),
	);
	expect(apiContractRequests.length).toBeGreaterThan(1);
	expect(apiContractRequests.every((url) => url.startsWith('http://127.0.0.1:8001/v1/'))).toBe(
		true,
	);
	expect(runtimeRequests.some((url) => /script\.google|apps-script/i.test(url))).toBe(false);
});

test('Japanese decks and cards use the shared routes with relevant fields', async ({ page }) => {
	await signIn(page);
	await page.goto('/decks?language=ja');
	await expect(page.getByRole('heading', { name: '日本語の基礎' })).toBeVisible();

	await page.getByRole('link', { name: 'Manage cards' }).click();
	await expect(page).toHaveURL(new RegExp(`/decks/${japaneseDeckId}\\?language=ja`));
	await expect(page.getByRole('heading', { name: '学ぶ' })).toBeVisible();
	await expect(page.getByText('まなぶ · manabu')).toBeVisible();

	await page.getByRole('link', { name: 'View card' }).click();
	await expect(page).toHaveURL(new RegExp(`/cards/${japaneseCardId}\\?language=ja`));
	await expect(page.getByText('まなぶ', { exact: true })).toBeVisible();
	await expect(page.getByText('manabu', { exact: true })).toBeVisible();
	await expect(page.getByText('Pronunciation', { exact: true })).toHaveCount(0);
});

test('invalid language is rejected before an API request', async ({ page }) => {
	await signIn(page);
	const apiRequests: string[] = [];
	page.on('request', (request) => {
		if (request.url().startsWith('http://127.0.0.1:8001/')) apiRequests.push(request.url());
	});
	await page.goto('/decks?language=fr');
	await expect(page.getByRole('heading', { name: 'Choose English or Japanese' })).toBeVisible();
	expect(apiRequests).toEqual([]);
});

test('archived decks remain available through an explicit read-only filter', async ({ page }) => {
	await signIn(page);
	await page.goto('/decks?language=en&status=archived');
	await expect(page.getByRole('heading', { name: 'English foundations' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Archived' })).toHaveAttribute(
		'aria-current',
		'page',
	);
});

test('management loading and empty states remain distinct', async ({ page }) => {
	await signIn(page, 'management-slow');
	await page.goto('/decks?language=en');
	await expect(page.getByText('Loading english decks…', { exact: true })).toBeVisible();
	await expect(page.getByRole('heading', { name: 'English foundations' })).toBeVisible();
});

test('empty management response gives the user a concrete next state', async ({ page }) => {
	await signIn(page, 'management-empty');
	await page.goto('/decks?language=ja');
	await expect(page.getByRole('heading', { name: 'No active japanese decks' })).toBeVisible();
});

test('management index remains usable on a mobile viewport', async ({ page }) => {
	await page.setViewportSize({ width: 390, height: 700 });
	await signIn(page);
	await page.goto('/decks?language=ja');
	await expect(page.getByRole('heading', { name: '日本語の基礎' })).toBeVisible();
	await expect(page.getByRole('link', { name: 'Manage cards' })).toBeVisible();
	const row = await page.locator('.management-row').boundingBox();
	expect(row?.width).toBeLessThanOrEqual(350);
});

test('authentication failure clears the local sign-in state', async ({ page }) => {
	await signIn(page, 'management-unauthorized');
	await page.goto('/decks?language=en');
	await expect(page.getByRole('heading', { name: 'Sign in required' })).toBeVisible();
	expect(await page.evaluate(() => localStorage.getItem('gid_id_token'))).toBeNull();
});

test('not-found detail does not disclose ownership', async ({ page }) => {
	await signIn(page, 'management-not-found');
	await page.goto(`/decks/${japaneseDeckId}?language=ja`);
	await expect(page.getByRole('heading', { name: 'Deck not found' })).toBeVisible();
	await expect(page.getByText('you may not have access', { exact: false })).toBeVisible();
});

test('retryable read failure offers an explicit retry', async ({ page }) => {
	await signIn(page, 'management-retryable');
	await page.goto('/decks?language=en');
	await expect(
		page.getByRole('heading', { name: 'Service temporarily unavailable' }),
	).toBeVisible();
	await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});
