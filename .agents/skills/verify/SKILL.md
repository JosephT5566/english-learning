---
name: verify
description: Use when reproducing or verifying a browser flow in English Learning, including guest review, private review, management, search, or GitHub Pages subpath behavior.
---

# Verify a browser flow

1. Start with the relevant specs under [tests/browser](../../../tests/browser). Playwright builds the static app with a local mock API and installs a synthetic guest snapshot in ignored build output. Use fixture sign-in and synthetic cards for interactive checks. Follow [local reviewer setup](../../../doc/development.md#local-verification-and-reviewer-setup) and the browser tool routing in [AGENTS.md](../../../AGENTS.md).
2. Run the affected specs from the root. For example, exercise guest and private review under the Pages subpath.

   ```sh
   BASE_PATH=/english-learning npm run test:browser -- tests/browser/guest-review-flow.spec.ts tests/browser/review-flow.spec.ts
   ```

3. Reproduce uncovered steps through visible controls. Record the viewport, route, actions, and observed result. Check request method and safe payload fields when the flow writes. For guest review, check that practice uses the static snapshot and sends no private API requests.
4. Keep screenshots and traces with synthetic data in ignored `test-results/`. Stop any test servers you started manually. Report the commands, results, evidence paths, and any blocked checks.
5. For API, ownership, or persistence claims, use the applicable backend checks in [AGENTS.md](../../../AGENTS.md#verification). Mocked browser results cover the browser contract with fixtures.
