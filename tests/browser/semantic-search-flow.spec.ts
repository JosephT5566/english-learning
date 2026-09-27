import { expect, test } from '@playwright/test';

test('semantic search preserves static routing and shows partial owned results', async ({
	page,
}) => {
	await page.addInitScript(() => {
		const encode = (value: object) =>
			btoa(JSON.stringify(value)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
		const exp = Math.floor(Date.now() / 1000) + 60 * 60;
		const token = `${encode({ alg: 'none' })}.${encode({
			iss: 'https://accounts.google.com',
			aud: 'browser-contract-test',
			exp,
			email: 'browser-test@example.com',
			email_verified: true,
			sub: 'browser-test-semantic-search',
		})}.test-signature`;
		localStorage.setItem('gid_id_token', token);
		localStorage.setItem('gid_exp', String(exp));
	});
	const requests: { url: string; body: string | null }[] = [];
	page.on('request', (request) => {
		if (new URL(request.url()).pathname === '/v1/cards/semantic-search') {
			requests.push({ url: request.url(), body: request.postData() });
		}
	});

	await page.goto('/search');
	await page.getByRole('button', { name: 'Meaning & concepts', exact: true }).click();
	await expect(
		page.getByText('Meaning search currently uses English cards only.', { exact: true }),
	).toBeVisible();
	await page.getByLabel('Describe the meaning or idea').fill('recover after difficulty');
	await page.getByRole('button', { name: 'Search cards', exact: true }).click();

	await expect(page.getByText('resilient', { exact: true })).toBeVisible();
	await expect(page.getByText('Strong match', { exact: true })).toBeVisible();
	await expect(page.getByRole('link', { name: /resilient/ })).toHaveAttribute(
		'href',
		'/cards/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa?language=en',
	);
	await expect(page.getByRole('status')).toContainText(
		'Meaning search is ready for 2 of your 3 English cards',
	);
	expect(requests).toHaveLength(1);
	expect(requests[0].url).toBe('http://127.0.0.1:8001/v1/cards/semantic-search');
	expect(JSON.parse(requests[0].body ?? '{}')).toEqual({
		query: 'recover after difficulty',
		target_language: 'en',
		limit: 10,
	});

	await page.setViewportSize({ width: 390, height: 700 });
	const searchPage = await page.locator('.search-page').boundingBox();
	expect(searchPage?.width).toBeLessThanOrEqual(366);
	await expect(page.getByRole('button', { name: 'Meaning & concepts' })).toBeVisible();
	await expect(page.getByRole('link', { name: /resilient/ })).toBeVisible();
});
