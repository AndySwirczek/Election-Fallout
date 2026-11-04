/**
 * Print the election-fallout HTML to PDF with Playwright's Chromium.
 *
 *   bun run src/election/pdf.ts [path/to/report.html] [--preview outDir]
 *
 * --preview also writes PNGs of the first pages of the PDF layout for a quick visual check.
 */
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const last = resolve(here, "..", "..", "dist", "election_last_render.json");

const args = process.argv.slice(2);
const pIdx = args.indexOf("--preview");
const previewDir = pIdx >= 0 ? resolve(args[pIdx + 1] ?? ".") : "";
const positional = args.filter((_, i) => pIdx < 0 || (i !== pIdx && i !== pIdx + 1));

let htmlPath = positional[0] ? resolve(positional[0]) : "";
let title = "What Michigan's New Majority Said About Health Care";
if (!htmlPath) {
  if (!existsSync(last)) throw new Error("no HTML path given and dist/election_last_render.json missing; run render first");
  const meta = JSON.parse(readFileSync(last, "utf8"));
  htmlPath = meta.html;
  title = meta.title ?? title;
}
const pdfPath = htmlPath.replace(/\.html?$/i, ".pdf");

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
  await page.evaluate(() => (document as any).fonts?.ready).catch(() => {});
  await page.waitForTimeout(500);
  await page.emulateMedia({ media: "print" });

  const footer = `
    <div style="width:100%;font-family:Inter,'Segoe UI',Arial,sans-serif;font-size:7.5px;color:#6a7684;
                padding:0 0.65in;display:flex;justify-content:space-between;letter-spacing:0.02em;">
      <span>${title.replace(/</g, "&lt;")} &nbsp;&middot;&nbsp; Michigan Health &amp; Hospital Association</span>
      <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
    </div>`;

  await page.pdf({
    path: pdfPath,
    format: "Letter",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate: footer,
  });
  console.log(`wrote ${pdfPath}`);

  if (previewDir) {
    // Render each PDF page to PNG via Chromium's built-in PDF viewer is unreliable headless;
    // instead screenshot the print-media layout at Letter width.
    mkdirSync(previewDir, { recursive: true });
    const p2 = await browser.newPage({ viewport: { width: 816, height: 1056 }, deviceScaleFactor: 1.25 });
    await p2.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
    await p2.evaluate(() => (document as any).fonts?.ready).catch(() => {});
    await p2.waitForTimeout(400);
    const h = await p2.evaluate(() => document.documentElement.scrollHeight);
    const n = Math.min(12, Math.ceil(h / 1056));
    for (let i = 0; i < n; i++) {
      await p2.screenshot({
        path: join(previewDir, `preview-${String(i + 1).padStart(2, "0")}.png`),
        clip: { x: 0, y: i * 1056, width: 816, height: Math.min(1056, h - i * 1056) },
        fullPage: true,
      });
    }
    console.log(`wrote ${n} previews to ${previewDir}`);
  }
} finally {
  await browser.close();
}
