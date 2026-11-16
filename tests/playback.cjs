// Dependency-free DOM/media double: execute the shipped app and exercise its event handlers.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const data = JSON.parse(fs.readFileSync(0, "utf8"));
const roots = new Map();
const documentListeners = {};
const requests = [];

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.className = "";
    this.paused = true;
    this.hidden = false;
    this.classList = {
      toggle: (name, on) => {
        const names = new Set(this.className.split(" ").filter(Boolean));
        if (on) names.add(name); else names.delete(name);
        this.className = [...names].join(" ");
      },
    };
  }
  setAttribute(key, value) {
    this.attrs[key] = value;
    if (key.startsWith("data-")) this.dataset[key.slice(5)] = value;
  }
  getAttribute(key) { return this.attrs[key]; }
  get value() { return this.attrs.value ?? this.children[0]?.value ?? ""; }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  querySelectorAll(selector) {
    const matches = (el) => {
      const [tag, cls] = selector.split(".");
      return (!tag || el.tag === tag) && (!cls || el.className.split(" ").includes(cls));
    };
    return this.children.flatMap((el) => [
      ...(matches(el) ? [el] : []), ...el.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0]; }
  dispatch(name) {
    const event = { target: this };
    for (const fn of documentListeners[name] || []) fn(event);
    for (const fn of this.listeners[name] || []) fn(event);
  }
  play() { this.paused = false; this.dispatch("play"); }
  pause() { this.paused = true; }
  click() { this.dispatch("click"); }
}

const document = {
  createElement: (tag) => new Element(tag),
  createTextNode: (text) => Object.assign(new Element("#text"), { textContent: text }),
  documentElement: new Element("html"),
  querySelector: (selector) => {
    if (!roots.has(selector)) roots.set(selector, new Element("div"));
    return roots.get(selector);
  },
  querySelectorAll: (selector) => [...roots.values()].flatMap((el) => el.querySelectorAll(selector)),
  addEventListener: (name, fn) => { (documentListeners[name] ??= []).push(fn); },
};

const timers = new Map();
let timerId = 0;
const context = vm.createContext({
  document, Node: Element, HTMLVideoElement: Element,
  fetch: async (url, options) => {
    requests.push({ url, options });
    return { ok: url === "data.json", json: async () => data };
  },
  setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; },
  clearTimeout: (id) => timers.delete(id),
});
vm.runInContext(fs.readFileSync(process.argv[2] || "site/app.js", "utf8"), context);

setImmediate(() => {
  assert.deepEqual(requests.map((r) => r.url).sort(), [
    "data.json", "evaluations/foundry-evals-v1.json", "evaluations/human-review.json",
  ]);
  assert.ok(requests.every((r) => r.options?.cache === "no-cache"), "all mutable JSON must revalidate");
  const $ = (selector) => document.querySelector(selector);
  const drafts = () => $("#drafts").querySelectorAll(".draft");
  const draftVideo = (i) => drafts()[i].querySelector("video");
  const choose = (i) => drafts()[i].querySelector("button.choose").click();
  const selected = (i) => drafts()[i].querySelector("button.choose").getAttribute("aria-pressed") === "true";

  assert.equal(drafts().length, 3, "the real app must initialize");
  let playing = draftVideo(1);
  playing.play();
  assert.ok(selected(1) && !playing.paused, "play selects and preserves the just-played draft");
  choose(2);
  assert.ok(selected(2) && playing.paused, "choosing a different concept pauses the old draft");

  choose(1);
  let hero = $("#hero-out").querySelector("video");
  hero.play();
  $("#replay-reset").click();
  assert.ok($("#hero-out").hidden && hero.paused, "reset pauses the hidden hero");

  playing = draftVideo(0);
  playing.play();
  $("#replay-reset").click();
  assert.ok(playing.paused, "reset pauses drafts before replacing them");

  choose(1);
  hero = $("#hero-out").querySelector("video");
  hero.play();
  choose(2);
  assert.ok(hero.paused, "replacing a hero pauses it before detaching");

  playing = draftVideo(1);
  playing.play();
  $("#scenario-tabs").querySelectorAll("button")[1].click();
  assert.ok(playing.paused, "scenario transitions pause other players");
  const scenario = $("#scenario-body").querySelector("video");
  scenario.play();
  $("#scenario-tabs").querySelectorAll("button")[2].click();
  assert.ok(scenario.paused, "scenario replacement pauses detached players");

  choose(1);
  hero = $("#hero-out").querySelector("video");
  hero.play();
  $("#replay-play").click();
  assert.ok(hero.paused, "replay starts by pausing the old hero");
  playing = draftVideo(0);
  playing.play();
  const other = draftVideo(2);
  other.play();
  assert.ok(playing.paused && !other.paused && selected(2), "single player and play-select stay compatible");

  $("#replay-play").click();
  playing = draftVideo(0);
  // Simulate playback state before the timed selection without cancelling the replay.
  playing.paused = false;
  [...timers.values()].find((t) => t.delay === 6600).fn();
  assert.ok(playing.paused && selected(1), "timed replay selection pauses incompatible playback");
  console.log("playback transitions passed");
});
