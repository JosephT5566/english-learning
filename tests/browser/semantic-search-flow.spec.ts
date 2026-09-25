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
	await page.getByLabel('Meaning or concept').fill('recover after difficulty');
	await page.getByRole('button', { name: 'Search', exact: true }).click();

	await expect(page.getByText('resilient', { exact: true })).toBeVisible();
	await expect(page.getByText('92%', { exact: true })).toBeVisible();
	await expect(page.getByRole('status')).toContainText(
		'Showing matches from 2 of 3 eligible cards',
	);
	expect(requests).toHaveLength(1);
	expect(requests[0].url).toBe('http://127.0.0.1:8001/v1/cards/semantic-search');
	expect(JSON.parse(requests[0].body ?? '{}')).toEqual({
		query: 'recover after difficulty',
		target_language: 'en',
		limit: 10,
	});
});
