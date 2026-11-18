// Regenerates the committed PWA PNG icons from the SVG sources in static/icons/.
// Run manually from the repo root after changing a source SVG; it is not part of the build.
//   node scripts/generate-pwa-icons.mjs
// Uses the Chromium that ships with @playwright/test (npx playwright install chromium).
import { chromium } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dir = fileURLToPath(new URL("../static/icons/", import.meta.url));
const jobs = [
  ["icon-any.svg", "icon-192.png", 192],
  ["icon-any.svg", "icon-512.png", 512],
  ["icon-maskable.svg", "icon-512-maskable.png", 512],
  ["icon-apple.svg", "apple-touch-icon.png", 180],
];

const browser = await chromium.launch();
try {
  for (const [source, output, size] of jobs) {
    const svg = readFileSync(`${dir}${source}`, "utf8");
    const page = await browser.newPage({
      viewport: { width: size, height: size },
      deviceScaleFactor: 1,
    });
    await page.setContent(
      `<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`,
    );
    const png = await page.screenshot({
      omitBackground: true,
      clip: { x: 0, y: 0, width: size, height: size },
    });
    writeFileSync(`${dir}${output}`, png);
    await page.close();
  }
} finally {
  await browser.close();
}
