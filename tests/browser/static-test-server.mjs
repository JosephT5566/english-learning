import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";

const root = path.resolve("build");
const port = Number(process.env.STATIC_TEST_PORT ?? 4173);
const base = process.env.BASE_PATH ?? "";
const contentTypes = {
  ".css": "text/css",
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function testToken(testMode) {
  const encode = (value) =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  const exp = Math.floor(Date.now() / 1000) + 60 * 60;
  return {
    token: `${encode({ alg: "none" })}.${encode({
      iss: "https://accounts.google.com",
      aud: "browser-contract-test",
      exp,
      email: "browser-test@example.com",
      email_verified: true,
      sub: `browser-test-${testMode}`,
    })}.test-signature`,
    exp,
  };
}

http
  .createServer(async (request, response) => {
    const authMatch = request.url?.match(
      /^\/__test__\/auth\/(success|retryable|conflict|empty|unauthorized|submit-unauthorized|validation|not-found|server-error|invalid-response|slow)$/,
    );
    if (authMatch) {
      const { token } = testToken(authMatch[1]);
      response.writeHead(200, { "Content-Type": "text/html" });
      response.end(`<!doctype html><script type="module">
        const response = await fetch('http://127.0.0.1:8001/v1/auth/session', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({credential: ${JSON.stringify(token)}})
        });
        if (!response.ok) throw new Error('Synthetic sign-in failed');
        const session = await response.json();
        await fetch('http://127.0.0.1:8001/__test__/auth/reset-data', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({refresh_token: session.refresh_token}) });
        localStorage.setItem('el_auth_refresh_v1', session.refresh_token);
        const profile = {
          ...session.user,
          ...(typeof session.profile.name === 'string' ? {name: session.profile.name} : {}),
          ...(typeof session.profile.picture === 'string' ? {picture: session.profile.picture} : {})
        };
        localStorage.setItem('el_auth_profile_v1', JSON.stringify(profile));
        localStorage.removeItem('pending_review_submission_v1');
        localStorage.removeItem('pending_review_submission_v2');
        localStorage.removeItem('el_review_pending_meta_v1');
        sessionStorage.removeItem('learning_guest_session');
        location.replace(${JSON.stringify(`${base}/review`)});
      </script>`);
      return;
    }

    const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
    const urlPath =
      base && pathname.startsWith(`${base}/`)
        ? pathname.slice(base.length)
        : pathname;
    const relative =
      urlPath === "/"
        ? "index.html"
        : urlPath === "/review" ||
            urlPath === "/review/guest" ||
            urlPath === "/decks" ||
            urlPath === "/search"
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
        "Content-Type":
          contentTypes[path.extname(filePath)] ?? "application/octet-stream",
      });
      response.end(body);
    } catch {
      try {
        const fallback = await fs.readFile(path.resolve(root, "404.html"));
        response.writeHead(200, { "Content-Type": "text/html" });
        response.end(fallback);
      } catch {
        response.writeHead(404);
        response.end("Not found");
      }
    }
  })
  .listen(port, "127.0.0.1", () => {
    process.stdout.write(`static browser-test server listening on ${port}\n`);
  });
