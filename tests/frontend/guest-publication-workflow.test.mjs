import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

const readWorkflow = (name) =>
  readFile(
    new URL(`../../.github/workflows/${name}.yml`, import.meta.url),
    "utf8",
  );

function assertManual(workflow) {
  assert.match(workflow, /workflow_dispatch:/);
  assert.doesNotMatch(workflow, /\b(push|schedule|pull_request|workflow_run):/);
  assert.match(workflow, /cancel-in-progress: false/);
}

test("Pages builds the committed snapshot independently of the backend", async () => {
  const workflow = await readWorkflow("deploy");
  assertManual(workflow);
  assert.doesNotMatch(
    workflow,
    /export_guest_cards|download-artifact|google-github-actions|GUEST_EXPORT/,
  );
  const build = workflow.split("  build_site:")[1].split("  deploy:")[0];
  assert.match(build, /github.ref == 'refs\/heads\/main'/);
  assert.doesNotMatch(build, /needs:|id-token:|contents: write/);
  assert.match(
    build,
    /node scripts\/validate-guest-snapshot.mjs static\/guest\/cards.json/,
  );
  assert.ok(
    build.indexOf("validate-guest-snapshot.mjs") <
      build.indexOf("npm run build"),
  );
  assert.match(
    workflow.split("  deploy:")[1],
    /github.ref == 'refs\/heads\/main'/,
  );
});

test("manual export separates machine identity from path-restricted PR writes", async () => {
  const workflow = await readWorkflow("export-guest-cards");
  assertManual(workflow);
  assert.match(workflow, /group: guest-cards-export/);
  const exporter = workflow
    .split("  export_guest_cards:")[1]
    .split("  propose_snapshot:")[0];
  const proposal = workflow.split("  propose_snapshot:")[1];
  for (const job of [exporter, proposal]) {
    assert.match(job, /github.ref == 'refs\/heads\/main'/);
    assert.match(job, /ref: main/);
    assert.match(job, /persist-credentials: false/);
  }
  assert.match(exporter, /environment: guest-cards-export/);
  assert.match(exporter, /contents: read\n {6}id-token: write/);
  assert.doesNotMatch(
    exporter,
    /contents: write|pull-requests: write|create-pull-request/,
  );
  assert.match(exporter, /create_credentials_file: false/);
  assert.match(exporter, /export_environment_variables: false/);
  assert.match(exporter, /id_token_include_email: true/);
  assert.match(exporter, /path: exported-guest\/cards.json/);
  assert.match(proposal, /needs: export_guest_cards/);
  assert.match(proposal, /contents: write\n {6}pull-requests: write/);
  assert.doesNotMatch(
    proposal,
    /id-token:|google-github-actions|GUEST_EXPORT|run-id:|repository:|github-token:/,
  );
  assert.match(proposal, /path: static\/guest/);
  assert.match(
    proposal,
    /node scripts\/validate-guest-snapshot.mjs static\/guest\/cards.json/,
  );
  assert.match(
    proposal,
    /node scripts\/validate-guest-snapshot.mjs static\/guest\/cards.json\n {10}npx prettier --write static\/guest\/cards.json\n {10}node scripts\/validate-guest-snapshot.mjs static\/guest\/cards.json/,
  );
  assert.match(
    proposal,
    /peter-evans\/create-pull-request@5f6978faf089d4d20b00c7766989d076bb2fc7f1/,
  );
  assert.match(proposal, /token: \$\{\{ secrets.GITHUB_TOKEN \}\}/);
  assert.match(
    proposal,
    /branch: automation\/guest-cards-snapshot\n {10}base: main\n {10}add-paths: static\/guest\/cards.json\n/,
  );
  assert.doesNotMatch(
    workflow,
    /gh pr merge|enable-pull-request-automerge|deploy-pages/,
  );
});

test("CI validates committed content before build or browser fixtures", async () => {
  const workflow = await readWorkflow("ci");
  const validation = workflow.indexOf(
    "node scripts/validate-guest-snapshot.mjs static/guest/cards.json",
  );
  assert.ok(validation > 0);
  assert.ok(validation < workflow.indexOf("npm run build"));
  assert.ok(validation < workflow.indexOf("npm run test:browser"));
});
