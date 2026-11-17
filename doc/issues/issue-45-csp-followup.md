# Issue #45 Q6: strict CSP deferred (2026-11-17)

Status: no CSP meta/configuration is shipped. No script `unsafe-inline` or `unsafe-eval`, and
no style-only relaxation, was added. This follows the approved Q6 stop condition; it is not
browser proof that an enforced policy works.

## Reproduced blocker

`src/lib/management/json-card-validation.ts:17-23` creates Ajv2020 with `allErrors`,
`strictRequired: false` and `useDefaults`, adds the date format, then compiles the generated
card-draft schema at module evaluation. `JsonCardForm.svelte` imports that module and the deck
detail route imports the form. The installed `ajv/dist/compile/index.js:89` uses `new Function`.
A strict script policy would block the deck editor even before JSON validation could run.

The same installed Ajv/options/schema compile normally. Running that operation with
`node --disallow-code-generation-from-strings` raises EvalError instead. This local diagnostic
establishes the runtime compilation requirement, not browser CSP/GIS compatibility.
[Ajv's primary documentation](https://ajv.js.org/standalone.html) recommends build-time standalone
validators to avoid this CSP conflict. Removing runtime compilation is follow-up implementation,
not a reason to weaken the approved script policy in #45.

## Follow-up implementation and verification

1. Generate/import a standalone card-draft validator at build/generation time. Preserve the
   current schema version, defaults, format checks, error locations and UI messages. Run existing
   `json-card-validation.test.ts`, JSON-authoring component tests and `json-card-flow.spec.ts`.
   Prove the browser bundle does not compile a schema or call the Function constructor.
2. Audit remaining script generation and external resources. Current Iconify string names can
   trigger remote icon loading; package the required local icon data rather than adding new
   origins to the policy. Check dialogs, review loading/results, JSON editing and assistant routes.
3. Use the installed SvelteKit 2 `kit.csp` mode `hash` with adapter-static, or an equivalently
   hashed meta. Installed `@sveltejs/kit/src/runtime/server/page/render.js` registers its generated
   bootstrap with `csp.add_script` and inserts prerendered meta; a shared nonce on static Pages is
   inappropriate. Do not change PUBLIC variable/base-path behavior to build the policy.
4. Restrict default resources to self; allow GIS script `https://accounts.google.com/gsi/client`
   and its `/gsi/` parent for frame/connect/style, Google Fonts style/font hosts, the profile-image
   host and data images only if required, plus the build-time origin of `PUBLIC_API_BASE_URL` in
   connect-src. Include object-src none and base-uri self. Do not rely on frame-ancestors in meta.
   Follow the [GIS CSP documentation](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid#content_security_policy).
5. Add Playwright policy coverage on home, guest review and a signed-in page, plus JSON editor
   loading. Register `securitypolicyviolation` and CSP-console-error capture before navigation;
   assert none without filtering blocked origins/directives. Intercept the real
   `https://accounts.google.com/gsi/client` URL like the existing GIS fixture, rather than serving
   it from an invented allowed origin. Exercise sign-in, API calls, icons and dialogs/transitions.
6. Build root/subpath artifacts and check index/fallback HTML contain the meta, generated bootstrap
   hashes and configured API origin. Verify each emitted inline script hash matches its bytes;
   reject unsafe script sources. A style-only `unsafe-inline` allowance, if actually required by
   GIS/Svelte inline styling/transitions, is a separate maintainer judgement and must be explicit.
7. Operator verifies real GIS, frames, callbacks, profile pictures and API exchange on GitHub Pages.
   A mocked script cannot establish real GIS compatibility. See e2e item 26.

The current build has no policy, so Phase 6 does not claim the requested policy/API-origin artifact
check or zero-CSP-violation Playwright pass. Existing auth/GIS mock tests remain useful session
regressions only. No new skipped test is used to make an absent policy appear covered.
