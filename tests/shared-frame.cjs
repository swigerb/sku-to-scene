// Local, real-Chromium composition acceptance. No package or service calls.
// node tests/shared-frame.cjs <previous-PR-preview> <candidate-preview> <artifact-directory>
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const [baseline, candidate, out] = process.argv.slice(2);
assert.ok(baseline && candidate && out);
fs.mkdirSync(out, { recursive: true });
const evidence = { baseline, candidate, baselineSha: "4a2eb46e8a412d3a1b30c68209aba2887bb554ae",
  zoom: 1, deviceScaleFactor: 1, edges: [], guide: [], examples: [], fullscreen: [], screenshots: [], sheets: [] };
const routes = [["home", "#home"], ["guide", "#guide/qsr/northwind"], ["gallery", "#scenarios"], ["evidence", "#evidence"], ["about", "#about"]];
const sizes = [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 },
  { width: 800, height: 900 }, { width: 390, height: 844 }];
const settle = async (page) => {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(150);
};
async function shot(page, name, fullPage = false) {
  const file = `${name}.png`;
  await page.evaluate(() => scrollTo(0, 0));
  await settle(page);
  await page.screenshot({ path: path.join(out, file), fullPage });
  evidence.screenshots.push(file);
  return file;
}
async function main() {
  const browser = await chromium.launch({ headless: true });
  const allowed = new Set([new URL(baseline).origin, new URL(candidate).origin]);
  try {
    for (const viewport of sizes) for (const theme of ["light", "dark"]) {
      const tiles = [];
      for (const [label, url] of [["before", baseline], ["after", candidate]]) {
        const ctx = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "reduce", deviceScaleFactor: 1 });
        await ctx.route("**/*", async (route) => {
          const request = new URL(route.request().url());
          if (!allowed.has(request.origin)) return route.abort("blockedbyclient");
          if (label === "after" && request.pathname.endsWith("/app.css") && process.env.FRAME_MUTATION) {
            const response = await route.fetch();
            const mutation = process.env.FRAME_MUTATION === "wide-guide"
              ? "main:has(#guide:not([hidden])) { max-width: 1840px; }"
              : "@media(max-width:900px) { footer nav { display:none !important; } }";
            return route.fulfill({ response, body: await response.text() + mutation });
          }
          return route.continue();
        });
        const page = await ctx.newPage();
        const errors = [];
        page.on("pageerror", (e) => errors.push(e.message));
        const prefix = `${label}-${viewport.width}x${viewport.height}-${theme}`;
        for (const [name, hash] of routes) {
          await page.goto(`${url}?scoutTheme=${theme}${hash}`);
          await page.locator("#guide-stage[data-account]").waitFor({ state: "attached" });
          await settle(page);
          const screenshot = await shot(page, `${prefix}-${name}`);
          await shot(page, `${prefix}-${name}-full`, true);
          tiles.push({ label, name, screenshot });
          const edges = await page.evaluate(() => {
            const rect = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width }; };
            const main = document.querySelector("main");
            const view = [...document.querySelectorAll("main > .view")].find((el) => !el.hidden);
            return { shell: rect(main), view: rect(view), footer: rect(document.querySelector("#footer-panel") || document.querySelector("footer")),
              headerLogo: rect(document.querySelector(".brand")), scrollWidth: document.documentElement.scrollWidth,
              footerPosition: getComputedStyle(document.querySelector("footer")).position };
          });
          evidence.edges.push({ label, viewport, theme, route: name, ...edges });
          if (label === "before") continue;
          const outer = Math.min(1240, viewport.width), gutter = viewport.width <= 640 ? 14 : 24;
          const expected = { left: (viewport.width - outer) / 2 + gutter, right: (viewport.width + outer) / 2 - gutter, width: outer - gutter * 2 };
          for (const target of ["view", "footer"]) for (const edge of ["left", "right", "width"]) {
            assert.ok(Math.abs(edges[target][edge] - expected[edge]) <= 2,
              `${prefix} ${name} ${target}.${edge}=${edges[target][edge]}, expected ${expected[edge]}`);
          }
          assert.ok(Math.abs(edges.headerLogo.left - expected.left) <= 2, "header inner row aligns with shared gutter");
          assert.ok(edges.scrollWidth <= viewport.width + 2, `${prefix} ${name} must not overflow horizontally`);
          assert.doesNotMatch(await page.locator("main > .view:visible").textContent(), /\b(?:null|undefined)\b/,
            `${prefix} ${name} cannot stringify an empty optional node`);
          assert.equal(edges.footerPosition, "static", "footer stays in document flow");
          const footerLinks = page.locator("footer a");
          assert.equal(await footerLinks.count(), 6);
          for (const link of await footerLinks.all()) {
            assert.equal(await link.isVisible(), true, `${prefix}: footer links remain visible with mobile header menu closed`);
            await link.scrollIntoViewIfNeeded();
            const box = await link.boundingBox();
            assert.ok(box.width >= 24 && box.height >= 44, `${prefix}: footer links have comfortable touch targets`);
            await link.focus();
            assert.equal(await link.evaluate((el) => el === document.activeElement), true, "footer links are keyboard focusable");
            assert.equal(await link.evaluate((el) => getComputedStyle(el).outlineStyle), "solid", "footer links expose visible keyboard focus");
          }
          assert.equal(await page.locator("#site-nav").isVisible(), viewport.width > 900, "closed mobile header cannot hide footer navigation");
          if (name === "home") {
            await page.locator(".utility-links a").first().focus();
            await page.keyboard.press("Enter");
            await page.waitForURL(/#about$/);
            assert.equal(await page.locator("#about").isVisible(), true, "footer About uses application route");
          }
          if (name === "gallery") {
            const categories = await page.locator("#scenario-category option").count();
            for (let i = 0; i < categories; i++) {
              await page.selectOption("#scenario-category", String(i), { force: true });
              assert.doesNotMatch(await page.locator("#scenario-panel").textContent(), /\b(?:null|undefined)\b/,
                "every gallery category omits optional-node placeholders");
              const learning = page.locator("#scenario-panel .learning-cases");
              if (await learning.count()) {
                await learning.evaluate((el) => { el.open = true; });
                assert.ok(await learning.locator(".learning-card").count() > 0, "actual learning cases remain available");
              }
            }
          }
        }
        if (label === "after") {
          await page.goto(`${url}?scoutTheme=${theme}#about`);
          await page.locator("#guide-stage[data-account]").waitFor({ state: "attached" });
          await page.locator("#about details").evaluateAll((els) => els.forEach((el) => { el.open = true; }));
          await shot(page, `${prefix}-about-expanded`, true);
          await page.locator("footer").scrollIntoViewIfNeeded();
          const footer = page.locator("#footer-panel");
          const footerScreenshot = `${prefix}-footer.png`;
          await footer.screenshot({ path: path.join(out, footerScreenshot) });
          evidence.screenshots.push(footerScreenshot);
          await page.goto(`${url}?scoutTheme=${theme}#guide/qsr/northwind`);
          await page.locator("#guide-stage[data-account=northwind]").waitFor({ state: "attached" });
          async function guideStep() {
            const step = await page.locator("#guide-wrap").getAttribute("data-step");
            const controls = ["#guide-example", "#guide-prev", "#guide-next", "#guide-options > summary"];
            if (await page.locator("#guide-playback").isVisible()) controls.push("#guide-play", "#sound");
            for (const selector of controls) {
              const control = page.locator(selector);
              await control.scrollIntoViewIfNeeded();
              const usable = await control.evaluate((el) => {
                const r = el.getBoundingClientRect();
                const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                return r.width > 0 && r.height > 0 && (hit === el || el.contains(hit));
              });
              assert.equal(usable, true, `${prefix} ${step} ${selector} must be reachable and unobscured`);
            }
            const media = await page.locator("#guide-stage video").evaluateAll((els) => els.map((el) => ({
              clip: el.dataset.clip, fit: getComputedStyle(el).objectFit,
              width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
            })));
            for (const m of media) assert.ok(m.fit === "contain" && m.width > 0 && m.height > 0, "media remains uncropped and visible");
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), true, "Guide controls cannot widen the page");
            const screenshot = await shot(page, `${prefix}-guide-${step}`, true);
            evidence.guide.push({ viewport, theme, step, media, screenshot });
          }
          await guideStep();
          await page.locator("#guide-next").click();
          await guideStep();
          await page.locator(".concept-thumb").nth(1).click();
          await page.locator("button.select").click();
          await page.locator("#guide-next").click();
          await guideStep();
          const normal = await page.locator("#guide-wrap").boundingBox();
          await page.locator("#guide-options > summary").click();
          await page.locator("#guide-full").click();
          await page.waitForFunction(() => !!document.fullscreenElement);
          await settle(page);
          const fullscreen = await page.locator("#guide-wrap").boundingBox();
          assert.ok(Math.abs(fullscreen.width - viewport.width) <= 2, "intentional fullscreen uses viewport");
          await shot(page, `${prefix}-guide-fullscreen`);
          await page.locator("#guide-options > summary").click();
          await page.locator("#guide-full").click();
          await page.waitForFunction(() => !document.fullscreenElement);
          await settle(page);
          const restored = await page.locator("#guide-wrap").boundingBox();
          assert.ok(Math.abs(restored.width - normal.width) <= 2 && Math.abs(restored.x - normal.x) <= 2,
            "exiting fullscreen restores shared frame");
          evidence.fullscreen.push({ viewport, theme, normal, fullscreen, restored });
          await page.locator("#guide-next").click();
          await guideStep();
          if ([1440, 390].includes(viewport.width) && theme === "light") {
            const data = await (await ctx.request.get(`${candidate}data.json`)).json();
            for (const account of data.accounts.filter((a) => a.id !== "northwind")) {
              await page.goto(`${url}#guide/${account.area}/${account.id}`);
              await page.locator(`#guide-stage[data-account="${account.id}"]`).waitFor({ state: "attached" });
              for (let i = 0; i < 3; i++) {
                await settle(page);
                const step = await page.locator("#guide-wrap").getAttribute("data-step");
                assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2), true,
                  `${account.id} ${step} cannot overflow shared frame`);
                for (const selector of ["#guide-example", "#guide-next", "#guide-options > summary"]) {
                  const box = await page.locator(selector).boundingBox();
                  assert.ok(box.width > 0 && box.x >= 0 && box.x + box.width <= viewport.width + 2,
                    `${account.id} ${step} controls fit the frame`);
                }
                const media = await page.locator("#guide-stage video").evaluateAll((els) => els.map((el) => ({
                  clip: el.dataset.clip, fit: getComputedStyle(el).objectFit,
                  width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
                })));
                assert.ok(media.every((m) => m.fit === "contain" && m.width > 0 && m.height > 0),
                  `${account.id} ${step} keeps media visible without cropping: ${JSON.stringify(media)}`);
                evidence.examples.push({ viewport, account: account.id, step, media });
                if (i < 2) await page.locator("#guide-next").click();
              }
            }
          }
        }
        assert.deepEqual(errors, [], "no script errors");
        await ctx.close();
      }
      const tileWidth = viewport.width === 390 ? 234 : 360;
      const sheet = await browser.newPage({ viewport: { width: tileWidth * 5 + 80, height: 100 }, deviceScaleFactor: 1 });
      const html = `<html><head><style>body{margin:0;padding:16px;background:#ededed;color:#242424;font:14px "Segoe UI",sans-serif}h1{font-size:20px}main{display:grid;grid-template-columns:repeat(5,${tileWidth}px);gap:12px}figure{margin:0}img{display:block;width:${tileWidth}px;height:auto}figcaption{padding:8px 0;font-weight:600}</style></head><body><h1>Same viewport, theme and 100% zoom: ${viewport.width} x ${viewport.height}, ${theme}. Before row / after row.</h1><main>${tiles.map((t) =>
        `<figure><figcaption>${t.label}: ${t.name}</figcaption><img src="data:image/png;base64,${fs.readFileSync(path.join(out, t.screenshot)).toString("base64")}"></figure>`).join("")}</main></body></html>`;
      await sheet.setContent(html);
      const file = `comparison-${viewport.width}x${viewport.height}-${theme}.png`;
      await sheet.screenshot({ path: path.join(out, file), fullPage: true });
      evidence.sheets.push(file);
      await sheet.close();
    }
    evidence.passed = true;
  } finally {
    fs.writeFileSync(path.join(out, "shared-frame-evidence.json"), JSON.stringify(evidence, null, 2));
    await browser.close();
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
