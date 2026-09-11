import { defineConfig } from '@playwright/test';

export default defineConfig({
	testDir: './tests/browser',
	testMatch: '**/*.spec.ts',
	fullyParallel: false,
	workers: 1,
	use: {
		baseURL: 'http://127.0.0.1:4173',
		channel: 'chrome',
		headless: true,
	},
	webServer: [
		{
			command:
				'PUBLIC_API_BASE_URL=http://127.0.0.1:8001 BASE_PATH= npm run build && node tests/browser/static-test-server.mjs',
			url: 'http://127.0.0.1:4173',
			reuseExistingServer: false,
		},
		{
			command:
				'MOCK_REVIEW_MODE=by-subject MOCK_REVIEW_PORT=8001 node tests/browser/mock-review-api.mjs',
			url: 'http://127.0.0.1:8001/health',
			reuseExistingServer: false,
		},
	],
});
