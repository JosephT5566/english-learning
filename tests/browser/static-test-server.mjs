import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';

const root = path.resolve('build');
const port = Number(process.env.STATIC_TEST_PORT ?? 4173);
const contentTypes = {
	'.css': 'text/css',
	'.html': 'text/html',
	'.js': 'text/javascript',
	'.json': 'application/json',
	'.svg': 'image/svg+xml',
	'.woff': 'font/woff',
	'.woff2': 'font/woff2',
};

function testToken(testMode) {
	const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url');
	const exp = Math.floor(Date.now() / 1000) + 60 * 60;
	return {
		token: `${encode({ alg: 'none' })}.${encode({
			iss: 'https://accounts.google.com',
			aud: 'browser-contract-test',
			exp,
			email: 'browser-test@example.com',
			email_verified: true,
			sub: `browser-test-${testMode}`,
		})}.test-signature`,
		exp,
	};
}

http
	.createServer(async (request, response) => {
		const authMatch = request.url?.match(
			/^\/__test__\/auth\/(retryable|conflict|empty|unauthorized|submit-unauthorized|validation|not-found|server-error|invalid-response|slow)$/,
		);
		if (authMatch) {
			const { token, exp } = testToken(authMatch[1]);
			response.writeHead(200, { 'Content-Type': 'text/html' });
			response.end(`<!doctype html><script>
				localStorage.setItem('gid_id_token', ${JSON.stringify(token)});
				localStorage.setItem('gid_exp', ${JSON.stringify(String(exp))});
				localStorage.removeItem('pending_review_submission_v1');
				location.replace('/review');
			</script>`);
			return;
		}

		const urlPath = new URL(request.url ?? '/', 'http://127.0.0.1').pathname;
		const relative =
			urlPath === '/'
				? 'index.html'
				: urlPath === '/review' || urlPath === '/decks'
					? `${urlPath.slice(1)}.html`
					: urlPath.slice(1);
		const filePath = path.resolve(root, relative);
		if (!filePath.startsWith(`${root}${path.sep}`)) {
			response.writeHead(404);
			response.end();
			return;
		}
		try {
			const body = await fs.readFile(filePath);
			response.writeHead(200, {
				'Content-Type': contentTypes[path.extname(filePath)] ?? 'application/octet-stream',
			});
			response.end(body);
		} catch {
			try {
				const fallback = await fs.readFile(path.resolve(root, '404.html'));
				response.writeHead(200, { 'Content-Type': 'text/html' });
				response.end(fallback);
			} catch {
				response.writeHead(404);
				response.end('Not found');
			}
		}
	})
	.listen(port, '127.0.0.1', () => {
		process.stdout.write(`static browser-test server listening on ${port}\n`);
	});
