import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("../../apps/web/node_modules/@playwright/test");

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const palettes = [
  ["#dff4f7", "#173a42", "#63aebb"],
  ["#daf0f2", "#14393d", "#4f9ba4"],
  ["#e1f6ef", "#183c31", "#62a88e"],
  ["#d6eef5", "#153845", "#559ab3"],
  ["#e4f7f4", "#173a37", "#5ea69c"],
  ["#dcf1ec", "#183b34", "#599d88"],
];
const [background, ink, accent] = palettes[payload.variant % palettes.length];
const points = payload.key_points
  .slice(0, 4)
  .map((point) => `<li>${escapeHtml(point)}</li>`)
  .join("");
const grid =
  payload.template_id === "offline-grid"
    ? `background-image:linear-gradient(${accent}22 1px,transparent 1px),linear-gradient(90deg,${accent}22 1px,transparent 1px);background-size:48px 48px;`
    : "";

const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:1500px}
body{font-family:"Microsoft YaHei UI","Noto Sans CJK SC",system-ui,sans-serif;color:${ink};background:${background};${grid}}
main{height:100%;padding:104px 104px 88px;display:flex;flex-direction:column}
.kicker{display:flex;align-items:center;gap:18px;font-size:24px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
.kicker:before{content:"";width:64px;height:8px;border-radius:999px;background:${accent}}
h1{font-size:76px;line-height:1.12;letter-spacing:-.045em;margin:112px 0 48px;max-height:340px;overflow:hidden}
.summary{font-size:34px;line-height:1.62;margin:0;max-height:330px;overflow:hidden;color:${ink}dd}
ul{list-style:none;margin:70px 0 0;padding:0;display:grid;gap:24px}
li{font-size:28px;line-height:1.45;padding-left:38px;position:relative}
li:before{content:"";position:absolute;left:0;top:.58em;width:14px;height:14px;border:4px solid ${accent};border-radius:50%}
footer{margin-top:auto;border-top:2px solid ${ink}22;padding-top:32px;display:flex;justify-content:space-between;font-size:23px;font-weight:650}
.stamp{color:${accent};letter-spacing:.08em}
</style></head><body><main>
<div class="kicker">${escapeHtml(payload.template_id)}</div>
<h1>${escapeHtml(payload.title)}</h1>
<p class="summary">${escapeHtml(payload.summary)}</p>
<ul>${points}</ul>
<footer><span>${escapeHtml(payload.source_name)}</span><span class="stamp">AI SIGNAL STUDIO</span></footer>
</main></body></html>`;

const browser = await chromium.launch({ channel: "chrome", headless: true });
try {
  const page = await browser.newPage({
    viewport: { width: 1200, height: 1500 },
    deviceScaleFactor: 1,
  });
  await page.setContent(html, { waitUntil: "load" });
  const png = await page.screenshot({ type: "png" });
  process.stdout.write(png);
} finally {
  await browser.close();
}
