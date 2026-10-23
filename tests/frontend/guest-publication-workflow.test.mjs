import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

test("Pages publication is manual and separates machine credentials from frontend build", async () => {
  const workflow = await readFile(
    new URL("../../.github/workflows/deploy.yml", import.meta.url),
    "utf8",
  );
  assert.match(workflow, /workflow_dispatch:/);
  assert.doesNotMatch(workflow, /\b(push|schedule|pull_request|workflow_run):/);
  assert.match(workflow, /github.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /create_credentials_file: false/);
  assert.match(workflow, /id_token_include_email: true/);
  assert.match(workflow, /needs: export_guest_cards/);
  assert.match(workflow, /path: static\/guest/);
  const build = workflow.split("  build_site:")[1].split("  deploy:")[0];
  assert.doesNotMatch(
    build,
    /id-token: write|GUEST_EXPORT_TOKEN|google-github-actions\/auth/,
  );
  assert.match(workflow, /cancel-in-progress: false/);
});
