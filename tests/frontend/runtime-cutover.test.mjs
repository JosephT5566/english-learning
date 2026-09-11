import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readdir, readFile } from 'node:fs/promises';
import test from 'node:test';

async function filesUnder(directory) {
	const entries = await readdir(directory, { withFileTypes: true });
	const files = await Promise.all(
		entries.map((entry) => {
			const path = `${directory}/${entry.name}`;
			return entry.isDirectory() ? filesUnder(path) : [path];
		}),
	);
	return files.flat();
}

test('normal frontend build configuration has no Apps Script variable', async () => {
	const trackedRuntimeFiles = [
		...(await filesUnder('.github/workflows')),
		...(await filesUnder('src')),
		'.env.example',
		'package.json',
		'svelte.config.js',
	];

	for (const path of trackedRuntimeFiles) {
		const source = await readFile(path, 'utf8');
		assert.doesNotMatch(source, /PUBLIC_APP_SCRIPT_URL/, path);
		assert.doesNotMatch(source, /from ['"]\$lib\/api\/sheet(?:\.ts)?['"]/, path);
	}
});

test('deployment requires the FastAPI origin and legacy helpers require explicit injection', async () => {
	const deployment = await readFile('.github/workflows/deploy.yml', 'utf8');
	const legacyWrapper = await readFile('src/lib/api/sheet.ts', 'utf8');

	assert.match(deployment, /PUBLIC_API_BASE_URL: \$\{\{ vars\.PUBLIC_API_BASE_URL \}\}/);
	assert.match(deployment, /node scripts\/validate-public-env\.mjs/);
	assert.match(legacyWrapper, /getWordListFromSheet\(endpoint: string\)/);
	assert.match(legacyWrapper, /endpoint: string,\s+updateFields: UpdateFields/);
});

test('deployment configuration validation accepts a complete HTTPS runtime', () => {
	const result = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: {
			...process.env,
			PUBLIC_API_BASE_URL: 'https://api.example.com',
			PUBLIC_GOOGLE_AUTH_CLIENT_ID: 'test-client',
			PUBLIC_EMAIL_WHITE_LIST: 'test@example.com',
		},
	});

	assert.equal(result.status, 0, result.stderr);
});

test('deployment configuration validation rejects missing or unsafe API origins', () => {
	const baseEnv = {
		...process.env,
		PUBLIC_GOOGLE_AUTH_CLIENT_ID: 'test-client',
		PUBLIC_EMAIL_WHITE_LIST: 'test@example.com',
	};
	delete baseEnv.PUBLIC_API_BASE_URL;

	const missing = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: baseEnv,
	});
	const insecure = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: { ...baseEnv, PUBLIC_API_BASE_URL: 'http://api.example.com' },
	});
	const queryBearing = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: { ...baseEnv, PUBLIC_API_BASE_URL: 'https://api.example.com?token=unsafe' },
	});
	const credentialBearing = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: { ...baseEnv, PUBLIC_API_BASE_URL: 'https://user:password@api.example.com' },
	});
	const fragmentBearing = spawnSync(process.execPath, ['scripts/validate-public-env.mjs'], {
		encoding: 'utf8',
		env: { ...baseEnv, PUBLIC_API_BASE_URL: 'https://api.example.com#unsafe' },
	});

	assert.notEqual(missing.status, 0);
	assert.match(missing.stderr, /Missing required public runtime configuration/);
	assert.notEqual(insecure.status, 0);
	assert.match(insecure.stderr, /must use HTTPS/);
	assert.notEqual(queryBearing.status, 0);
	assert.match(queryBearing.stderr, /must not contain credentials, a query, or a fragment/);
	assert.notEqual(credentialBearing.status, 0);
	assert.match(credentialBearing.stderr, /must not contain credentials, a query, or a fragment/);
	assert.notEqual(fragmentBearing.status, 0);
	assert.match(fragmentBearing.stderr, /must not contain credentials, a query, or a fragment/);
});
