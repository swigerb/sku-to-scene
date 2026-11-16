// Dependency-free DOM/media double: execute the shipped app.js and exercise its real event handlers.
// Usage: node tests/playback.cjs <app.js> [mode] < {"data":…, "ev":…, "hr":…}
// Views are hash-routed; #routing/#qa/#evals are stubbed as <details> so deep links can be checked.
// Modes: ok (default) | hr-404 | hr-network | hr-malformed-json | hr-malformed-data | hr-null-finding |
//        hr-empty-finding | hr-unknown-severity
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const mode = process.argv[3] || "ok";
const roots = new Map();
const documentListeners = {};
const requests = [];
const storage = new Map();
if (mode === "theme-url-light" || mode === "theme-stored-dark") storage.set("s2s-theme", "dark");
if (mode === "theme-url-dark" || mode === "theme-stored-light") storage.set("s2s-theme", "light");
if (mode === "theme-invalid") storage.set("s2s-theme", "broken");
const search = mode === "theme-url-light" ? "?scoutTheme=light" : mode === "theme-url-dark" ? "?scoutTheme=dark"
  : mode === "theme-invalid" ? "?scoutTheme=broken" : "";

class Element {
  constructor(tag) {
    this.tag = tag;
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.className = "";
    this.paused = true;
    this.hidden = false;
    this.disabled = false;
    this.readyState = 0;
    this.error = null;
    this._text = null;
    this._value = undefined;
    const names = () => new Set(this.className.split(" ").filter(Boolean));
    this.classList = {
      add: (n) => { const s = names(); s.add(n); this.className = [...s].join(" "); },
      remove: (n) => { const s = names(); s.delete(n); this.className = [...s].join(" "); },
      contains: (n) => names().has(n),
      toggle: (n, on) => {
        const s = names();
        if (on === undefined ? !s.has(n) : on) s.add(n); else s.delete(n);
        this.className = [...s].join(" ");
      },
    };
  }
  setAttribute(key, value) {
    this.attrs[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-(\w)/g, (_, c) => c.toUpperCase())] = String(value);
  }
  getAttribute(key) { return this.attrs[key]; }
  removeAttribute(key) { delete this.attrs[key]; }
  get textContent() { return this._text !== null ? this._text : this.children.map((c) => c.textContent).join(""); }
  set textContent(t) { this._text = String(t); this.children = []; }
  get value() {
    if (this._value !== undefined) return this._value;
    if (this.attrs.value !== undefined) return this.attrs.value;
    const first = this.children.find((c) => c.tag === "option");
    return first ? first.value : "";
  }
  set value(v) { this._value = String(v); }
  append(...kids) { this.children.push(...kids.map(node)); }
  prepend(...kids) { this.children.unshift(...kids.map(node)); }
  replaceChildren(...kids) { this.children = kids.map(node); this._text = null; if (this.children.some((c) => c.tag === "option")) this._value = undefined; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  querySelectorAll(selector) {
    const [tag, cls] = selector.split(".");
    const matches = (el) => (!tag || el.tag === tag) && (!cls || el.className.split(" ").includes(cls));
    return this.children.flatMap((el) => [...(matches(el) ? [el] : []), ...el.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  dispatch(name, extra = {}) {
    const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
    for (const fn of documentListeners[name] || []) fn(event);
    for (const fn of this.listeners[name] || []) fn(event);
    return event;
  }
  play() {
    if (failures.play) return Promise.reject(Object.assign(new Error("blocked"), { name: "NotAllowedError" }));
    this.paused = false; this.dispatch("play"); return Promise.resolve();
  }
  pause() { if (!this.paused) { this.paused = true; this.dispatch("pause"); } }
  scrollIntoView() { scrolled.push(this); }
  click() { if (!this.disabled) this.dispatch("click"); }
  focus() { document.activeElement = this; }
  requestFullscreen() {
    fullscreenRequests.push(this);
    return failures.fullscreen ? Promise.reject(Object.assign(new Error("denied"), { name: "TypeError" })) : Promise.resolve();
  }
}
class TextNode extends Element {
  constructor(text) { super("#text"); this._text = String(text); }
}
const fullscreenRequests = [];
const scrolled = [];
const windowListeners = {};
const DETAILS = new Set(["#routing", "#qa", "#evals"]);
const failures = { play: false, fullscreen: false };
const node = (k) => (k instanceof Element ? k : new TextNode(k));

const document = {
  activeElement: null,
  fullscreenEnabled: true,
  fullscreenElement: null,
  exitFullscreen: () => Promise.resolve(),
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => new TextNode(text),
  documentElement: new Element("html"),
  getElementById: (id) => roots.get(`#${id}`) || null,
  querySelector: (selector) => {
    if (!roots.has(selector)) roots.set(selector, new Element(DETAILS.has(selector) ? "details" : "div"));
    return roots.get(selector);
  },
  querySelectorAll: (selector) => [...roots.values()].flatMap((el) => el.querySelectorAll(selector)),
  addEventListener: (name, fn) => { (documentListeners[name] ??= []).push(fn); },
};
const json = (body) => ({ ok: true, status: 200, json: async () => body });
const context = vm.createContext({
  document,
  Node: Element,
  HTMLVideoElement: { [Symbol.hasInstance]: (x) => x instanceof Element && x.tag === "video" },
  window: {
    location: { hash: "", search },
    matchMedia: () => ({ matches: ["theme-url-light", "theme-stored-light", "theme-system-dark", "theme-storage-blocked"].includes(mode) }),
    addEventListener: (name, fn) => { (windowListeners[name] ??= []).push(fn); },
    scrollTo: () => {},
  },
  URLSearchParams,
  localStorage: {
    getItem: (key) => { if (mode === "theme-storage-blocked") throw new Error("blocked"); return storage.get(key); },
    setItem: (key, value) => { if (mode === "theme-storage-blocked") throw new Error("blocked"); storage.set(key, value); },
  },
  fetch: async (url, options) => {
    requests.push({ url, options });
    if (url === "data.json") return json(input.data);
    if (url.endsWith("foundry-evals-v1.json")) return json(input.ev);
    if (mode === "hr-404") return { ok: false, status: 404, json: async () => { throw new Error("no body"); } };
    if (mode === "hr-network") throw new TypeError("Failed to fetch");
    if (mode === "hr-malformed-json") return { ok: true, status: 200, json: async () => { throw new SyntaxError("Unexpected token <"); } };
    if (mode === "hr-malformed-data") return json({ findings: "not-a-list" });
    const broken = { "hr-null-finding": null, "hr-empty-finding": {}, "hr-unknown-severity": { ...input.hr.findings[0], severity: "blocker?" } };
    if (mode in broken) return json({ ...input.hr, findings: [...input.hr.findings, broken[mode]] });
    return json(input.hr);
  },
  setTimeout: () => { throw new Error("the guided demo must not use timers"); },
  setInterval: () => { throw new Error("the guided demo must not use timers"); },
});
vm.runInContext(input.theme_script, context);
vm.runInContext(fs.readFileSync(process.argv[2] || "site/app.js", "utf8"), context);

setImmediate(() => {
  const $ = (selector) => document.querySelector(selector);
  const text = (el) => el.textContent;

  assert.deepEqual(requests.map((r) => r.url).sort(), [
    "data.json", "evaluations/foundry-evals-v1.json", "evaluations/human-review.json",
  ]);
  assert.ok(requests.every((r) => r.options?.cache === "no-cache"), "all mutable JSON must revalidate");

  const heroRoot = () => $("#hero-compare");
  const VIEW_IDS = { home: "#view-home", guide: "#guide", scenarios: "#scenarios", evidence: "#evidence" };
  const shown = () => Object.entries(VIEW_IDS).filter(([, sel]) => !$(sel).hidden).map(([k]) => k);
  const navigate = (hash) => {
    context.window.location.hash = hash;
    for (const fn of windowListeners.hashchange || []) fn({});
  };
  const pills = (root) => root.querySelectorAll("span.pill").filter((s) => s.attrs["data-readiness"]);
  assert.deepEqual(shown(), ["home"], "the landing view is shown alone on load");
  const expectedTheme = ["theme-url-dark", "theme-stored-dark", "theme-system-dark", "theme-storage-blocked"].includes(mode) ? "dark" : "light";
  assert.equal(document.documentElement.getAttribute("data-theme"), expectedTheme, `${mode}: URL > storage > system`);
  const themeButtons = [$("#theme-light"), $("#theme-dark")];
  const themeChoice = () => themeButtons.map((b) => b.getAttribute("aria-checked"));
  assert.deepEqual(themeChoice(), expectedTheme === "light" ? ["true", "false"] : ["false", "true"]);
  $("#theme-dark").click();
  assert.equal(document.documentElement.getAttribute("data-theme"), "dark");
  assert.deepEqual(themeChoice(), ["false", "true"], "theme has exactly one selected option");
  $("#theme-toggle").dispatch("keydown", { key: "Home" });
  assert.equal(document.activeElement, $("#theme-light"));
  assert.deepEqual(themeButtons.map((b) => b.getAttribute("tabindex")), ["0", "-1"]);
  $("#theme-toggle").dispatch("keydown", { key: "End" });
  assert.equal(document.activeElement, $("#theme-dark"));
  $("#theme-toggle").dispatch("keydown", { key: "ArrowRight" });
  assert.deepEqual(themeChoice(), ["true", "false"], "theme arrow wraps and selects");
  assert.equal(document.activeElement, $("#theme-light"));
  if (mode !== "theme-storage-blocked") assert.equal(storage.get("s2s-theme"), "light", "theme selection persists");
  if (mode.startsWith("hr-")) {
    assert.equal($("#review-alert").hidden, false, "unavailable alert is shown");
    assert.match(text($("#review-alert")), /Human-review evidence unavailable/);
    assert.match(text($("#readiness-summary")), /Human-review evidence unavailable/);
    assert.doesNotMatch(text($("#readiness-summary")), /open publication blockers/, "unavailable must not render a blocker count");
    assert.doesNotMatch(text(heroRoot()), /Publication blocked|Human sign-off required\./, "unavailable must not show a reviewed state");
    assert.match(text(heroRoot()), /Human-review evidence unavailable/);
    $("#guide-next").click();
    assert.ok(pills($("#guide-stage")).length >= 3 && pills($("#guide-stage")).every((s) => s.attrs["data-readiness"] === "unavailable"),
      "every visible draft says review evidence is unavailable");
    console.log(`human-review ${mode} handled`);
    return;
  }
  assert.equal(text($("#review-alert")), "", "no unavailable alert when the review record loads");
  assert.match(text(heroRoot()), /Publication blocked\./);
  assert.match(text($("#readiness-summary")), /1open publication blockers/);

  // ---------- guided demo ----------
  const lto = input.data.lto;
  const stage = $("#guide-stage");
  const status = () => text($("#guide-status"));
  const prev = $("#guide-prev"), next = $("#guide-next"), play = $("#guide-play");
  const cards = () => stage.querySelectorAll("article").filter((a) => a.classList.contains("draft") && a.dataset.variant);
  const vid = (i) => cards()[i].querySelector("video");
  const selectButtons = () => stage.querySelectorAll("button.select");
  const withheld = new Set(input.data.clips.filter((c) => c.withheld_reason).map((c) => c.id));
  const noWithheldPlayers = (root) => root.querySelectorAll("video").every((v) => !withheld.has(v.dataset.clip));

  assert.match(status(), /Step 1 of 5: Brief/);
  assert.ok(prev.disabled && play.disabled, "brief step has no previous step or video");
  next.click();
  assert.match(status(), /Step 2 of 5/);
  assert.equal(cards().length, 3);
  assert.ok(noWithheldPlayers(stage), "withheld account attempts are not guided preview players");
  assert.ok(cards().every((c) => pills(c).length === 1 && /sign-off required|blocked|decision|Awaiting human review/.test(text(pills(c)[0]))),
    "each visible draft shows its publication readiness outside Inspect evidence");
  assert.equal(selectButtons().length, 0, "the compare step offers no selection");
  assert.equal(play.textContent, "Play");
  play.click();
  assert.ok(!vid(0).paused, "Play drives the default preview");
  vid(2).play();
  assert.ok(vid(0).paused && !vid(2).paused, "one player at a time");
  assert.equal(play.textContent, "Pause");
  play.click();
  assert.ok(vid(2).paused, "Pause drives the last previewed draft");

  next.click();
  assert.ok(noWithheldPlayers(stage), "QSR: withheld attempts remain evidence, not previews");
  assert.match(status(), /Step 3 of 5: Choose a concept/);
  assert.ok(next.disabled, "Next waits for a selection");
  assert.equal(selectButtons().length, 1, "only the recorded hero concept is selectable");
  const heroCard = cards()[lto.hero_variant - 1];
  assert.equal(heroCard.querySelector("button.select"), selectButtons()[0]);
  assert.match(text(heroCard), /Recorded hero available/);
  cards().forEach((c, i) => {
    if (i !== lto.hero_variant - 1) assert.match(text(c), /Concept preview only[\s\S]*Preview only: this replay has no recorded hero/);
  });
  vid(lto.hero_variant - 1).play();
  assert.equal(selectButtons()[0].getAttribute("aria-pressed"), "false", "previewing never selects");
  assert.ok(next.disabled, "previewing never selects");
  const other = vid(lto.hero_variant === 3 ? 0 : 2);
  other.play();
  selectButtons()[0].click();
  assert.ok(other.paused, "selecting pauses other previews");
  assert.equal(selectButtons()[0].getAttribute("aria-pressed"), "true");
  assert.match(status(), new RegExp(`Concept #${lto.hero_variant} selected`));
  assert.ok(!next.disabled, "selection unlocks the hero step");

  next.click();
  assert.match(status(), /Step 4 of 5: Recorded hero/);
  assert.ok(cards().every((c) => c.querySelector("video").paused), "leaving a step pauses its players");
  const hero = stage.querySelector("video");
  assert.equal(hero.dataset.clip, lto.hero_clip);
  play.click();
  assert.ok(!hero.paused, "Play drives the hero");
  const heroNotes = stage.querySelectorAll("p").filter((p) => p.classList.contains("audio-note"));
  assert.match(text(heroNotes[0]), /Played here at 50% volume/, "plain-language sound note stays visible");
  const heroInspect = stage.querySelector("details");
  assert.ok(heroInspect && /LUFS/.test(text(heroInspect)), "signal metrics live in Inspect evidence");
  assert.doesNotMatch(text(stage).replace(text(heroInspect), ""), /LUFS|dBTP/, "no signal metrics outside evidence");
  next.click();
  assert.ok(hero.paused, "moving on pauses the replaced hero");
  assert.match(status(), /Step 5 of 5/);
  assert.match(text(stage), /Publication blocked\./);
  assert.ok(next.disabled, "last step");
  const reviewHero = stage.querySelector("video");
  reviewHero.play();
  $("#guide-restart").click();
  assert.ok(reviewHero.paused, "restart pauses the hero");
  assert.match(status(), /Step 1 of 5/);
  next.click(); next.click();
  assert.ok(next.disabled, "restart clears the selection");

  const wrap = $("#guide-wrap");
  wrap.dispatch("keydown", { key: "ArrowLeft" });
  assert.match(status(), /Step 2 of 5/, "ArrowLeft goes back");
  wrap.dispatch("keydown", { key: "ArrowRight", target: new Element("video") });
  assert.match(status(), /Step 2 of 5/, "arrow keys on a video are left to the player");
  const ev = wrap.dispatch("keydown", { key: "ArrowRight" });
  assert.match(status(), /Step 3 of 5/);
  assert.ok(ev.defaultPrevented);
  assert.equal($("#guide-full").hidden, false);
  $("#guide-full").click();
  assert.equal(fullscreenRequests[0], wrap, "fullscreen targets the guide");
  assert.equal($("#guide-alert").hidden, true);

  // ---------- views ----------
  navigate("#guide");
  assert.deepEqual(shown(), ["guide"]);
  assert.equal(document.activeElement, $("#guide-heading"), "a view change moves focus to its heading");
  const guidePlayer = stage.querySelector("video");
  guidePlayer.play();
  navigate("#main");
  assert.deepEqual(shown(), ["guide"], "the skip link stays in the current view");
  navigate("#scenarios");
  assert.deepEqual(shown(), ["scenarios"]);
  assert.ok(guidePlayer.paused, "hiding a view pauses its players");
  for (const deep of ["#routing", "#qa", "#evals"]) {
    $(deep).open = false;
    navigate(deep);
    assert.deepEqual(shown(), ["evidence"], `${deep} opens the evidence view`);
    assert.equal($(deep).open, true, `${deep} expands its section`);
    assert.equal(scrolled.at(-1), $(deep), `${deep} scrolls to its section`);
  }
  navigate("");
  assert.deepEqual(shown(), ["home"]);
  const entry = $("#entry-grid").children[2];
  entry.click();
  assert.deepEqual(shown(), ["guide"], "a scenario card opens its area guide");
  assert.match(text($("#guide-area-label")), /Home Improvement/);
  assert.equal(document.activeElement, $("#guide-heading"), "with focus on the guide heading");
  for (const [area, heroId] of [["apparel", "hero-apparel-kling"], ["home", "hero-home-kling"], ["grocery", "hero-grocery-turbo"]]) {
    navigate(`#guide/${area}`);
    assert.deepEqual(shown(), ["guide"], `#guide/${area} opens the guide`);
    const accounts = input.data.accounts.filter((a) => a.area === area);
    assert.match(status(), /Step 1 of 5/);
    assert.equal(stage.querySelectorAll("article.account-card").length, accounts.length, `${area} lists every account brief`);
    accounts.forEach((a) => assert.ok(text(stage).includes(a.fictional_brand) && text(stage).includes(a.real_company), a.id));
    next.click();
    assert.ok(noWithheldPlayers(stage), `${area}: withheld attempts remain evidence, not previews`);
    const example = stage.querySelector("video");
    example.play();
    assert.equal(next.disabled, false);
    next.click();
    assert.ok(example.paused, `${area}: leaving drafts pauses media`);
    assert.ok(next.disabled, `${area}: hero waits for an explicit choice`);
    const choices = stage.querySelectorAll("button.select");
    assert.equal(choices.length, 1, `${area}: only the PIM hero is selectable`);
    assert.match(text(stage), /Preview only — no approved PIM hero recorded/);
    const preview = stage.querySelector("video");
    preview.play();
    assert.ok(next.disabled, `${area}: playing never selects`);
    choices[0].click();
    next.click();
    assert.equal(stage.querySelector("video").dataset.clip, heroId);
    play.click();
    const active = stage.querySelector("video");
    next.click();
    assert.ok(active.paused);
    assert.match(text(stage), /sign-off|Publication blocked|human review/);
    $("#guide-restart").click();
    next.click(); next.click();
    assert.ok(next.disabled, `${area}: restart clears selection`);
    stage.querySelector("video").play();
  }
  const areaPlaying = stage.querySelector("video");
  navigate("#guide");
  assert.ok(areaPlaying.paused, "switching areas pauses incompatible players");
  assert.match(text($("#guide-area-label")), /QSR/);
  assert.match(status(), /Step 1 of 5/, "#guide still opens the coffee flow");
  next.click();
  $("#scenario-tabs").children[0].click();

  // ---------- scenario tabs ----------
  const tabs = $("#scenario-tabs");
  const panel = $("#scenario-panel");
  const tabButtons = tabs.children;
  const selectedTab = () => tabButtons.findIndex((b) => b.getAttribute("aria-selected") === "true");
  assert.equal(tabButtons.length, 4);
  assert.ok(tabButtons.every((b) => b.getAttribute("role") === "tab" && b.getAttribute("aria-controls") === "scenario-panel"));
  assert.equal(selectedTab(), 0);
  assert.equal(panel.getAttribute("aria-labelledby"), tabButtons[0].getAttribute("id"));
  assert.deepEqual(tabButtons.map((b) => b.getAttribute("tabindex")), ["0", "-1", "-1", "-1"], "roving tabindex");
  const playing = panel.querySelector("video");
  playing.play();
  tabs.dispatch("keydown", { key: "ArrowRight" });
  assert.equal(selectedTab(), 1);
  assert.equal(document.activeElement, tabButtons[1], "arrow keys move focus");
  assert.equal(panel.getAttribute("aria-labelledby"), tabButtons[1].getAttribute("id"));
  assert.ok(playing.paused, "tab change pauses the replaced player");
  tabs.dispatch("keydown", { key: "End" });
  assert.equal(selectedTab(), 3);
  tabs.dispatch("keydown", { key: "ArrowRight" });
  assert.equal(selectedTab(), 0, "arrows wrap");
  tabs.dispatch("keydown", { key: "ArrowLeft" });
  assert.equal(selectedTab(), 3);
  tabs.dispatch("keydown", { key: "Home" });
  assert.equal(selectedTab(), 0);
  assert.match(text(panel), /Coffee|seasonal/i);
  tabButtons[2].click();
  assert.equal(panel.querySelectorAll("article.scenario-card").length, input.data.scenarios[2].clips.length);
  assert.equal(panel.querySelectorAll("article.account-card").length, 4, "home gallery lists all four representative accounts");
  const single = input.data.scenarios.findIndex((s) => s.clips.length === 1);
  if (single >= 0) {
    tabButtons[single].click();
    assert.equal(panel.querySelectorAll("div").filter((d) => d.classList.contains("scenario"))[0].classList.contains("single"), true,
      "single-clip scenarios use the full-width layout");
  }
  tabButtons.forEach((b) => {
    b.click();
    assert.ok(noWithheldPlayers(panel), "withheld attempts are never playable gallery cards");
  });

  // ---------- cost estimate ----------
  const mSel = $("#calc-model"), tSel = $("#calc-tier"), choice = $("#calc-sec-choice");
  const secIn = $("#calc-sec"), nIn = $("#calc-n"), out = () => text($("#calc-out")), err = () => text($("#calc-error"));
  const form = $("#calc");
  nIn.value = "1";
  const fire = (el, name) => { el.dispatch(name); form.dispatch(name); };
  const options = () => choice.children.map((o) => o.value);
  const setModel = (key) => { mSel.value = key; fire(mSel, "change"); };
  const setTier = (key) => { tSel.value = key; fire(tSel, "change"); };

  setModel("ltx-2.5-pro");
  assert.deepEqual(options(), ["6", "8", "10"], "LTX Pro offers 6/8/10 only");
  setModel("kling-v3-pro");
  assert.deepEqual(options(), ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]);
  setModel("ltx-2.5-fast");
  setTier("720p");
  assert.deepEqual(options(), ["6", "8", "10", "12", "14", "16", "18", "20"]);
  choice.value = "20"; fire(choice, "change");
  assert.match(out(), /\$1\.80 estimated for 1 × 20 s/);
  setTier("2160p");
  assert.deepEqual(options(), ["6", "8", "10"], "tier change re-derives durations");
  assert.ok(options().includes(choice.value), "tier change replaces an unsupported duration");
  assert.doesNotMatch(out(), /× 20 s/, "tier change invalidates the old estimate");

  setModel("minimax-h3-max-turbo");
  assert.equal($("#calc-sec-wrap").hidden, false);
  secIn.value = ""; fire(secIn, "input");
  assert.equal(out(), "No estimate", "missing duration gives no estimate");
  assert.match(err(), /duration/);
  assert.equal(secIn.getAttribute("aria-invalid"), "true");
  secIn.value = "16"; fire(secIn, "input");
  assert.equal(out(), "No estimate", "out-of-range duration is rejected");
  secIn.value = "2.5"; fire(secIn, "input");
  assert.equal(err(), "", "fractional MiniMax duration is valid");
  nIn.value = "1.5"; fire(nIn, "input");
  assert.equal(out(), "No estimate", "fractional clip count is rejected");
  assert.match(err(), /whole number of clips/);
  nIn.value = "0"; fire(nIn, "input");
  assert.equal(out(), "No estimate", "zero clips is rejected");
  nIn.value = "4"; fire(nIn, "input");
  const turbo = input.data.models.find((m) => m.key === "minimax-h3-max-turbo");
  const price = turbo.price_per_second_usd[tSel.value];
  assert.ok(out().includes(`for 4 × 2.5 s`) && out().includes((price * 2.5 * 4).toFixed(price * 10 < 1 ? 4 : 2)), out());
  assert.equal(err(), "");
  const otherTier = Object.keys(turbo.price_per_second_usd).find((t) => t !== tSel.value);
  setTier(otherTier);
  assert.equal(secIn.value, "2.5", "a tier change keeps a valid custom MiniMax duration");
  assert.ok(out().includes("for 4 × 2.5 s"), out());
  secIn.value = "1.5"; fire(secIn, "input");
  setModel("minimax-h3-max");
  assert.equal(secIn.value, "1.5", "switching between MiniMax models keeps a valid duration");
  setModel("minimax-h3-max-turbo");
  nIn.value = "250000"; fire(nIn, "input");
  assert.equal(err(), "", "no arbitrary clip-count ceiling");
  nIn.value = "9007199254740993"; fire(nIn, "input");
  assert.equal(out(), "No estimate", "unsafe integers are rejected");

  setImmediate(async () => {
    // Rejected promises must surface an actionable message, not vanish.
    failures.play = true;
    play.click();
    await new Promise(setImmediate);
    assert.equal($("#guide-alert").hidden, false);
    assert.match(text($("#guide-alert")), /Playback didn't start \(NotAllowedError\)\. Press play on the video itself/);
    $("#watch-overview").click();
    await new Promise(setImmediate);
    assert.match(text($("#overview-status")), /Playback didn't start/, "overview reports blocked playback in its dialog");
    failures.play = false;
    failures.fullscreen = true;
    $("#guide-full").click();
    await new Promise(setImmediate);
    assert.match(text($("#guide-alert")), /Fullscreen isn't available here \(TypeError\)\. Use your browser's own full-screen view/);
    failures.fullscreen = false;
    $("#guide-full").click();
    assert.equal($("#guide-alert").hidden, true, "a later success clears the message");
    console.log("guided demo, tabs and calculator passed");
  });
});
