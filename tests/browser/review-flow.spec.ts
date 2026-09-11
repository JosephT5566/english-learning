import { expect, test } from '@playwright/test';

async function answerOneCard(page: import('@playwright/test').Page) {
	const yes = page.getByRole('button', { name: 'Yes', exact: true });
	await expect(yes).toBeDisabled();
	await page.locator('.swipe--card').click();
	await expect(yes).toBeEnabled();
	await yes.click();
	await page.getByRole('button', { name: 'Submit Results', exact: true }).click();
}

test('an unconfirmed submission retries the identical command and succeeds once', async ({
	page,
}) => {
	await page.goto('/__test__/auth/retryable');
	await expect(page.getByText('resilient', { exact: true })).toBeVisible();
	await answerOneCard(page);

	await expect(page.getByRole('heading', { name: 'Review not confirmed' })).toBeVisible();
	const firstPending = await page.evaluate(() =>
		localStorage.getItem('pending_review_submission_v1')
	);
	expect(firstPending).not.toBeNull();

	await page.getByRole('button', { name: 'Retry submission', exact: true }).click();
	await expect(
		page.getByRole('heading', { name: "You've completed today's review!" })
	).toBeVisible();
	expect(
		await page.evaluate(() => localStorage.getItem('pending_review_submission_v1'))
	).toBeNull();
});

test('a stale batch is visibly rejected and retired', async ({ page }) => {
	await page.goto('/__test__/auth/conflict');
	await answerOneCard(page);

	await expect(page.getByRole('heading', { name: 'Review not saved' })).toBeVisible();
	await expect(page.getByText('None of your answers were saved.', { exact: false })).toBeVisible();
	await expect(page.getByRole('button', { name: 'Reload current reviews' })).toBeVisible();
	expect(
		await page.evaluate(() => localStorage.getItem('pending_review_submission_v1'))
	).toBeNull();
});

test('empty and authentication states are distinct', async ({ page }) => {
	await page.goto('/__test__/auth/empty');
	await expect(
		page.getByRole('heading', { name: "We don't have any cards for you today." })
	).toBeVisible();

	await page.goto('/__test__/auth/unauthorized');
	await expect(page.getByRole('heading', { name: 'Sign in required' })).toBeVisible();
	expect(await page.evaluate(() => localStorage.getItem('gid_id_token'))).toBeNull();
});

test('loading is visible while due cards are pending', async ({ page }) => {
	await page.goto('/__test__/auth/slow');
	await expect(page.getByText('Loading...', { exact: true })).toBeVisible();
	await expect(page.getByText('resilient', { exact: true })).toBeVisible();
});

test('a submission 401 signs out but preserves the unconfirmed command', async ({ page }) => {
	await page.goto('/__test__/auth/submit-unauthorized');
	await answerOneCard(page);

	await expect(page.getByRole('heading', { name: 'Sign in required' })).toBeVisible();
	expect(await page.evaluate(() => localStorage.getItem('gid_id_token'))).toBeNull();
	expect(
		await page.evaluate(() => localStorage.getItem('pending_review_submission_v1'))
	).not.toBeNull();
});

for (const testCase of [
	{ mode: 'validation', message: 'The review was rejected.' },
	{ mode: 'not-found', message: 'One or more review cards are no longer available.' },
]) {
	test(`${testCase.mode} rejection never appears successful`, async ({ page }) => {
		await page.goto(`/__test__/auth/${testCase.mode}`);
		await answerOneCard(page);

		await expect(page.getByRole('heading', { name: 'Review unavailable' })).toBeVisible();
		await expect(page.getByText(testCase.message, { exact: false })).toBeVisible();
		expect(
			await page.evaluate(() => localStorage.getItem('pending_review_submission_v1'))
		).toBeNull();
	});
}

for (const mode of ['server-error', 'invalid-response']) {
	test(`${mode} remains unconfirmed and recoverable`, async ({ page }) => {
		await page.goto(`/__test__/auth/${mode}`);
		await answerOneCard(page);

		await expect(page.getByRole('heading', { name: 'Review not confirmed' })).toBeVisible();
		expect(
			await page.evaluate(() => localStorage.getItem('pending_review_submission_v1'))
		).not.toBeNull();
	});
}
