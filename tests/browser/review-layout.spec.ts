import { expect, test, type Page } from '@playwright/test';

async function signIn(page: Page) {
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
			sub: 'browser-test-review-layout',
		})}.test-signature`;
		localStorage.setItem('gid_id_token', token);
		localStorage.setItem('gid_exp', String(exp));
	});
}

async function expectReviewToFitViewport(page: Page) {
	await expect(page.locator('.swipe--card').first()).toBeVisible();
	const bounds = await page.evaluate(() => {
		const header = document.querySelector('header')!.getBoundingClientRect();
		const review = document.querySelector('.review-page-container')!.getBoundingClientRect();
		const guidance = document.querySelector('.review-guidance')!.getBoundingClientRect();
		const cards = Array.from(document.querySelectorAll<HTMLElement>('.swipe--card')).filter(
			(card) => !card.dataset.removed
		);
		const cardRects = cards.map((card) => card.getBoundingClientRect());
		const card = cardRects[0];
		const controls = document.querySelector('.swipe--buttons')!.getBoundingClientRect();
		return {
			viewportHeight: window.innerHeight,
			headerBottom: header.bottom,
			reviewTop: review.top,
			reviewBottom: review.bottom,
			guidanceBottom: guidance.bottom,
			cardTop: Math.min(...cardRects.map((rect) => rect.top)),
			cardBottom: card.bottom,
			cardWidth: card.width,
			cardHeight: card.height,
			controlsBottom: controls.bottom,
		};
	});

	expect(bounds.reviewTop).toBeGreaterThanOrEqual(bounds.headerBottom - 1);
	expect(bounds.reviewBottom).toBeLessThanOrEqual(bounds.viewportHeight + 1);
	expect(bounds.cardTop).toBeGreaterThanOrEqual(bounds.guidanceBottom + 16);
	expect(bounds.cardBottom).toBeLessThanOrEqual(bounds.viewportHeight + 1);
	expect(bounds.cardHeight).toBeLessThanOrEqual(bounds.cardWidth * 1.26);
	expect(bounds.controlsBottom).toBeLessThanOrEqual(bounds.viewportHeight + 1);
}

test('review card stack uses the shell height on desktop and mobile', async ({ page }) => {
	await signIn(page);

	await page.setViewportSize({ width: 1280, height: 800 });
	await page.goto('/review');
	await expectReviewToFitViewport(page);

	await page.setViewportSize({ width: 390, height: 844 });
	await expectReviewToFitViewport(page);
});
