/**
 * Election-fallout data.json -> standalone HTML with Tailwind CSS inlined.
 *
 *   bun run src/election/render.tsx [path/to/data.json] [--brief]
 *
 * --brief renders the 2-3 page short version (components/Brief.tsx) to
 * election_health_<date>_brief.html instead of the full report. Its text comes from
 * brief.json next to data.json.
 *
 * Writes reports/election_fallout/election_health_<date>.html and
 * dist/election_last_render.json (consumed by src/election/pdf.ts).
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { Brief, type BriefContent } from "./components/Brief";
import { Report } from "./components/Report";
import type { ReportData } from "./types";

const here = dirname(fileURLToPath(import.meta.url));
const componentsDir = resolve(here, "..", "..");
const args = process.argv.slice(2);
const brief = args.includes("--brief");
const dataArg = args.find((a) => !a.startsWith("--"));
const dataPath = resolve(dataArg ?? join(componentsDir, "..", "reports", "election_fallout", "data.json"));
const outDir = dirname(dataPath);
const distDir = join(componentsDir, "dist");
mkdirSync(distDir, { recursive: true });

const data: ReportData = JSON.parse(readFileSync(dataPath, "utf8"));
let body: string;
if (brief) {
  const briefPath = join(dirname(dataPath), "brief.json");
  const content: BriefContent = JSON.parse(readFileSync(briefPath, "utf8"));
  body = renderToStaticMarkup(<Brief data={{ ...data, brief: content }} />);
} else {
  body = renderToStaticMarkup(<Report data={data} />);
}

const cssOut = join(distDir, "election.css");
const twCli = join(componentsDir, "node_modules", "@tailwindcss", "cli", "dist", "index.mjs");
const tw = Bun.spawnSync(
  [process.execPath, twCli, "-i", join(here, "styles.css"), "-o", cssOut, "--minify"],
  { cwd: componentsDir, stdout: "pipe", stderr: "pipe" },
);
if (tw.exitCode !== 0) {
  throw new Error(`tailwind build failed (exit ${tw.exitCode}):\n${tw.stdout.toString()}\n${tw.stderr.toString()}`);
}
const css = readFileSync(cssOut, "utf8");

const title = brief
  ? "What Michigan's New Majority Said About Health Care (Short Version)"
  : "What Michigan's New Majority Said About Health Care";
// The brief has no full-bleed cover, so its first page keeps the normal margins.
const briefCss = brief ? "@page :first { margin: 0.6in 0.65in 0.72in 0.65in; }" : "";
const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<meta name="generator" content="election_fallout pipeline (React + Tailwind + Playwright)">
<style>${css}${briefCss}</style>
</head>
<body>
${body}
</body>
</html>
`;

const stamp = data.generated.slice(0, 10);
const htmlPath = join(outDir, `election_health_${stamp}${brief ? "_brief" : ""}.html`);
writeFileSync(htmlPath, html, "utf8");
writeFileSync(
  join(distDir, "election_last_render.json"),
  JSON.stringify({ html: htmlPath, pdf: htmlPath.replace(/\.html$/, ".pdf"), title }, null, 2),
);
console.log(`wrote ${htmlPath} (${(html.length / 1024).toFixed(0)} KB)`);
