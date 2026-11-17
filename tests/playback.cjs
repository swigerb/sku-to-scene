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
// Learning cases first in the data proves default entries choose by curation, not by array position.
if (mode === "learning-first") input.data.accounts.sort((a, b) => (b.curation === "learning") - (a.curation === "learning"));
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
    const first = this.querySelectorAll("option")[0];
    return first ? first.value : "";
  }
  set value(v) { this._value = String(v); }
  append(...kids) { this.children.push(...kids.map(node)); }
  prepend(...kids) { this.children.unshift(...kids.map(node)); }
  replaceChildren(...kids) {
    this.children = kids.map(node); this._text = null;
    if (this.children.some((c) => c.tag === "option" || c.tag === "optgroup")) this._value = undefined;
  }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  querySelectorAll(selector) {
    const [tag, cls] = selector.split(".");
    const matches = (el) => (!tag || el.tag === tag) && (!cls || el.className.split(" ").includes(cls));
    return this.children.flatMap((el) => [...(matches(el) ? [el] : []), ...el.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  closest(selector) {
    return selector === 'a[href^="#"]' && this.tag === "a" && this.attrs.href?.startsWith("#") ? this : null;
  }
  contains(el) { return el === this || this.children.some((c) => c.contains(el)); }
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
  scrollTo(options) { this.scrollTop = options.top; }
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
const frames = [];
const flushFrames = () => { while (frames.length) frames.shift()(); };
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
for (const selector of DETAILS) document.querySelector(selector);
const json = (body) => ({ ok: true, status: 200, json: async () => body });
const context = vm.createContext({
  document,
  Node: Element,
  HTMLVideoElement: { [Symbol.hasInstance]: (x) => x instanceof Element && x.tag === "video" },
  window: {
    location: { hash: "", search },
    history: { pushState: (_state, _unused, href) => { context.window.location.hash = href; } },
    matchMedia: () => ({ matches: ["theme-url-light", "theme-stored-light", "theme-system-dark", "theme-storage-blocked"].includes(mode) }),
    addEventListener: (name, fn) => { (windowListeners[name] ??= []).push(fn); },
    scrollTo: () => {},
  },
  requestAnimationFrame: (fn) => frames.push(fn),
  URLSearchParams,
  localStorage: {
    getItem: (key) => { if (mode === "theme-storage-blocked") throw new Error("blocked"); return storage.get(key); },
    setItem: (key, value) => { if (mode === "theme-storage-blocked") throw new Error("blocked"); storage.set(key, value); },
  },
  fetch: async (url, options) => {
    requests.push({ url, options });
    if (url === "data.json") return json(input.data);
    if (url.endsWith("foundry-evals-v1.json")) return mode === "ev-404" ? { ok: false, status: 404 } : json(input.ev);
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
    flushFrames();
  };
  const activateLink = (href) => {
    const a = document.createElement("a");
    a.setAttribute("href", href);
    a.click();
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
  // Native replaceChildren stringifies an unspread array; the double does the same, so this catches "[object …]".
  for (const sel of ["#readiness-summary", "#qa-summary", "#evals-body", "#scenario-panel"]) {
    assert.doesNotMatch(text($(sel)), /\[object /, `${sel} renders nodes, not stringified objects`);
  }
  if (mode === "learning-first") {
    const featured = input.data.accounts.filter((a) => a.curation === "featured");
    assert.equal($("#guide-stage").getAttribute("data-account"), featured[0].id, "the initial guide example is featured");
    for (const area of new Set(input.data.accounts.map((a) => a.area))) {
      for (const route of [`#guide/${area}`, `#guide/${area}/not-an-example`]) {
        navigate(route);
        assert.equal($("#guide-stage").getAttribute("data-account"), featured.find((a) => a.area === area).id,
          `${route} defaults to a featured presentation`);
      }
    }
    navigate("#guide/nowhere");
    assert.equal($("#guide-stage").getAttribute("data-account"), featured[0].id, "an unknown area falls back to a featured presentation");
    console.log("learning-first default entries handled");
    return;
  }
  if (mode.startsWith("hr-")) {
    assert.equal($("#review-alert").hidden, false, "unavailable alert is shown");
    assert.match(text($("#review-alert")), /Human-review evidence unavailable/);
    assert.match(text($("#readiness-summary")), /Human-review evidence unavailable/);
    assert.doesNotMatch(text($("#readiness-summary")), /open publication blockers/, "unavailable must not render a blocker count");
    assert.doesNotMatch(text(heroRoot()), /Publication blocked|Human sign-off required\./, "unavailable must not show a reviewed state");
    assert.match(text(heroRoot()), /Human-review evidence unavailable/);
    $("#guide-next").click();
    assert.match(text($("#guide-readiness")), /Human-review evidence unavailable/,
      "the active recording must fail closed outside evidence");
    console.log(`human-review ${mode} handled`);
    return;
  }
  assert.equal(text($("#review-alert")), "", "no unavailable alert when the review record loads");
  assert.match(text(heroRoot()), /^[^]*Silent fictional-demo presentation\. Original model audio was removed; this is not customer-campaign approval\./,
    "Home states the silent presentation once, concisely");
  assert.doesNotMatch(text(heroRoot()), /Silent presentation variant/, "Home does not repeat the variant label");
  const sourceHistory = heroRoot().querySelector("details.source-history");
  assert.ok(sourceHistory && !sourceHistory.open, "transformation and caveats sit in a closed disclosure");
  assert.match(text(sourceHistory), /^Source history and limitations[^]*Transformation\.[^]*Historical finding on the native original\.[^]*not to this silent presentation[^]*Retained visual caveat\./,
    "Source history keeps the transformation, the historical native finding and visual caveats");
  assert.doesNotMatch(text(heroRoot()), /Publication blocked\./, "native audio blocker does not attach unchanged to the silent derivative");
  const nFeatured = input.data.accounts.filter((a) => a.curation === "featured").length;
  const nLearning = input.data.accounts.filter((a) => a.curation === "learning").length;
  assert.deepEqual([nFeatured, nLearning], [8, 6], "curated scope is eight featured and six learning cases");
  assert.match(text($("#readiness-summary")), new RegExp(`^${nFeatured}featured fictional-demo presentations; no customer-campaign approval` +
    `${nLearning}learning cases with known limitations; future remediation required6rejected replacement attempts; none selected` +
    "Different populations, not a total\\."), "evidence summary separates the three populations");
  for (const a of input.data.accounts.filter((x) => x.curation === "learning")) {
    assert.ok(text($("#readiness-summary")).includes(a.learning_defect), `${a.id} learning defect is listed for future remediation`);
  }
  const blockerNotes = $("#readiness-summary").querySelectorAll("div.readiness.blocked");
  assert.equal(blockerNotes.length, 1, "each open blocker renders as its own note");
  assert.match(text(blockerNotes[0]), /Publication blocker · /);
  const nAccounts = input.data.accounts.length, nClips = input.data.clips.length;
  const nGenerations = input.data.clips.filter((c) => c.record_kind !== "presentation").length;
  assert.match(text($("#readiness-summary")), new RegExp(`${nAccounts} of ${nAccounts} fictional accounts keep a playable recording\\. ` +
    "Playable is not repaired"), "account coverage count is not presented as repair");
  assert.match(text($("#readiness-summary")), new RegExp(`${nGenerations}recorded attempts retained as evidence, not a current approval backlog`));
  // One shared note names both denominators, so the cards stay concise and 36 never reads as 36 selected examples.
  for (const sel of ["#readiness-summary", "#qa-summary-note"]) {
    assert.equal($(sel).querySelectorAll("p.summary-note").length, 1, `${sel} has one shared denominator note`);
    assert.match(text($(sel)), new RegExp(`${nAccounts} is account coverage: one retained recording per fictional account ` +
      `\\(${nFeatured} featured presentations, ${nLearning} learning cases\\)\\. ` +
      `${nGenerations} counts every recorded clip and attempt on file[^]*not the number of selected examples`), `${sel} names both denominators`);
    assert.match(text($(sel)), /2 presentation derivatives are not additional generations/);
  }
  assert.equal($("#readiness-summary").querySelectorAll("span.stat-note").length, 0, "denominator prose is not repeated inside cards");
  assert.equal($("#qa-recordings").querySelectorAll("article.qa-recording").length, 1, "QA defaults to one selected recording");
  assert.equal($("#qa-recordings").querySelector("article.qa-recording").dataset.clip, input.data.lto.hero_clip);
  assert.match(text($("#qa-summary")), /maximum|max Content Safety severity across sampled frames of the source recording/,
    "single-recording safety scope is explicit");
  const setScope = (id) => { $("#evidence-scope").value = id; $("#evidence-scope").dispatch("change"); };
  const pending = $("#readiness-summary").querySelector("details.pending-decisions");
  assert.equal(pending.querySelectorAll("a").length, 2, "pending decisions link to both affected examples");
  assert.match(text(blockerNotes[0]), /Northwind/, "global blocker names its example");
  pending.querySelectorAll("a")[0].click();
  assert.equal($("#evidence-scope").value, "hero-home-kling", "decision link selects affected evidence");
  assert.ok($("#qa").open, "decision link expands screening");
  assert.match(text($("#qa-recordings").querySelector("section.original-screening")), /Prompt adherence: 0.72 \/ 0.75 threshold/,
    "original screening shows the actual failed check and threshold");
  assert.doesNotMatch(text($("#qa-recordings").querySelector("section.original-screening")), /black\/teal/);
  assert.match(text($("#qa-recordings").querySelector("section.additional-finding")), /black\/teal/,
    "reference conflict is separate additional evidence");
  setScope("all");
  assert.equal($("#qa-recordings").querySelectorAll("article.qa-recording").length, nClips, "all-attempts scope retains every recorded verdict");
  assert.match(text($("#qa-summary")), new RegExp(`/ ${nGenerations}distinct source recordings`),
    "source QA is counted once, not again for each presentation derivative");
  assert.match(text($("#qa-summary")), /No campaign approval/);
  assert.match(text($("#qa-summary")), /including historical and withheld attempts/, "aggregate safety scope is explicit");
  if (mode === "ok") {
    const ev = input.ev, evText = text($("#evals-body"));
    const clipCards = $("#evals-body").querySelectorAll("details.clip-card");
    assert.deepEqual(clipCards.map((c) => c.attrs["data-clip"]), Object.keys(ev.media), "one readable findings card per evaluated clip");
    for (const [id, m] of Object.entries(ev.media)) {
      const card = clipCards.find((c) => c.attrs["data-clip"] === id);
      const toggle = card.querySelectorAll("span.clip-toggle");
      assert.equal(toggle.length, 1, `${id} summary draws a visible expand/collapse affordance`);
      assert.equal(toggle[0].attrs["aria-hidden"], "true", `${id} toggle is decorative; <details> carries the state`);
      const applicable = Object.entries(m.checks).filter(([, c]) => c.applicable).map(([k]) => k);
      assert.deepEqual(card.querySelectorAll("article.check-card").map((c) => c.attrs["data-check"]).sort(), applicable.sort(), `${id} check cards`);
      for (const [key, chk] of Object.entries(m.checks)) {
        if (!chk.applicable) { assert.ok(text(card).includes(chk.na_reason), `${id} ${key} shows its N/A reason`); continue; }
        for (const r of chk.repeats || chk.cloud || []) {
          assert.ok(text(card).includes(r.run_id), `${id} ${key} keeps run ${r.run_id} discoverable`);
          for (const reason of r.reasons || []) assert.ok(text(card).includes(reason), `${id} ${key} keeps every reason verbatim`);
        }
        if ((chk.repeats || []).some((r) => r.service_label !== chk.label)) {
          assert.match(text(card), /Service label: /, `${id} ${key} keeps the grader vs service distinction`);
        }
        const svc = [...new Set((chk.repeats || chk.cloud || []).map((r) => r.service_label))];
        const checkText = text(card.querySelectorAll("article.check-card").find((c) => c.attrs["data-check"] === key));
        if (svc.length && svc.join() !== chk.label) {
          assert.ok(checkText.includes(`Service label: ${svc.join(" / ")}. `), `${id} ${key} shows both labels`);
          assert.equal(/non-passing grader label as fail/.test(checkText), svc.includes("fail"),
            `${id} ${key}: the recorded-as-fail explanation appears only for a non-passing service result (${svc.join("/")} vs ${chk.label})`);
        }
        if (chk.needs_human_review) assert.match(text(card), /Needs human review/);
      }
    }
    for (const r of Object.values(ev.runs).flatMap((x) => x.runs)) assert.ok(evText.includes(r.run_id), `run table keeps ${r.run_id}`);
    assert.match(evText, /How to read these results/);
    for (const r of input.data.targeted_evaluations.checks) {
      assert.ok(evText.includes(r.request_id), "bounded direct evaluation retains its request ID");
      for (const reason of r.result.reasons) assert.ok(evText.includes(reason), "new evaluation reasons are unchanged");
    }
    assert.doesNotMatch(evText, /Genuine product failure: the bundle omits/, "Woodgrove's disputed omission is not repeated as fact");
    setScope("zava-silent-presentation-v1");
    assert.match(text($("#evals-body")), /partial/);
    assert.match(text($("#evals-body")), /not Foundry Evals service runs/);
    assert.match(text($("#evals-body")), /not applicable to this unbranded concept/);
    setScope("release-wide-world-20261117-v1");
    assert.match(text($("#qa-recordings")), /Rejected despite automated pass/);
    assert.match(text($("#qa-recordings")), /background shipping-label/);
    assert.doesNotMatch(text($("#qa-recordings")), /Current fictional-demo disposition/);
    setScope("account-proseware-draft-s7");
    assert.equal($("#evals-body").querySelectorAll("details.clip-card").length, 0, "unevaluated clip never borrows another recording's result");
    assert.match(text($("#evals-body")), /Not yet evaluated/);
    assert.ok(text($("#selected-route")).includes(input.data.clips.find((c) => c.id === "account-proseware-draft-s7").model_name),
      "route explanation follows the actual selected recording, not an earlier plan");
    setScope(input.data.lto.hero_clip);
    assert.deepEqual($("#evals-body").querySelectorAll("details.clip-card").map((c) => c.dataset.clip), [],
      "silent derivative does not inherit native audio evaluation as its own");
    assert.match(text($("#evals-body")), /Not yet evaluated/);
  }
  if (mode === "ev-404") {
    navigate("#guide");
    $("#guide-next").click();
    $("#guide-stage").querySelectorAll("button.concept-thumb")[1].click();
    $("#guide-stage").querySelector("button.select").click();
    $("#guide-next").click();
    assert.match(text($("#guide-readiness")), /Not approved for customer-campaign publication/);
    assert.match(text($("#readiness-summary")), /Publication blocker/, "missing evals cannot erase historical source blockers");
    assert.match(text($("#guide-stage")), /Evaluation evidence unavailable/);
    console.log("evaluation evidence unavailable handled");
    return;
  }

  // ---------- guided demo ----------
  const lto = input.data.lto;
  const stage = $("#guide-stage");
  const status = () => text($("#guide-status"));
  const prev = $("#guide-prev"), next = $("#guide-next"), play = $("#guide-play");
  const vid = () => stage.querySelector("video");
  const thumbs = () => stage.querySelectorAll("button.concept-thumb");
  const selectButtons = () => stage.querySelectorAll("button.select");
  const withheld = new Set(input.data.clips.filter((c) => c.withheld_reason).map((c) => c.id));
  const noWithheldPlayers = (root) => root.querySelectorAll("video").every((v) => !withheld.has(v.dataset.clip));

  assert.match(status(), /Step 1 of 4: Brief/);
  assert.equal(stage.getAttribute("data-account"), "northwind");
  assert.equal(stage.querySelectorAll("blockquote").length, 1, "full prompt appears once, in details");
  assert.ok(prev.disabled && play.disabled, "brief step has no previous step or video");
  next.click();
  assert.match(status(), /Step 2 of 4/);
  assert.equal(thumbs().length, 3);
  assert.equal(stage.querySelectorAll("video").length, 1, "only one active player, not three comparison videos");
  assert.equal(vid().getAttribute("poster"), `posters/${vid().dataset.clip}.jpg`, "paused preview uses a recorded-frame poster");
  assert.ok(noWithheldPlayers(stage), "withheld account attempts are not guided preview players");
  assert.match(text($("#guide-readiness")), /human review|decision|sign-off/,
    "publication readiness outside Inspect evidence");
  assert.equal(selectButtons().length, 0, "concept 1 is not eligible");
  assert.ok(next.disabled, "result waits for explicit selection");
  assert.equal(play.textContent, "Play");
  play.click();
  const first = vid();
  assert.ok(!first.paused, "Play drives the default preview");
  thumbs()[1].click();
  assert.ok(first.paused, "changing active concept pauses the previous player");
  assert.equal(vid().dataset.clip, "lto-draft-2");
  assert.equal(play.getAttribute("aria-label"), "Play concept #2 preview");
  assert.ok($("#sound").disabled, "the silent second concept disables Sound");
  assert.match(text($("#sound-label")), /unavailable/);
  assert.match(text($("#guide-next-hint")), /Select concept #2 to continue/, "disabled Next explains the selection gate");
  assert.ok(next.disabled, "previewing never selects");
  assert.equal(selectButtons().length, 1, "only the recorded hero concept is selectable");
  play.click();
  assert.equal(selectButtons()[0].getAttribute("aria-pressed"), "false", "previewing never selects");
  assert.ok(next.disabled, "previewing never selects");
  selectButtons()[0].click();
  assert.equal(selectButtons()[0].getAttribute("aria-pressed"), "true");
  assert.match(status(), new RegExp(`Concept #${lto.hero_variant} selected`));
  assert.ok(!next.disabled, "selection unlocks the hero step");
  const playingDraft = vid();
  next.click();
  assert.ok(playingDraft.paused, "step changes pause the old recording");
  assert.match(status(), /Step 3 of 4: Recorded result/);
  const hero = stage.querySelector("video");
  assert.equal(hero.dataset.clip, lto.hero_clip);
  assert.equal(play.getAttribute("aria-label"), "Play Northwind Coffee recorded result",
    "recorded-result accessible name uses the current step, not retained concept metadata");
  assert.equal($("#sound").disabled, true, "selected silent hero cannot enable Sound");
  play.click();
  assert.ok(!hero.paused, "Play drives the hero");
  assert.equal(play.getAttribute("aria-label"), "Pause Northwind Coffee recorded result");
  assert.match(text(stage), /Requested native audio was removed/, "presentation edit stays explicit");
  const heroInspect = stage.querySelector("details");
  assert.ok(heroInspect && !/LUFS/.test(text(heroInspect)), "native source loudness is not a silent-variant measurement");
  assert.doesNotMatch(text(stage).replace(text(heroInspect), ""), /LUFS|dBTP/, "no signal metrics outside evidence");
  const beforeScroll = scrolled.length;
  next.click();
  assert.ok(hero.paused, "moving on pauses the replaced hero");
  assert.match(status(), /Step 4 of 4/);
  assert.equal(play.getAttribute("aria-label"), "Play Northwind Coffee recorded result",
    "Review retains the recorded-result playback context");
  assert.match(text(stage), /Historical source screening[^]*Current fictional-demo disposition[^]*Customer-campaign approvalNot approved\.[^]*What needs checking next/,
    "Review separates source screening, current demo disposition and campaign approval");
  assert.doesNotMatch(text(stage), /Current fictional-demo dispositionCurrent fictional-demo disposition/, "disposition heading is not repeated as its body");
  assert.match(text(stage.querySelector("section.review-guidance")), /Use the silent variant for this demo/);
  assert.ok(text(stage.querySelector("section.review-guidance")).length < 230, "review guidance is concise, not finding history");
  assert.match(text(stage), /original audio mismatch remains attached to the native source/);
  assert.doesNotMatch(text($("#guide-readiness")), /Publication blocked\./);
  assert.ok(scrolled.length > beforeScroll, "explicit step change resets scroll");
  assert.equal(document.activeElement, $("#guide-heading"), "step change focuses the start");
  assert.match(next.getAttribute("aria-label"), /Explore examples/, "review offers a truthful exit, not another imaginary step");
  const reviewHero = stage.querySelector("video");
  reviewHero.play();
  $("#guide-restart").click();
  assert.ok(reviewHero.paused, "restart pauses the hero");
  assert.match(status(), /Step 1 of 4/);
  next.click();
  assert.ok(next.disabled, "restart clears the selection");

  const wrap = $("#guide-wrap");
  wrap.dispatch("keydown", { key: "ArrowLeft" });
  assert.match(status(), /Step 1 of 4/, "ArrowLeft goes back");
  wrap.dispatch("keydown", { key: "ArrowRight", target: new Element("video") });
  assert.match(status(), /Step 1 of 4/, "arrow keys on a video are left to the player");
  const ev = wrap.dispatch("keydown", { key: "ArrowRight" });
  assert.match(status(), /Step 2 of 4/);
  assert.ok(ev.defaultPrevented);
  wrap.dispatch("keydown", { key: "End", target: thumbs()[0] });
  assert.equal(vid().dataset.clip, "lto-draft-3", "thumbnail keyboard navigation previews, never selects");
  assert.ok(next.disabled);
  assert.equal(document.activeElement, thumbs()[2]);
  wrap.dispatch("keydown", { key: "Home", target: thumbs()[2] });
  assert.equal(vid().dataset.clip, "lto-draft-1");
  assert.equal($("#guide-full").hidden, false);
  $("#guide-full").click();
  assert.equal(fullscreenRequests[0], wrap, "fullscreen targets the guide");
  assert.equal($("#guide-alert").hidden, true);

  // ---------- Options popover ----------
  const opts = $("#guide-options"), optsToggle = $("#guide-options-toggle");
  const insideOpts = document.createElement("button");
  opts.append(insideOpts);
  opts.open = true;
  opts.dispatch("keydown", { key: "Escape" });
  assert.equal(opts.open, false, "Escape closes Options");
  assert.equal(document.activeElement, optsToggle, "and returns focus to its toggle");
  opts.open = true;
  insideOpts.click();
  assert.equal(opts.open, true, "a click inside the panel keeps it open");
  stage.click();
  assert.equal(opts.open, false, "an outside click dismisses Options");

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
  assert.deepEqual(shown(), ["scenarios"], "a home category opens the visual gallery");
  assert.equal(document.activeElement, $("#scenarios-heading"), "with focus on the gallery heading");
  for (const a of input.data.accounts.filter((a) => a.id !== "northwind")) {
    navigate(`#guide/${a.area}/${a.id}`);
    assert.deepEqual(shown(), ["guide"]);
    assert.match(status(), /Step 1 of 3/);
    assert.equal(stage.getAttribute("data-account"), a.id, "only the chosen fictional example appears");
    assert.equal(stage.querySelectorAll("video").length, 0);
    assert.equal(stage.querySelectorAll("h3").length, 1, "Brief has one product title, not a duplicate in its text-led placeholder");
    const need = text(stage.querySelector("p.business-need"));
    assert.ok(need && need !== text(stage.querySelector("p.creative-summary")), `${a.id} separates business need from creative summary`);
    const notices = stage.querySelectorAll("p.learning-notice");
    const occurrences = (s, part) => s.split(part).length - 1;
    if (a.curation === "learning") {
      assert.equal(notices.length, 1, `${a.id} deep link states its learning-case role`);
      assert.match(text(notices[0]), /^Learning case — not a featured presentation\. /);
      assert.equal(occurrences(`${text($("#guide-readiness"))} ${text(stage)}`, a.learning_defect), 1,
        `${a.id} deep link names its unresolved defect once`);
    } else {
      assert.equal(notices.length, 0, `${a.id} featured presentation carries no learning notice`);
    }
    next.click();
    assert.match(status(), /Step 2 of 3: Recorded result/, "no fabricated Concepts or selection for a single recording");
    assert.equal(vid().dataset.clip, a.recorded_clip);
    assert.equal(vid().getAttribute("poster"), `posters/${a.recorded_clip}.jpg`, "recorded result has its own still poster");
    assert.equal(stage.querySelectorAll("video").length, 1, "historical attempts don't add players");
    assert.ok(noWithheldPlayers(stage));
    assert.equal(selectButtons().length, 0);
    if (!a.hero_clip) assert.match(text(stage), /Recorded preview — no PIM hero/);
    play.click();
    const active = stage.querySelector("video");
    next.click();
    assert.ok(active.paused);
    assert.match(status(), /Step 3 of 3: Review/, "preview-only recordings can reach review");
    if (a.curation === "learning") {
      assert.equal(occurrences(text(stage.querySelector("div.review-summary")), a.learning_defect), 1,
        `${a.id} Review names its unresolved defect once`);
    }
    navigate("#scenarios");
    navigate(`#guide/${a.area}/${a.id}`);
    assert.match(status(), /Step 3 of 3: Review/, "history navigation does not restart the same example");
    navigate("#scenarios");
    activateLink(`#guide/${a.area}/${a.id}`);
    assert.match(status(), /Step 1 of 3: Brief/, "explicit guide entry restarts the same example");
    next.click(); next.click();
  }
  const areaPlaying = vid();
  areaPlaying.play();
  navigate("#guide");
  assert.ok(areaPlaying.paused, "switching areas pauses incompatible players");
  assert.equal(stage.getAttribute("data-account"), "northwind");
  assert.match(status(), /Step 1 of 4/, "#guide still opens the coffee flow");
  next.click();
  assert.ok(next.disabled, "unrelated account changes clear the selection");
  thumbs()[1].click(); selectButtons()[0].click();
  $("#guide-example").value = "proseware"; $("#guide-example").dispatch("change");
  assert.match(status(), /Step 1 of 3/);
  $("#guide-example").value = "northwind"; $("#guide-example").dispatch("change");
  next.click();
  assert.ok(next.disabled, "change-example selector also clears the selection");
  thumbs()[1].click(); selectButtons()[0].click();
  navigate("#scenarios");
  activateLink("#guide/qsr/northwind");
  assert.match(status(), /Step 1 of 4: Brief/, "explicit entry restarts Northwind too");
  next.click(); thumbs()[1].click();
  assert.ok(next.disabled, "explicit guide entry clears an old concept selection");
  assert.equal(selectButtons()[0].getAttribute("aria-pressed"), "false");
  // Every default entry chooses a featured presentation; learning cases are reachable only by explicit choice.
  const firstFeatured = (area) => input.data.accounts.find((a) => a.area === area && a.curation === "featured");
  for (const area of new Set(input.data.accounts.map((a) => a.area))) {
    for (const route of [`#guide/${area}`, `#guide/${area}/not-an-example`]) {
      navigate(route);
      assert.equal(stage.getAttribute("data-account"), firstFeatured(area).id, `${route} defaults to a featured presentation`);
      assert.equal(stage.querySelectorAll("p.learning-notice").length, 0, `${route} does not land on a learning case`);
    }
  }
  const groups = $("#guide-example").children;
  assert.deepEqual(groups.map((g) => [g.tag, g.getAttribute("label"), g.children.length]),
    [["optgroup", "Featured presentations", nFeatured], ["optgroup", "Learning cases", nLearning]],
    "the example selector distinguishes featured presentations from learning cases");
  assert.deepEqual(groups[1].children.map((o) => o.value), input.data.accounts.filter((a) => a.curation === "learning").map((a) => a.id));
  assert.deepEqual($("#evidence-scope").children.slice(0, 2).map((g) => [g.getAttribute("label"), g.children.length]),
    [["Featured presentations", nFeatured], ["Learning cases", nLearning]], "evidence scope separates the two populations");
  navigate("#guide/qsr/northwind");
  next.click(); thumbs()[1].click();
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
  assert.equal(panel.querySelectorAll("video").length, 0, "gallery initially mounts no players");
  assert.equal(text($("#scenario-coverage")), `${nFeatured} featured presentations across 4 categories, with ${nLearning} additional learning cases.`,
    "gallery coverage line describes the curated scope");
  tabs.dispatch("keydown", { key: "ArrowRight" });
  assert.equal(selectedTab(), 1);
  assert.equal(document.activeElement, tabButtons[1], "arrow keys move focus");
  assert.equal(panel.getAttribute("aria-labelledby"), tabButtons[1].getAttribute("id"));
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
  assert.equal(panel.querySelectorAll("article.scenario-card").length, 0, "no duplicate original scenario listing");
  const homeFeatured = input.data.accounts.filter((a) => a.area === "home" && a.curation === "featured").length;
  assert.equal(panel.children[0].querySelectorAll("article.account-card").length, homeFeatured,
    "home gallery shows featured presentations by default");
  assert.equal(panel.querySelectorAll("article.account-card").length, 4, "home gallery lists all four representative accounts");
  tabButtons.forEach((b) => {
    b.click();
    assert.ok(noWithheldPlayers(panel), "withheld attempts are never playable gallery cards");
  });
  input.data.scenarios.forEach((s, i) => {
    tabButtons[i].click();
    const accounts = input.data.accounts.filter((a) => a.area === s.guide);
    const learningIds = accounts.filter((a) => a.curation === "learning").map((a) => a.id);
    const learningBox = panel.querySelector("details.learning-cases");
    assert.deepEqual(panel.children[0].children.map((c) => c.dataset.account),
      accounts.filter((a) => a.curation === "featured").map((a) => a.id), `${s.guide} shows featured presentations by default`);
    if (learningIds.length) {
      assert.ok(learningBox && learningBox.attrs.open === undefined && !learningBox.open, `${s.guide} learning cases start collapsed`);
      assert.equal(text(learningBox.querySelector("summary")), `Learning cases and known limitations (${learningIds.length})`);
      assert.deepEqual(learningBox.querySelectorAll("article.account-card").map((c) => c.dataset.account), learningIds,
        `${s.guide} learning cases sit only in the labelled section`);
    } else {
      assert.equal(learningBox, undefined, `${s.guide} has no empty learning section`);
    }
    assert.equal(panel.querySelectorAll("a.ext").length, 0, "research is absent from the browsing surface");
    for (const [j, card] of panel.querySelectorAll("article.account-card").entries()) {
      const a = accounts[j];
      const learningCase = a.curation === "learning";
      assert.equal(card.children[0].tag, "button", "gallery card leads with Preview");
      assert.equal(card.querySelector("a").getAttribute("href"), `#guide/${a.area}/${a.id}`, "each gallery action targets the exact account");
      assert.equal(text(card.querySelector("a")), learningCase ? "Inspect learning case" : "Open guided demo", `${a.id} CTA names its role`);
      assert.equal(card.querySelectorAll("p.learning-defect").length, learningCase ? 1 : 0, `${a.id} card shows a known limitation only if learning`);
      assert.match(card.children[0].getAttribute("aria-label"), learningCase ? /^Preview .+ learning case$/ : /^Preview [^]+$/);
      assert.ok(text(card.querySelector("p.example-summary")).split(/\s+/).length <= 18, "authored use case meets the content budget");
      assert.equal(card.querySelectorAll("video").length, 0);
      assert.equal(card.querySelectorAll("blockquote").length, 0);
      const trigger = card.querySelector("button");
      trigger.click();
      const preview = $("#preview-body"), v = preview.querySelector("video");
      assert.equal(preview.querySelectorAll("video").length, 1, "only the requested recording is mounted");
      assert.equal(v.dataset.clip, a.recorded_clip, "Preview opens the selected output");
      const previewNotice = preview.querySelectorAll("p.learning-notice");
      assert.equal(previewNotice.length, learningCase ? 1 : 0, `${a.id} preview keeps its learning-case notice only if learning`);
      if (learningCase) assert.equal(text(preview).split(a.learning_defect).length - 1, 1, `${a.id} preview names the defect once`);
      assert.match(text(preview.querySelector("h3.preview-recording-name")), learningCase ? /^Learning case recording · /
        : input.data.clips.find((c) => c.id === a.recorded_clip).presentation ? /^Selected silent presentation · / : /^Selected example · /);
      assert.ok(preview.querySelectorAll("a.button").some((x) => text(x) === (learningCase ? "Inspect learning case" : "Open guided demo")),
        `${a.id} preview CTA names its role`);
      assert.deepEqual(preview.querySelectorAll("a.ext").filter((x) => x.getAttribute("href").startsWith("http")).map((x) => x.getAttribute("href")).sort(),
        a.sources.map((x) => x.url).sort(), `${a.id} citations keep exact URLs in details`);
      for (const cite of preview.querySelectorAll("a.ext")) {
        assert.equal(cite.getAttribute("target"), "_blank");
        assert.equal(cite.getAttribute("rel"), "noopener noreferrer");
        assert.match(text(cite), /\(opens in new tab\)$/);
      }
      assert.ok(noWithheldPlayers(preview));
      const alternative = preview.querySelectorAll("button").find((b) => text(b) === "Preview this recording");
      if (alternative) {
        $("#scenario-preview").scrollTop = 500;
        alternative.click();
        const replacement = preview.querySelector("video");
        assert.ok(v.paused && !replacement.paused, "alternative Preview pauses old recording and plays new recording");
        assert.equal($("#scenario-preview").scrollTop, 0, "alternative Preview resets dialog scroll");
        assert.match(text(preview.querySelector("h3.preview-recording-name")), /Alternative concept|Earlier attempt|Native original/);
        assert.ok(noWithheldPlayers(preview));
      }
      $("#preview-close").click();
      assert.ok(v.paused, "closing preview pauses its recording");
      assert.equal(preview.querySelectorAll("video").length, 0, "closing preview unmounts its player");
      assert.equal(document.activeElement, trigger, "closing preview restores focus to the originating card");
    }
  });

  // ---------- cost estimate ----------
  const mSel = $("#calc-model"), tSel = $("#calc-tier"), choice = $("#calc-sec-choice");
  const secIn = $("#calc-sec"), nIn = $("#calc-n"), out = () => text($("#calc-out")), err = () => text($("#calc-error"));
  const form = $("#calc");
  setScope("hero-home-kling");
  const recordedRoute = text($("#selected-route"));
  nIn.value = "12"; form.dispatch("input");
  assert.equal(text($("#selected-route")), recordedRoute, "what-if changes cannot revise retained evidence");
  $("#calc-reset").click();
  assert.equal(nIn.value, "1", "reset restores a single recorded clip");
  assert.equal(mSel.value, input.data.clips.find((c) => c.id === "hero-home-kling").model);
  setScope("all");
  assert.ok($("#calc-reset").disabled, "aggregate scope has no recording to reset to");
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
    $("#scenario-tabs").querySelectorAll("button")[0].click();
    $("#scenario-panel").querySelector("button.poster-preview").click();
    $("#preview-body").querySelectorAll("button").find((b) => text(b) === "Preview this recording").click();
    await new Promise(setImmediate);
    assert.match(text($("#preview-status")), /Playback didn't start/, "alternative preview reports rejected playback visibly");
    $("#preview-close").click();
    failures.play = false;
    failures.fullscreen = true;
    $("#guide-full").click();
    await new Promise(setImmediate);
    assert.match(text($("#guide-alert")), /Fullscreen isn't available here \(TypeError\)\. Use your browser's own full-screen view/);
    failures.fullscreen = false;
    $("#guide-full").click();
    assert.equal($("#guide-alert").hidden, true, "a later success clears the message");
    $("#guide-options").open = true;
    $("#guide-restart").click();
    assert.equal($("#guide-options").open, false, "Restart closes Options");
    console.log("guided demo, tabs and calculator passed");
  });
});
