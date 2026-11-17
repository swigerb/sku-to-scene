// Real Chromium acceptance: no service calls or package installation.
// PLAYWRIGHT_MODULE may point to an existing Playwright installation.
// node tests/ux-regressions.cjs <baseline-url> <candidate-url> <artifact-directory>
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const [baseline, candidate, out] = process.argv.slice(2);
assert.ok(baseline && candidate && out, "baseline URL, candidate URL and artifact directory are required");
fs.mkdirSync(out, { recursive: true });
const evidence = { baseline, candidate, baselineSha: process.env.BASELINE_SHA, screenshots: [], geometry: [], routing: [], states: [] };
const allowed = new Set([new URL(baseline).origin, new URL(candidate).origin]);
const settle = async (page) => {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
};
async function shot(page, name) {
  const file = `${name}.png`;
  await page.evaluate(() => scrollTo(0, 0));
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({ path: path.join(out, file), fullPage: true });
  evidence.screenshots.push(file);
  return file;
}
async function main() {
  const browser = await chromium.launch({ headless: true });
  try {
    async function context(viewport, theme = "light", reviewFailure = null) {
      const ctx = await browser.newContext({ viewport, colorScheme: theme, reducedMotion: "reduce" });
      await ctx.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        if (!allowed.has(url.origin)) return route.abort("blockedbyclient");
        if (reviewFailure && url.pathname.endsWith("/evaluations/human-review.json")) {
          if (reviewFailure === "missing") return route.fulfill({ status: 404, body: "unavailable" });
          return route.fulfill({ contentType: "application/json", body: reviewFailure === "malformed-json" ? "{" : '{"findings":[{}]}' });
        }
        return route.continue();
      });
      return ctx;
    }
    for (const viewport of [{ width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      for (const theme of ["light", "dark"]) {
        for (const [label, url] of [["before", baseline], ["after", candidate]]) {
          const ctx = await context(viewport, theme);
          const page = await ctx.newPage();
          await page.goto(`${url}?scoutTheme=${theme}`);
          await page.locator(".source-history").waitFor();
          await settle(page);
          const positions = () => page.evaluate(() => Object.fromEntries(
            ["#hero-title", ".hero-copy .lede", ".hero-copy .cta"].map((selector) => {
              const r = document.querySelector(selector).getBoundingClientRect();
              return [selector, { x: r.x + scrollX, y: r.y + scrollY }];
            })));
          const prefix = `${label}-${viewport.width}x${viewport.height}-${theme}`;
          const closed = await positions();
          await shot(page, `${prefix}-collapsed`);
          await page.locator(".source-history > summary").click();
          await settle(page);
          const opened = await positions();
          await shot(page, `${prefix}-expanded`);
          await page.locator(".source-history > summary").click();
          await settle(page);
          const reclosed = await positions();
          await shot(page, `${prefix}-recollapsed`);
          const deltas = Object.fromEntries(Object.keys(closed).map((selector) => [selector, {
            expandedX: opened[selector].x - closed[selector].x,
            expandedY: opened[selector].y - closed[selector].y,
            collapsedX: reclosed[selector].x - closed[selector].x,
            collapsedY: reclosed[selector].y - closed[selector].y,
          }]));
          evidence.geometry.push({ label, viewport, theme, closed, opened, reclosed, deltas });
          if (label === "after") {
            for (const [selector, delta] of Object.entries(deltas)) {
              for (const [state, pixels] of Object.entries(delta)) assert.ok(Math.abs(pixels) <= 2,
                `${prefix}: ${selector} ${state} moved ${pixels}px`);
            }
            const links = page.locator("#site-nav a");
            assert.deepEqual(await links.allTextContents(), ["Home", "Guided demo", "Scenario gallery", "Technical evidence", "About"]);
            if (viewport.width < 600) {
              await page.locator("#menu-toggle").click();
              await page.keyboard.press("Tab");
            } else {
              await page.locator(".brand").focus();
              await page.keyboard.press("Tab");
            }
            assert.equal(await page.evaluate(() => document.activeElement.textContent.trim()), "Home");
            await page.keyboard.press("Enter");
            await settle(page);
            assert.equal(await page.locator("#site-nav a[aria-current=page]").textContent(), "Home");
            assert.equal(await page.evaluate(() => document.activeElement.id), "hero-title");
            assert.equal(await page.evaluate(() => scrollY), 0);
          } else if (viewport.width > 1000) {
            assert.ok(deltas["#hero-title"].expandedY > 100, "baseline must reproduce the real hero regression");
          }
          await ctx.close();
        }
      }
    }
    const ctx = await context({ width: 1440, height: 900 });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const data = await (await ctx.request.get(`${candidate}data.json`)).json();
    const accountRoute = (id) => {
      const a = data.accounts.find((a) => a.id === id);
      return `#guide/${a.area}/${id}`;
    };
    const snapshot = () => page.evaluate(() => ({
      hash: location.hash, account: document.querySelector("#guide-stage").dataset.account,
      step: document.querySelector("#guide-wrap").dataset.step,
      selected: document.querySelector("button.select")?.getAttribute("aria-pressed") || null,
      nextDisabled: document.querySelector("#guide-next").disabled,
    }));
    async function aboutRoundTrip(name, alias = "#about") {
      const before = await snapshot();
      const beforeScreenshot = await shot(page, `${name}-before`);
      const player = await page.locator("#guide-stage video").elementHandle();
      await page.evaluate((href) => {
        const a = document.createElement("a");
        a.href = href;
        document.body.append(a);
        a.click();
        a.remove();
      }, alias);
      await settle(page);
      assert.equal(await page.locator("#about").isVisible(), true);
      assert.equal(await page.locator("#site-nav a[aria-current=page]").textContent(), "About");
      if (player) assert.equal(await player.evaluate((v) => v.paused), true, "hidden media must pause");
      const aboutScreenshot = await shot(page, `${name}-about`);
      await page.goBack();
      await settle(page);
      const returned = await snapshot();
      assert.deepEqual(returned, before, `${name}: browser Back preserves exact account/step/selection`);
      const returnedScreenshot = await shot(page, `${name}-returned`);
      await page.goForward();
      await settle(page);
      assert.equal(await page.locator("#about").isVisible(), true);
      await page.goBack();
      await settle(page);
      assert.deepEqual(await snapshot(), before, "Forward then Back preserves state too");
      evidence.routing.push({ name, before, returned, beforeScreenshot, aboutScreenshot, returnedScreenshot });
    }
    await page.goto(`${candidate}${accountRoute("tailspin")}`);
    await page.locator("#guide-stage[data-account=tailspin]").waitFor();
    await page.locator("#guide-next").click();
    await settle(page);
    assert.equal((await snapshot()).step, "result");
    await page.locator("#guide-play").click();
    await page.waitForFunction(() => !document.querySelector("#guide-stage video").paused);
    const tailspinResult = await snapshot();
    await page.evaluate(() => {
      const a = document.createElement("a");
      a.href = "#guide-heading";
      document.body.append(a);
      a.click();
      a.remove();
    });
    await settle(page);
    const anchorResult = await snapshot();
    assert.equal(anchorResult.account, tailspinResult.account, "informational anchors inside Guide cannot reroute the account");
    assert.equal(anchorResult.step, tailspinResult.step, "informational anchors inside Guide cannot reset the step");
    await page.goBack();
    await settle(page);
    await aboutRoundTrip("tailspin-result");
    await page.goto(`${candidate}${accountRoute("northwind")}`);
    await page.locator("#guide-stage[data-account=northwind]").waitFor();
    await page.locator("#guide-next").click();
    await page.locator(".concept-thumb").nth(1).click();
    await page.locator("button.select").click();
    assert.equal((await snapshot()).selected, "true");
    await aboutRoundTrip("northwind-selected-concept", "#about-demo");
    await page.locator("#guide-next").click();
    assert.equal((await snapshot()).step, "result");
    await page.locator("#guide-options > summary").click();
    await page.locator("#guide-restart").click();
    assert.equal((await snapshot()).step, "brief", "explicit restart still resets");
    await page.locator("#guide-next").click();
    assert.equal((await snapshot()).nextDisabled, true, "restart clears concept selection");
    for (const hash of ["#top", "#home", ""]) {
      await page.goto(`${candidate}${hash}`);
      await page.locator(".source-history").waitFor();
      assert.equal(await page.locator("#view-home").isVisible(), true);
      assert.equal(await page.locator("#site-nav a[aria-current=page]").textContent(), "Home");
      evidence.routing.push({ alias: hash || "(root)", view: "home" });
    }
    await page.goto(`${candidate}#evals`);
    await page.locator("#evidence-scope option").first().waitFor({ state: "attached" });
    async function selectScope(id) {
      await page.selectOption("#evidence-scope", id);
      await page.locator("#evals").evaluate((el) => { el.open = true; });
      await page.locator("#evals").scrollIntoViewIfNeeded();
      await settle(page);
      assert.doesNotMatch(await page.locator("#evals-body").textContent(), /\b(?:null|undefined)\b/,
        "real DOM must not stringify conditional placeholders");
    }
    const tailspin = data.accounts.find((a) => a.id === "tailspin");
    await selectScope(tailspin.hero_clip || tailspin.recorded_clip);
    const empty = await page.locator("#evals-body").textContent();
    assert.match(empty, /No Foundry Evaluations run is recorded for this example/);
    assert.match(empty, /No additional review notes are recorded for this recording/);
    assert.doesNotMatch(empty, /No targeted v2|Targeted direct/);
    assert.equal(await page.locator(".additional-review details").count(), 0);
    evidence.states.push({ state: "empty", scope: await page.inputValue("#evidence-scope"), screenshot: await shot(page, "evaluations-empty-tailspin") });
    await selectScope("lto-hero-kling");
    assert.match(await page.locator(".additional-review").textContent(), /human review \(presenter, browser playback\)/);
    assert.match(await page.locator(".additional-review").textContent(), /frothing sound/);
    assert.ok((await page.locator(".additional-review .finding").boundingBox()).width > 500,
      "a single scoped finding must have readable width rather than empty grid columns");
    assert.ok(await page.locator("#evals-body .check-card").count() > 0);
    assert.equal(await page.locator("#evals details details").count(), 0, "no triple-nested disclosures");
    evidence.states.push({ state: "populated-source", scope: "lto-hero-kling", screenshot: await shot(page, "evaluations-populated-source") });
    await selectScope("zava-silent-presentation-v1");
    assert.match(await page.locator("#evals-body").textContent(), /not Foundry Evals service runs/);
    assert.equal(await page.locator("[data-check=zava-concept-v2]").count(), 1);
    evidence.states.push({ state: "targeted", scope: "zava-silent-presentation-v1", screenshot: await shot(page, "evaluations-zava-targeted") });
    await selectScope(data.lto.hero_clip);
    assert.doesNotMatch(await page.locator(".additional-review").textContent(), /frothing sound|human review \(presenter/);
    assert.match(await page.locator(".additional-review").textContent(), /No additional review notes/);
    assert.equal(await page.locator("[data-check=zava-concept-v2]").count(), 0, "scope changes clear stale targeted results");
    evidence.states.push({ state: "derivative-no-native-notes", scope: data.lto.hero_clip, screenshot: await shot(page, "evaluations-silent-derivative") });
    await page.locator("#evals .legend > summary").click();
    await shot(page, "evaluations-interpretation-expanded");
    await page.locator("#historical-evals details").nth(1).locator("summary").click();
    await page.locator("#historical-heading").scrollIntoViewIfNeeded();
    await shot(page, "historical-comparison-expanded");
    await page.locator("#historical-evals details").evaluateAll((items) => items.forEach((el) => { el.open = true; }));
    await shot(page, "historical-all-expanded");
    await page.goto(`${candidate}#about-demo`);
    await page.locator("#about-heading").waitFor();
    assert.equal(await page.locator("#about").isVisible(), true, "legacy About alias supports direct loads");
    await page.locator("#about details").evaluateAll((items) => items.forEach((el) => { el.open = true; }));
    await shot(page, "about-supporting-details-expanded");
    assert.deepEqual(errors, [], "candidate must not raise browser script errors");
    await ctx.close();
    for (const failure of ["missing", "malformed-json", "malformed-data"]) {
      const failCtx = await context({ width: 1440, height: 900 }, "light", failure);
      const failPage = await failCtx.newPage();
      await failPage.goto(`${candidate}#evals`);
      await failPage.locator("#evidence-scope option").first().waitFor({ state: "attached" });
      await failPage.selectOption("#evidence-scope", tailspin.hero_clip || tailspin.recorded_clip);
      await failPage.locator("#evals").evaluate((el) => { el.open = true; });
      await failPage.locator("#evals").scrollIntoViewIfNeeded();
      assert.match(await failPage.locator("#evals-body").textContent(), /Human-review evidence unavailable/);
      assert.doesNotMatch(await failPage.locator("#evals-body").textContent(), /No additional review notes are recorded/);
      assert.doesNotMatch(await failPage.locator("#evals-body").textContent(), /\b(?:null|undefined)\b/);
      evidence.states.push({ state: failure, screenshot: await shot(failPage, `evaluations-unavailable-${failure}`) });
      await failCtx.close();
    }
    evidence.passed = true;
  } finally {
    fs.writeFileSync(path.join(out, "ux-evidence.json"), JSON.stringify(evidence, null, 2));
    await browser.close();
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
