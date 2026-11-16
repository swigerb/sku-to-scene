/* SKU to Scene browser demo: a guided replay of recorded Foundry renders. It loads only this site's own files;
   nothing is generated or evaluated in the browser. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const CHECKS = ["logo_integrity", "label_legibility", "product_fidelity", "prompt_adherence"];
  const CHECK_LABEL = {
    logo_integrity: "Logo", label_legibility: "Label", product_fidelity: "Product", prompt_adherence: "Prompt",
  };

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, "");
      else el.setAttribute(k, String(v));
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  const usd = (n) => (n === null || n === undefined ? "n/a" : `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`);
  const secs = (n) => (n === null || n === undefined ? "n/a" : `${n.toFixed(1)} s`);
  const screening = (v) => (v === "pass" ? "passed" : v === "fail" ? "did not pass" : "not evaluated");
  const verdictPill = (v) => h("span", {
    class: `pill ${v === "pass" ? "pass" : v === "fail" ? "fail" : "warn"}`,
    title: `Recorded @brand-qa verdict: ${v || "not evaluated"}`,
  }, `Automated screening: ${screening(v)}`);
  // Rejected play/fullscreen promises get a visible, actionable message instead of failing silently.
  function showIssue(target, message) {
    const el = $(target);
    if (!el) return;
    el.textContent = message;
    el.hidden = !message;
  }
  const reason = (err) => (err && err.name ? ` (${err.name})` : "");
  function playSafely(v, statusTarget = "#guide-alert") {
    showIssue(statusTarget, "");
    let p;
    try { p = v.play(); } catch (err) { p = Promise.reject(err); }
    if (p && typeof p.catch === "function") {
      p.catch((err) => showIssue(statusTarget, `Playback didn't start${reason(err)}. Press play on the video itself, ` +
        "or allow autoplay and sound for this site in your browser settings."));
    }
  }
  const togglePlay = (v) => { if (v.paused) playSafely(v); else v.pause(); };

  // Presentation-only playback level for the Kling hero: its native track peaks at +2.0 dBTP and a reviewer found
  // the ambience too loud. This lowers loudness only; the file and its native audio are unchanged.
  const PRESENTATION_VOLUME = { "lto-hero-kling": 0.5 };
  let EV = null; // sanitized Foundry Evals results (evaluations/foundry-evals-v1.json)
  let HR = null; // human-review findings (evaluations/human-review.json)

  // A missing or malformed review record must read as "unavailable", never as "no blockers". Every finding is
  // validated, so one bad entry can't crash the page or silently hide a blocker.
  const SEVERITIES = new Set(["publication blocker", "needs human decision", "informational", "grader calibration"]);
  const nonEmpty = (v) => typeof v === "string" && v.trim() !== "";
  const optText = (v) => v === undefined || nonEmpty(v);
  function validFinding(f) {
    return !!f && typeof f === "object" && !Array.isArray(f) &&
      nonEmpty(f.id) && nonEmpty(f.source) && nonEmpty(f.status) && nonEmpty(f.observation) && SEVERITIES.has(f.severity) &&
      (nonEmpty(f.clip) !== nonEmpty(f.case)) && optText(f.clip) && optText(f.case) &&
      optText(f.measured_signal) && optText(f.handling) && optText(f.mitigation_in_demo) &&
      (f.resolution_options === undefined || (Array.isArray(f.resolution_options) && f.resolution_options.every(nonEmpty)));
  }
  const validReview = (r) => !!r && typeof r === "object" && Array.isArray(r.findings) && r.findings.every(validFinding);
  const hrAvailable = () => HR !== null;
  const isOpen = (f) => !["resolved", "closed"].includes(f.status);
  const isBlocker = (f) => f.severity === "publication blocker" && isOpen(f);
  const findingsFor = (clipId) => (hrAvailable() ? HR.findings.filter((f) => f.clip === clipId) : []);

  function readiness(clip) {
    if (!hrAvailable()) {
      return {
        level: "unavailable", title: "Human-review evidence unavailable.",
        text: "The review record could not be loaded, so open publication blockers can't be shown. Treat this clip as not approved.",
      };
    }
    const mine = findingsFor(clip.id);
    if (!mine.length) {
      return { level: "awaiting", title: "Awaiting human review — not approved.", text: "No human review has been recorded for this clip. Automated screening is not approval." };
    }
    const blockers = mine.filter(isBlocker);
    if (blockers.length) {
      return { level: "blocked", title: "Publication blocked.", text: `${blockers.map((f) => f.observation).join(" ")} Human sign-off required.` };
    }
    const decisions = mine.filter((f) => isOpen(f) && f.severity === "needs human decision");
    if (decisions.length) {
      return { level: "decision", title: "Needs a human decision.", text: "An open review finding must be resolved before sign-off.", findings: decisions };
    }
    return { level: "review", title: "Human sign-off required.", text: "Automated screening is not publication approval." };
  }
  function readinessBox(clip) {
    const r = readiness(clip);
    return h("div", { class: `readiness ${r.level}`, role: "note", "data-readiness": r.level }, h("b", {}, r.title), " ", r.text);
  }
  // Compact form for small cards: every visible clip still shows whether it can be published.
  const READINESS_PILL = {
    unavailable: ["fail", "Review evidence unavailable"], blocked: ["fail", "Publication blocked"],
    decision: ["warn", "Needs a human decision"], review: ["", "Not approved: sign-off required"],
    awaiting: ["warn", "Awaiting human review — not approved"],
  };
  function readinessPill(clip) {
    const r = readiness(clip);
    const [cls, label] = READINESS_PILL[r.level];
    return h("span", { class: `pill ${cls}`, "data-readiness": r.level, title: `${r.title} ${r.text}` }, label);
  }

  function video(clip, opts = {}) {
    const el = h("video", {
      src: clip.file, controls: true, playsinline: true, preload: "metadata", loop: opts.loop,
      "data-clip": clip.id, "data-title": opts.title || clip.id,
      "aria-label": `Recorded ${clip.model_name} video${opts.label ? ` of ${opts.label}` : ""}${clip.concept ? `, ${clip.concept}` : ""}` +
        (clip.has_audio ? "" : " (no audio track)"),
    });
    el.muted = !soundOn();
    if (PRESENTATION_VOLUME[clip.id]) el.volume = PRESENTATION_VOLUME[clip.id];
    return el;
  }
  const soundOn = () => !!($("#sound") && $("#sound").checked);
  const ownAudio = (v) => !!(v.dataset && v.dataset.ownAudio);

  function pausePlayers(except = null) {
    document.querySelectorAll("video").forEach((v) => { if (v !== except && !v.paused) v.pause(); });
  }

  // One player at a time; the Sound toggle and each player's native mute control stay in sync. The narrated
  // overview keeps its own audio controls.
  let syncingMute = false;
  let onPlayState = () => {};
  function setSound(on) {
    $("#sound").checked = on;
    syncingMute = true;
    document.querySelectorAll("video").forEach((v) => { if (!ownAudio(v)) v.muted = !on; });
    syncingMute = false;
  }
  document.addEventListener("play", (e) => {
    if (!(e.target instanceof HTMLVideoElement)) return;
    pausePlayers(e.target);
    onPlayState();
  }, true);
  for (const name of ["pause", "ended"]) {
    document.addEventListener(name, (e) => { if (e.target instanceof HTMLVideoElement) onPlayState(); }, true);
  }
  document.addEventListener("volumechange", (e) => {
    if (syncingMute || !(e.target instanceof HTMLVideoElement) || ownAudio(e.target)) return;
    if (e.target.muted === !soundOn()) return;
    setSound(!e.target.muted);
  }, true);

  const evalCheck = (clipId, check) => (EV && EV.media && EV.media[clipId] ? EV.media[clipId].checks[check] : null);
  const GOOD = new Set(["pass", "match", "consistent", "grounded"]);
  const SOFT = new Set(["partial", "split"]);
  function labelPill(label, text, expectedBad) {
    const cls = expectedBad ? "pass" : GOOD.has(label) ? "pass" : SOFT.has(label) ? "warn" : "fail";
    return h("span", { class: `pill ${cls}` }, text);
  }
  function evalPill(chk, name, expectedBad) {
    if (!chk) return null;
    if (!chk.applicable) return h("span", { class: "pill", title: chk.na_reason }, `${name}: N/A`);
    return labelPill(chk.label, `${name}: ${chk.label} (${chk.agreement})`, expectedBad);
  }

  function audioNote(c) {
    if (c.presentation_audio_removed) {
      return h("p", { class: "audio-note none" }, h("b", {}, "Silent presentation edit. "),
        "The model returned an unexpected audio stream; it was removed here, not requested or validated. ",
        h("a", { href: c.original_file }, "Original-audio rendition retained"), ". Original source retained locally.",
        c.presentation_trimmed_to_s ? ` Video trimmed to ${c.presentation_trimmed_to_s} seconds for presentation.` : "",
        c.qa_sampled_from ? " Recorded QA samples come from the retained untrimmed rendition." : "");
    }
    if (!c.has_audio) {
      return h("p", { class: "audio-note none" }, h("b", {}, "No recorded audio track. "),
        `Audio was ${String(c.audio || "").startsWith("native") ? "requested" : "not requested"} for this ${c.model_name} render and the file has no audio stream, so the Sound toggle cannot add one.`);
    }
    if (String(c.audio || "").startsWith("native")) {
      return h("p", { class: "audio-note" }, h("b", {}, "Sound generated by the model."),
        PRESENTATION_VOLUME[c.id]
          ? ` Played here at ${PRESENTATION_VOLUME[c.id] * 100}% volume because a reviewer found it too loud; the original file is unchanged.`
          : "");
    }
    return h("p", { class: "audio-note" }, h("b", {}, "This model added sound that wasn't requested."), " It hasn't been reviewed for meaning.");
  }
  // Signal metrics belong in evidence details, not in the primary narrative.
  function audioMetrics(c) {
    const a = evalCheck(c.id, "audio_signal");
    const m = a && a.measurements;
    if (!c.has_audio || !m) return null;
    return kv([["Measured loudness", `${m.integrated_lufs} LUFS integrated, ${m.true_peak_dbtp > 0 ? "+" : ""}${m.true_peak_dbtp} dBTP true peak`]]);
  }

  function kv(rows) {
    return h("dl", { class: "kv" }, rows.filter(Boolean).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  }
  const inspect = (label, ...kids) => h("details", { class: "inspect" }, h("summary", {}, label), ...kids);

  function scoreCell(q, check) {
    const s = q.scores ? q.scores[check] : null;
    const t = q.thresholds ? q.thresholds[check] : null;
    if (typeof s !== "number") return h("td", {}, "n/a");
    const ok = typeof t === "number" && s >= t;
    return h("td", {},
      h("div", { class: "score" },
        h("span", { class: "mono" }, `${s.toFixed(2)} / ${t}`),
        h("div", { class: "bar", role: "img", "aria-label": `${CHECK_LABEL[check]} ${s} vs threshold ${t}: ${ok ? "meets" : "below"}` },
          h("span", { class: ok ? "ok" : "", style: `width:${Math.round(s * 100)}%` }),
          h("i", { style: `left:${Math.round(t * 100)}%` }))));
  }

  // ---------- page chrome: theme, mobile menu, evidence anchors, overview ----------
  const themes = ["light", "dark"];
  const themeButtons = themes.map((name) => $(`#theme-${name}`));
  function setTheme(name, persist = false) {
    document.documentElement.setAttribute("data-theme", name);
    themeButtons.forEach((b, i) => {
      b.setAttribute("aria-checked", String(themes[i] === name));
      b.setAttribute("tabindex", themes[i] === name ? "0" : "-1");
    });
    if (persist) {
      try { localStorage.setItem("s2s-theme", name); } catch (_) { /* storage unavailable */ }
    }
  }
  themeButtons.forEach((b, i) => b.addEventListener("click", () => setTheme(themes[i], true)));
  $("#theme-toggle").addEventListener("keydown", (e) => {
    const active = document.documentElement.getAttribute("data-theme") === "dark" ? 1 : 0;
    const i = { ArrowRight: 1 - active, ArrowLeft: 1 - active, ArrowUp: 1 - active, ArrowDown: 1 - active, Home: 0, End: 1 }[e.key];
    if (i === undefined) return;
    e.preventDefault();
    setTheme(themes[i], true);
    themeButtons[i].focus();
  });
  setTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light");

  const menu = $("#menu-toggle");
  function setMenu(open) {
    $("#topbar").classList.toggle("nav-open", open);
    menu.setAttribute("aria-expanded", String(open));
  }
  menu.addEventListener("click", () => setMenu(menu.getAttribute("aria-expanded") !== "true"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu.getAttribute("aria-expanded") === "true") { setMenu(false); menu.focus(); }
  });

  function openDetails(id) {
    const el = id && typeof document.getElementById === "function" ? document.getElementById(id) : null;
    if (el && el.tagName === "DETAILS") el.open = true;
  }
  // Hash-routed views: the landing page, guided demo, scenario gallery and technical evidence are shown one at a
  // time. Evidence deep links (#routing, #qa, #evals) open the evidence view with that section expanded. Players in
  // a view that is being hidden are paused (one player at a time), so no invisible audio keeps going.
  const VIEWS = { home: "#view-home", guide: "#guide", scenarios: "#scenarios", evidence: "#evidence" };
  const VIEW_HEADINGS = { home: "#hero-title", guide: "#guide-heading", scenarios: "#scenarios-heading", evidence: "#evidence-heading" };
  const VIEW_ALIASES = { "": "home", top: "home", routing: "evidence", qa: "evidence", evals: "evidence" };
  let currentView = null;
  let routeGuide = () => {};
  function viewFor(id) {
    if (id.startsWith("guide/")) return "guide";
    if (id === "main") return currentView || "home"; // the skip link stays in the current view
    if (VIEWS[id]) return id;
    if (id in VIEW_ALIASES) return VIEW_ALIASES[id];
    const el = typeof document.getElementById === "function" ? document.getElementById(id) : null;
    const host = el && typeof el.closest === "function" ? el.closest("[data-view]") : null;
    return host && VIEWS[host.dataset.view] ? host.dataset.view : "home";
  }
  function showView(id, focus) {
    const name = viewFor(id);
    const changed = name !== currentView;
    if (changed) pausePlayers();
    for (const [key, sel] of Object.entries(VIEWS)) {
      const el = $(sel);
      if (el) el.hidden = key !== name;
    }
    const nav = $("#site-nav");
    if (nav) nav.querySelectorAll("a").forEach((a) => {
      if (a.dataset.view === name) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    currentView = name;
    if (name === "guide") routeGuide(id.split("/")[1] || "qsr");
    openDetails(id);
    const target = id && typeof document.getElementById === "function" ? document.getElementById(id) : null;
    if (target && target.tagName === "DETAILS") {
      if (typeof target.scrollIntoView === "function") target.scrollIntoView();
    } else if (changed && focus) {
      const heading = $(VIEW_HEADINGS[name]);
      if (heading) heading.focus({ preventScroll: true });
      if (typeof window.scrollTo === "function") window.scrollTo(0, 0);
    }
  }
  const hashId = () => decodeURIComponent(window.location.hash.slice(1));
  document.addEventListener("click", (e) => {
    const a = e.target && typeof e.target.closest === "function" ? e.target.closest('a[href^="#"]') : null;
    if (!a) return;
    setMenu(false);
    showView(decodeURIComponent(a.getAttribute("href").slice(1)), true);
  });
  window.addEventListener("hashchange", () => showView(hashId(), true));
  showView(hashId(), false);
  // Sticky guide controls sit directly under the topbar, whose height changes when the mobile menu opens.
  const topbar = $(".topbar");
  if (topbar && typeof ResizeObserver === "function") {
    new ResizeObserver(() => document.documentElement.style.setProperty("--topbar-h", `${topbar.offsetHeight}px`)).observe(topbar);
  }

  const overview = $("#overview");
  const overviewVideo = $("#overview-video");
  $("#watch-overview").addEventListener("click", () => {
    if (typeof overview.showModal === "function") overview.showModal(); else overview.setAttribute("open", "");
    playSafely(overviewVideo, "#overview-status");
  });
  overview.addEventListener("close", () => overviewVideo.pause());
  $("#overview-source").addEventListener("error", () => { $("#overview-error").hidden = false; });

  // ---------- data ----------
  const optionalJson = (url) => fetch(url, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  Promise.all([
    fetch("data.json", { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`data.json ${r.status}`);
      return r.json();
    }),
    optionalJson("evaluations/foundry-evals-v1.json"),
    optionalJson("evaluations/human-review.json"),
  ]).then(([data, ev, hr]) => { EV = ev; HR = validReview(hr) ? hr : null; init(data); }).catch((err) => {
    $("#main").prepend(h("p", { class: "notice", role: "alert" }, `Could not load demo data (${err.message}).`));
  });

  function init(data) {
    const clips = Object.fromEntries(data.clips.map((c) => [c.id, c]));
    const products = data.products;
    if (!hrAvailable()) {
      const alert = $("#review-alert");
      alert.replaceChildren(h("div", { class: "readiness unavailable", role: "alert" },
        h("b", {}, "Human-review evidence unavailable."),
        " The review record could not be loaded, so publication blockers and pending decisions are not shown. " +
        "Treat every clip as not approved."));
      alert.hidden = false;
    }
    initLanding(data, clips, products);
    initScenarios(data, clips, products);
    initEntry(data, clips, products);
    routeGuide = initGuide(data, clips, products);
    if (viewFor(hashId()) === "guide") routeGuide(hashId().split("/")[1] || "qsr");
    $("#fictional-brands").textContent = `Fictional retail examples: ${data.accounts.map((a) => a.fictional_brand).join(", ")}.`;
    initReadinessSummary(data, clips);
    initRouting(data);
    initQa(data, clips, products);
    initEvals(data, clips);
    $("#sound").addEventListener("change", () => setSound(soundOn()));
    // Evidence sections fill in after the data loads, so land a deep link (#qa, #evals) again once they have.
    const deep = hashId() && typeof document.getElementById === "function" ? document.getElementById(hashId()) : null;
    if (deep && deep.tagName === "DETAILS" && typeof deep.scrollIntoView === "function") deep.scrollIntoView({ behavior: "instant" });
  }

  // ---------- landing ----------
  function initLanding(data, clips, products) {
    const hero = clips[data.lto.hero_clip];
    const p = products[data.lto.sku];
    $("#hero-compare").replaceChildren(
      h("div", { class: "compare-pair" },
        h("figure", {}, h("img", { src: p.image, alt: `Approved product image: ${p.name}` }), h("figcaption", {}, "Product image")),
        h("span", { class: "arrow", "aria-hidden": "true" }, "→"),
        h("figure", { class: "vertical" }, video(hero, { label: p.name, title: "hero video" }),
          h("figcaption", {}, `Recorded video · ${hero.model_name}`))),
      readinessBox(hero));
  }

  function initEntry(data, clips, products) {
    $("#entry-grid").replaceChildren(...data.scenarios.map((s) => {
      const c = clips[s.clips[0]];
      const img = c.source_image || products[c.sku].image;
      const dest = `guide/${s.guide}`;
      return h("a", { class: "entry-card card", href: `#${dest}`, onclick: () => showView(dest, true) },
        img ? h("img", { src: img, alt: "" }) : null,
        h("span", { class: "entry-title" }, s.label || s.title),
        h("span", { class: "hint" }, s.story || s.use_case));
    }));
  }

  function accountCard(a, clips, withPreview = false) {
    const recorded = a.recorded_clip && clips[a.recorded_clip];
    return h("article", { class: "card account-card", "data-account": a.id },
      h("h3", {}, a.fictional_brand),
      a.sources.length
        ? h("p", { class: "hint" }, `Inspired by publicly reported priorities of ${a.real_company}. `,
          a.sources.map((s, i) => h("a", { href: s.url }, `${i ? " · " : ""}${s.publisher} (${s.published})`)))
        : h("p", { class: "hint" }, `Representative account: ${a.real_company}. Public-source brief pending.`),
      a.need ? h("p", {}, h("b", {}, "Public priority: "), a.need) : null,
      h("p", {}, h("b", {}, "Video need: "), a.use_case || "Account-specific brief pending public-source review."),
      recorded && recorded.source_image ? h("img", { class: "guide-reference", src: recorded.source_image, alt: `Approved reference for ${a.fictional_brand}'s recorded product` }) : null,
      a.brief ? h("blockquote", {}, a.brief) : null,
      kv([["Channel", `${a.channel} · ${a.aspect_ratio}`], ["Routed model", a.model_name],
        ["Why", a.why], ["Estimate", `${usd(a.estimate_usd)} for ${a.duration} s (${a.tier}); list-price estimate, not a bill`]]),
      h("p", { class: "hint" }, a.hero_clip ? "Recorded PIM hero available; human sign-off still required."
        : "Preview only — no approved PIM hero recorded."),
      recorded ? readinessPill(recorded) : h("span", { class: "pill warn" }, a.excluded_clips?.length ? "Recording withheld — not approved" : "No recording yet"),
      a.review_note ? h("p", { class: "hint review-note" }, h("b", {}, "Reviewer note: "), a.review_note) : null,
      a.excluded_clips?.length ? h("p", { class: "hint" }, `Withheld attempts (${a.excluded_clips.length}): `, a.excluded_clips.map((c) => c.reason).join(" "),
        " Their request and screening evidence are retained in Technical evidence; the media is not published.") : null,
      withPreview && a.planned_clip && recorded ? [
        h("p", { class: "hint" }, "Exploratory silent draft · Awaiting human review — not approved"),
        video(recorded, { title: `${a.fictional_brand} preview` }),
        verdictPill(recorded.qa.verdict),
        inspect("Inspect evidence", audioNote(recorded), h("p", {}, "Not yet evaluated."),
          h("ul", {}, recorded.qa.findings.map((f) => h("li", {}, f)))),
      ] : null,
      withPreview ? learningOf(a, clips).map((c) => learningCard(a, c)) : null);
  }

  // Safe attempts that failed automated screening, shown only to explain what the QA gate caught.
  const learningOf = (a, clips) => (a.learning_clips || []).map((e) => clips[e.id]).filter((c) => c && c.file);
  const LEARNING_LABEL = "QA learning example — failed screening; not approved";
  function learningCard(a, c) {
    return h("div", { class: "learning", "data-learning": c.id },
      h("p", {}, h("span", { class: "pill fail" }, LEARNING_LABEL)),
      h("p", { class: "hint" }, c.learning_note),
      video(c, { title: `${a.fictional_brand} QA learning example` }),
      inspect("Inspect evidence", verdictPill(c.qa.verdict), audioNote(c),
        h("ul", {}, c.qa.findings.map((f) => h("li", {}, f))),
        kv([["Model", c.model_name], ["Request ID", h("span", { class: "mono" }, c.request_id)]])));
  }

  // ---------- guided demo (presenter-controlled; no timers, no auto-scroll, no auto-selection) ----------
  function initGuide(data, clips, products) {
    const lto = data.lto;
    const product = products[lto.sku];
    const hero = clips[lto.hero_clip];
    const drafts = lto.drafts.map((id) => clips[id]);
    const heroConcept = lto.concepts[lto.hero_variant - 1];
    const STEPS = [
      { key: "brief", title: "Brief" },
      { key: "drafts", title: "Draft concepts" },
      { key: "select", title: "Choose a concept" },
      { key: "hero", title: "Recorded hero" },
      { key: "review", title: "Review and sign-off" },
    ];
    const state = { step: 0, selected: null, preview: drafts[0].variant };
    let area = "qsr";
    let chosenRecord = null;
    const areaAccounts = () => data.accounts.filter((a) => a.area === area);
    const extraRecords = () => areaAccounts().filter((a) => a.id !== "northwind").flatMap((a) => {
      const ids = a.draft_clips.length ? a.draft_clips : a.recorded_clip ? [a.recorded_clip] : [];
      return [...ids.filter((id) => clips[id] && clips[id].file).map((id) => ({ account: a, clip: clips[id] })),
        ...learningOf(a, clips).map((c) => ({ account: a, clip: c, learning: true }))];
    });
    const isCoffee = () => area === "qsr";
    const chosenHero = () => chosenRecord ? chosenRecord.clip : hero;
    const chosenProduct = () => chosenRecord ? products[chosenRecord.clip.sku] : product;
    let players = {};
    let selectButton = null;
    const stage = $("#guide-stage");
    const prev = $("#guide-prev"), next = $("#guide-next"), play = $("#guide-play");
    const full = $("#guide-full"), wrap = $("#guide-wrap");
    const areaLinks = data.scenarios.map((s) => h("a", {
      href: `#guide/${s.guide}`, onclick: () => showView(`guide/${s.guide}`, true),
    }, s.title));
    $("#guide-areas").replaceChildren(...areaLinks);

    const canEnter = (i) => i <= 2 || state.selected !== null;
    const chips = STEPS.map((s, i) => h("button", { type: "button", class: "chip", onclick: () => go(i) }, `${i + 1} · ${s.title}`));
    $("#guide-steps").replaceChildren(...chips.map((c) => h("li", {}, c)));

    function currentPlayer() {
      const key = STEPS[state.step].key;
      if (key === "drafts" || key === "select") return players[state.preview] || null;
      if (key === "hero" || key === "review") return players.hero || null;
      return null;
    }
    function updateControls() {
      prev.disabled = state.step === 0;
      next.disabled = state.step === STEPS.length - 1 || !canEnter(state.step + 1);
      const p = currentPlayer();
      const verb = p && !p.paused ? "Pause" : "Play";
      play.disabled = !p;
      play.textContent = verb;
      play.setAttribute("aria-label", p ? `${verb} ${p.dataset.title}` : "No video in this step");
      $("#guide-clip").textContent = !p ? "" : p.error ? "Clip failed to load" : p.readyState >= 1 ? "Clip ready" : "Loading clip…";
      chips.forEach((c, i) => {
        c.setAttribute("aria-current", i === state.step ? "step" : "false");
        c.disabled = !canEnter(i);
        c.classList.toggle("done", i < state.step);
      });
    }
    onPlayState = updateControls;

    function track(v) {
      v.addEventListener("loadedmetadata", updateControls);
      v.addEventListener("error", updateControls);
      return v;
    }
    function notes(agent, title, ...kids) {
      return h("div", { class: "stage-notes" },
        agent ? h("p", { class: "eyebrow" }, agent) : null,
        h("h3", { class: "stage-title", tabindex: "-1" }, title), ...kids);
    }

    function draftCard(c, selectable) {
      const v = track(video(c, { loop: true, title: `concept #${c.variant} preview`, label: product.name }));
      players[c.variant] = v;
      // Previewing never selects: it only sets which clip the Play control drives.
      v.addEventListener("play", () => { state.preview = c.variant; updateControls(); });
      const recorded = c.variant === lto.hero_variant;
      const chosen = state.selected === c.variant;
      let action = null;
      if (selectable && recorded) {
        action = h("button", { type: "button", class: "select", "aria-pressed": String(chosen), onclick: () => select(c.variant) },
          chosen ? `✓ Concept #${c.variant} selected` : `Select concept #${c.variant}`);
        selectButton = action;
      } else if (selectable) {
        action = h("p", { class: "hint" }, "Preview only: this replay has no recorded hero for this concept.");
      }
      return h("article", { class: `card draft vertical${chosen ? " selected" : ""}`, "data-variant": c.variant },
        h("h4", {}, `Concept #${c.variant} · ${c.concept}`),
        h("div", {}, h("span", { class: `pill ${recorded ? "auth" : ""}` }, recorded ? "Recorded hero available" : "Concept preview only"),
          readinessPill(c)),
        v,
        h("div", { class: "card-actions" },
          h("button", { type: "button", class: "ghost preview", onclick: () => { state.preview = c.variant; togglePlay(v); } },
            `Preview concept #${c.variant}`),
          action),
        inspect("Inspect evidence",
          kv([
            ["Model", `${c.model_name} · ${c.mode} · ${c.aspect_ratio}`],
            ["Recorded generation time", secs(c.accepted_to_completed_s)],
            ["Estimate", usd(c.estimate_usd)],
            ["Request ID", h("span", { class: "mono" }, c.request_id)],
          ]),
          audioNote(c),
          audioMetrics(c),
          h("div", {}, verdictPill(c.qa.verdict), evalPill(evalCheck(c.id, "concept_adherence"), "AI eval · concept"))));
    }

    function recordedCard(record, selectable) {
      const { account: a, clip: c, learning } = record;
      const v = track(video(c, { loop: true, title: `${a.fictional_brand} ${learning ? "QA learning example" : "preview"}` }));
      players[c.id] = v;
      v.addEventListener("play", () => { state.preview = c.id; updateControls(); });
      const eligible = !learning && a.hero_clip === c.id && !!c.source_image;
      const chosen = state.selected === a.id;
      const choose = eligible && selectable ? h("button", {
        class: "select", type: "button", "aria-pressed": String(chosen), onclick: () => {
          pausePlayers(v);
          chosenRecord = record;
          state.selected = a.id;
          stage.querySelectorAll("button.select").forEach((b) => b.setAttribute("aria-pressed", "false"));
          stage.querySelectorAll("article.draft").forEach((card) => card.classList.toggle("selected", card.dataset.account === a.id));
          choose.setAttribute("aria-pressed", "true");
          choose.textContent = `${a.fictional_brand} selected`;
          $("#guide-status").textContent = `${a.fictional_brand} selected. Press Next to review its recorded hero.`;
          updateControls();
        },
      }, chosen ? `${a.fictional_brand} selected` : `Select ${a.fictional_brand}`) : null;
      return h("article", { class: `card draft${c.aspect_ratio === "9:16" ? " vertical" : ""}${chosen ? " selected" : ""}`,
        "data-account": a.id, "data-learning": learning ? c.id : null },
        h("h4", {}, learning ? `${a.fictional_brand} · earlier attempt` : a.fictional_brand),
        h("div", {}, learning ? h("span", { class: "pill fail" }, LEARNING_LABEL)
          : h("span", { class: "pill" }, eligible ? "Recorded PIM hero available · no separate draft recorded"
            : c.account ? "Silent draft · Awaiting human review" : "Text-only recording · no PIM hero"),
          c.account ? verdictPill(c.qa.verdict) : null, readinessPill(c)),
        learning ? h("p", { class: "hint" }, c.learning_note) : a.review_note ? h("p", { class: "hint review-note" }, h("b", {}, "Reviewer note: "), a.review_note) : null,
        v,
        h("button", { class: "ghost preview", type: "button", onclick: () => { state.preview = c.id; togglePlay(v); } }, `Preview ${a.fictional_brand}`),
        choose || (selectable ? h("p", { class: "hint" }, "Preview only — no approved PIM hero recorded.") : null),
        inspect("Inspect evidence", verdictPill(c.qa.verdict), audioNote(c),
          evalCheck(c.id, "concept_adherence") ? evalPill(evalCheck(c.id, "concept_adherence"), "AI eval · concept")
            : h("p", {}, "Not yet evaluated."),
          kv([["Model", c.model_name], ["Request ID", h("span", { class: "mono" }, c.request_id)]])));
    }
    function previews(selectable) {
      return h("div", { class: "stage-media drafts" },
        isCoffee() ? drafts.map((c) => draftCard(c, selectable)) : null,
        extraRecords().map((r) => recordedCard(r, selectable)),
        areaAccounts().filter((a) => !a.recorded_clip && !a.draft_clips.length).map((a) =>
          h("article", { class: "card", "data-account": a.id }, h("h4", {}, a.fictional_brand),
            h("p", {}, a.excluded_clips?.length ? ["Recordings withheld from the primary demo. ",
              h("a", { href: "#qa" }, "Inspect the retained screening evidence.")]
              : "No recording yet. No video has been generated for this example."),
            h("p", { class: "hint" }, "Preview only — no approved PIM hero recorded."))));
    }
    function generalHero(review) {
      const c = chosenHero(), p = chosenProduct();
      players.hero = track(video(c, { title: "recorded hero", label: p.name }));
      return [
        h("div", { class: `stage-media${c.aspect_ratio === "9:16" ? " vertical" : ""}` },
          !review && c.source_image ? h("figure", {}, h("img", { class: "guide-reference", src: c.source_image, alt: `Approved product image: ${p.name}` }),
            h("figcaption", {}, "Approved product image → recorded video")) : null, players.hero),
        notes(review ? "@brand-qa + human reviewer" : "@foundry-router", review ? "Review and sign-off" : `Recorded hero: ${chosenRecord.account.fictional_brand}`,
          h("p", {}, `Recorded ${c.model_name} ${c.mode}; no generation occurs in this browser.`),
          verdictPill(c.qa.verdict), readinessBox(c), audioNote(c),
          evalCheck(c.id, "product_identity") ? evalPill(evalCheck(c.id, "product_identity"), "AI eval · identity") : h("p", {}, "Not yet evaluated."),
          inspect("Inspect evidence", kv([["Estimate", usd(c.estimate_usd)], ["Request ID", h("span", { class: "mono" }, c.request_id)]])),
          h("a", { href: "#evidence" }, "Inspect all technical evidence"))];
    }
    function select(variant) {
      pausePlayers(players[variant]);
      chosenRecord = null;
      state.selected = variant;
      if (selectButton) {
        selectButton.setAttribute("aria-pressed", "true");
        selectButton.textContent = `✓ Concept #${variant} selected`;
      }
      $("#guide-status").textContent = `Concept #${variant} selected. Press Next to see its recorded hero render.`;
      updateControls();
    }

    const draftPasses = drafts.filter((c) => c.qa.verdict === "pass").length;
    const RENDER = {
      brief: () => [
        h("div", { class: "account-grid" }, areaAccounts().map((a) => accountCard(a, clips))),
        notes("@retail-merchandiser", "Start from a product and a short brief",
          h("p", {}, "Choose the area, inspect the fictional account briefs, and move through the recordings deliberately. Sources describe public priorities, not customer data."),
          isCoffee() ? h("blockquote", {}, lto.presenter_prompt) : null,
          isCoffee() ? inspect("Technical detail", kv([
            ["Product ID (SKU)", lto.sku], ["Channel", lto.channel], ["Image status (PIM)", product.image_status],
          ])) : null),
      ],
      drafts: () => [
        previews(false),
        notes("@foundry-router", "Compare quick, low-cost drafts",
          h("p", {}, "The router sends early ideas to fast, lower-cost video models so the team can compare concepts before paying for a final render."),
          h("p", {}, "Watching a draft never chooses it. Preview as many as you like."),
          isCoffee() ? h("p", { class: "hint" }, `${draftPasses === 0 ? "None" : `${draftPasses} of ${drafts.length}`} of the three coffee drafts passed the final-brand screen; concept #2, for example, has garbled lettering. ` +
            "Drafts are for comparing ideas; that is an observation about these clips, not a rule that drafts must fail.") : h("p", { class: "hint" }, "Existing PIM heroes are labelled as recorded examples, not invented draft runs. New text-only drafts cannot unlock a hero.")),
      ],
      select: () => {
        selectButton = null;
        return [
          previews(true),
          notes("Presenter", "Choose a concept",
            h("p", {}, isCoffee() ? `Only concept #${lto.hero_variant} (${heroConcept.title}) has a recorded hero render in this replay. The other concepts are preview only.`
              : "Only an existing recorded PIM hero can be selected. Text-only previews have no approved PIM hero recorded."),
            h("p", {}, "This page can't generate video. In live mode, choosing another concept would start a new, billable Foundry job."),
            h("p", { class: "hint" }, state.selected ? isCoffee() ? `Concept #${state.selected} is selected.`
              : `${chosenRecord.account.fictional_brand} is selected.` : "Select the concept to continue.")),
        ];
      },
      hero: () => {
        if (!isCoffee()) return generalHero(false);
        players.hero = track(video(hero, { label: product.name, title: "recorded hero" }));
        return [
          h("div", { class: "stage-media vertical" }, players.hero),
          notes("@foundry-router", `Recorded hero: concept #${lto.hero_variant}`,
            h("p", {}, `The router upgraded the chosen concept to ${hero.model_name} (${hero.mode}), starting from the approved product image and requesting native audio.`),
            verdictPill(hero.qa.verdict),
            readinessBox(hero),
            audioNote(hero),
            inspect("Inspect evidence",
              kv([
                ["Model", `${hero.model_name} (${hero.mode})`],
                ["Source", "Approved product image (start frame)"],
                ["Recorded generation time", `${secs(hero.accepted_to_completed_s)} (accepted→completed)`],
                ["Estimate", `${usd(hero.estimate_usd)} (preview list price × requested seconds)`],
                ["Request ID", h("span", { class: "mono" }, hero.request_id)],
                ["Rendered", hero.rendered_at],
              ]),
              audioMetrics(hero),
              h("div", {},
                evalPill(evalCheck(hero.id, "product_identity"), "AI eval · identity"),
                evalPill(evalCheck(hero.id, "brand_marks"), "AI eval · brand marks"),
                evalPill(evalCheck(hero.id, "audio_signal"), "Audio signal")))),
        ];
      },
      review: () => {
        if (!isCoffee()) return generalHero(true);
        players.hero = track(video(hero, { label: product.name, title: "recorded hero" }));
        const blocker = findingsFor(hero.id).find(isBlocker);
        return [
          h("div", { class: "stage-media vertical" }, players.hero),
          notes("@brand-qa + human reviewer", "Review before anything is published",
            h("p", {}, `Automated screening ${screening(hero.qa.verdict)} on sampled frames. Screening is an aid, not approval.`),
            readinessBox(hero),
            blocker && blocker.resolution_options ? h("div", {}, h("p", {}, h("b", {}, "Ways to resolve it")),
              h("ul", {}, blocker.resolution_options.map((t) => h("li", {}, t)))) : null,
            h("p", {}, h("a", { href: "#evidence" }, "Inspect all technical evidence"))),
        ];
      },
    };

    function render() {
      pausePlayers();
      players = {};
      const step = STEPS[state.step];
      stage.replaceChildren(h("div", { class: `stage stage-${step.key}${step.key === "brief" ? " stage-accounts" : ""}` }, ...RENDER[step.key]()));
      $("#guide-status").textContent = `Step ${state.step + 1} of ${STEPS.length}: ${step.title}`;
      updateControls();
      const active = document.activeElement;
      if (active && active.disabled) {
        const title = stage.querySelector(".stage-title");
        if (title) title.focus();
      }
    }
    function go(i) {
      if (i < 0 || i >= STEPS.length || i === state.step || !canEnter(i)) return;
      state.step = i;
      render();
    }
    function restart() {
      state.step = 0;
      state.selected = null;
      chosenRecord = null;
      state.preview = isCoffee() ? drafts[0].variant : extraRecords()[0]?.clip.id;
      render();
    }

    prev.addEventListener("click", () => go(state.step - 1));
    next.addEventListener("click", () => go(state.step + 1));
    play.addEventListener("click", () => { const p = currentPlayer(); if (p) togglePlay(p); });
    $("#guide-restart").addEventListener("click", restart);
    wrap.addEventListener("keydown", (e) => {
      const tag = e.target && e.target.tagName;
      if (["VIDEO", "INPUT", "SELECT", "TEXTAREA"].includes(tag)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); go(state.step + 1); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); go(state.step - 1); }
    });

    const fullscreenOk = !!(document.fullscreenEnabled && typeof wrap.requestFullscreen === "function");
    full.hidden = !fullscreenOk;
    full.addEventListener("click", () => {
      showIssue("#guide-alert", "");
      const exiting = !!document.fullscreenElement;
      let p;
      try { p = exiting ? document.exitFullscreen() : wrap.requestFullscreen(); } catch (err) { p = Promise.reject(err); }
      if (p && typeof p.catch === "function") {
        p.catch((err) => showIssue("#guide-alert", exiting
          ? `Couldn't leave fullscreen${reason(err)}. Press Esc to exit.`
          : `Fullscreen isn't available here${reason(err)}. Use your browser's own full-screen view (F11 on Windows) instead.`));
      }
    });
    document.addEventListener("fullscreenchange", () => {
      full.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
    });
    render();
    return (key) => {
      const s = data.scenarios.find((item) => item.guide === key) || data.scenarios[0];
      if (s.guide !== area) {
        area = s.guide;
        restart();
      }
      $("#guide-area-label").textContent = `Guided demo · ${s.title}`;
      areaLinks.forEach((a, i) => a.setAttribute("aria-current", String(data.scenarios[i].guide === area)));
    };
  }

  // ---------- scenario gallery ----------
  function initScenarios(data, clips, products) {
    const tabs = $("#scenario-tabs");
    const panel = $("#scenario-panel");
    let current = 0;
    const buttons = data.scenarios.map((s, i) => h("button", {
      type: "button", role: "tab", id: `tab-${s.vertical}`, "aria-controls": "scenario-panel",
      "aria-selected": "false", tabindex: "-1", onclick: () => select(i, false),
    }, s.label || s.title));
    tabs.replaceChildren(...buttons);
    tabs.addEventListener("keydown", (e) => {
      const n = buttons.length;
      const target = { ArrowRight: (current + 1) % n, ArrowLeft: (current - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
      if (target === undefined) return;
      e.preventDefault();
      select(target, true);
    });

    function card(c, s) {
      const p = products[c.sku];
      const input = c.source_image
        ? h("img", { class: "pim", src: c.source_image, alt: `Approved product image: ${p.name}` })
        : h("div", { class: "placeholder" }, "Text brief only: no product image was used.");
      const r = readiness(c);
      return h("article", { class: `card scenario-card${c.aspect_ratio === "9:16" ? " vertical" : ""}` },
        h("h3", {}, p.name),
        h("div", { class: "pair" },
          h("figure", {}, input, h("figcaption", {}, c.source_image ? "Product image" : "Input")),
          h("figure", {}, video(c, { label: p.name, title: p.name }), h("figcaption", {}, "Recorded video"))),
        h("div", { class: "readiness-line" }, verdictPill(c.qa.verdict), readinessBox(c)),
        inspect("Inspect evidence",
          h("p", {}, h("b", {}, "Why this model: "), s.why),
          kv([
            ["Model", `${c.model_name} · ${c.mode} · ${c.aspect_ratio}`],
            ["Recorded generation time", `${secs(c.accepted_to_completed_s)} (accepted→completed)`],
            ["Estimate", usd(c.estimate_usd)],
            c.qa.failed_checks.length ? ["Failed checks", c.qa.failed_checks.join(", ")] : null,
            c.qa.findings.length ? ["Top finding", c.qa.findings[0]] : null,
            ["Request ID", h("span", { class: "mono" }, c.request_id)],
          ]),
          r.findings ? h("ul", {}, r.findings.map((f) => h("li", {}, f.observation))) : null,
          audioNote(c),
          audioMetrics(c),
          h("div", {},
            evalPill(evalCheck(c.id, "concept_adherence"), "AI eval · concept"),
            evalPill(evalCheck(c.id, "product_identity"), "identity"),
            evalPill(evalCheck(c.id, "brand_marks"), "brand marks"))));
    }

    function select(i, focus) {
      pausePlayers();
      current = i;
      buttons.forEach((b, j) => {
        b.setAttribute("aria-selected", String(i === j));
        b.setAttribute("tabindex", i === j ? "0" : "-1");
      });
      panel.setAttribute("aria-labelledby", buttons[i].getAttribute("id"));
      if (focus) buttons[i].focus();
      const s = data.scenarios[i];
      panel.replaceChildren(
        h("p", { class: "lede small" }, s.story || s.use_case, " ", h("span", { class: "hint" }, `Examples: ${s.accounts}.`)),
        h("p", {}, h("a", { href: `#guide/${s.guide}`, onclick: () => showView(`guide/${s.guide}`, true) }, `Start ${s.title} guided demo`)),
        h("div", { class: "account-grid" }, data.accounts.filter((a) => a.area === s.guide).map((a) => accountCard(a, clips, true))),
        h("div", { class: `scenario${s.clips.length === 1 ? " single" : ""}` }, s.clips.map((id) => card(clips[id], s))));
    }
    select(0, false);
    return { select, buttons };
  }

  // ---------- readiness summary (always visible in the evidence section) ----------
  function initReadinessSummary(data, clips) {
    const all = data.clips;
    const original = all.filter((c) => !c.account);
    const pass = original.filter((c) => c.qa.verdict === "pass").length;
    const stat = (big, text) => h("div", { class: "stat" }, h("b", {}, big), text);
    const base = [
      stat(`${pass} of ${original.length}`, "original recorded clips passed automated screening"),
      stat(String(all.length), "need human sign-off before publication"),
      stat(`${data.accounts.filter((a) => a.recorded_clip && clips[a.recorded_clip] && clips[a.recorded_clip].file).length} of ${data.accounts.length}`,
        "fictional accounts have a playable recorded example"),
      stat(String(all.filter((c) => c.withheld_reason).length), "attempts withheld; evidence only, media not published"),
    ];
    const box = $("#readiness-summary");
    if (!hrAvailable()) {
      box.replaceChildren(
        h("div", { class: "readiness unavailable", role: "note", "data-readiness": "unavailable" },
          h("b", {}, "Human-review evidence unavailable."),
          " Publication blockers and pending decisions can't be shown, so their count is unknown, not zero."),
        h("div", { class: "qa-summary" }, base));
      return;
    }
    const blockers = HR.findings.filter(isBlocker);
    const decisions = HR.findings.filter((f) => isOpen(f) && f.severity === "needs human decision");
    const name = (id) => (clips[id] ? clips[id].concept || id : id);
    box.replaceChildren(
      h("div", { class: "qa-summary" }, base,
        stat(String(blockers.length), "open publication blockers"),
        stat(String(decisions.length), "findings waiting for a human decision")),
      blockers.map((f) => h("div", { class: "readiness blocked", role: "note", "data-readiness": "blocked" },
        h("b", {}, `Publication blocker · ${name(f.clip)}: `), f.observation, " ",
        h("span", { class: "hint" }, f.mitigation_in_demo || ""))));
  }

  // ---------- routing and cost ----------
  function initRouting(data) {
    const table = $("#models-table");
    table.append(
      h("thead", {}, h("tr", {}, ["Model", "Modes", "Offering", "Speed tier", "Native audio", "Durations", "Price tiers", "Strengths"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, data.models.map((m) => h("tr", {},
        h("th", { scope: "row" }, m.name), h("td", {}, m.modes.join(", ")), h("td", {}, m.offering),
        h("td", {}, m.speed_tier), h("td", {}, m.native_audio ? "yes" : "no"),
        h("td", {}, m.durations_by_tier
          ? Object.entries(m.durations_by_tier).map(([t, d]) => h("div", {}, `${t}: ${d.length > 8 ? `${d[0]}–${d[d.length - 1]} (whole seconds)` : d.join(", ")} s`))
          : `${m.duration_range[0]}–${m.duration_range[1]} s`),
        h("td", {}, Object.entries(m.price_per_second_usd).map(([k, v]) => h("div", { class: "mono" }, `${k}: $${v}/s`))),
        h("td", {}, m.strengths.join("; "))))));

    const mSel = $("#calc-model"), tSel = $("#calc-tier");
    const secChoice = $("#calc-sec-choice"), secInput = $("#calc-sec"), nIn = $("#calc-n");
    const model = () => data.models.find((x) => x.key === mSel.value) || data.models[0];
    const tierPrice = (m) => m.price_per_second_usd[tSel.value];
    // Allowed durations come from data.json, derived at build time from the real payload validator, per price tier
    // (e.g. LTX-2.5 Fast caps at 10 s at 1440p/2160p). Range models have no list.
    const choicesOf = (m) => (m.durations_by_tier ? m.durations_by_tier[tSel.value] || [] : []);
    mSel.replaceChildren(...data.models.map((m) => h("option", { value: m.key }, m.name)));

    function fillTiers() {
      const m = model();
      tSel.replaceChildren(...Object.entries(m.price_per_second_usd).map(([k, v]) => h("option", { value: k }, `${k} ($${v}/s)`)));
    }
    function fillDurations() {
      const m = model();
      const choices = choicesOf(m);
      if (m.durations_by_tier) {
        const keep = Number(secChoice.value);
        $("#calc-sec-choice-wrap").hidden = false;
        $("#calc-sec-wrap").hidden = true;
        secChoice.replaceChildren(...choices.map((d) => h("option", { value: String(d) }, `${d} s`)));
        const pick = choices.includes(keep) ? keep : choices.includes(Number(m.default_duration)) ? Number(m.default_duration) : choices[0];
        secChoice.value = pick === undefined ? "" : String(pick);
        const auto = m.supports_auto ? " “auto” lets the model choose and can't be priced in advance." : "";
        $("#calc-sec-help").textContent = `${m.name} at ${tSel.value} supports ${choices.join(", ")} s.${auto}`;
      } else {
        const [lo, hi] = m.duration_range;
        const wasShown = !$("#calc-sec-wrap").hidden;
        const raw = String(secInput.value ?? "").trim();
        const keep = raw === "" ? NaN : Number(raw);
        $("#calc-sec-choice-wrap").hidden = true;
        $("#calc-sec-wrap").hidden = false;
        secInput.setAttribute("min", String(lo));
        secInput.setAttribute("max", String(hi));
        // Keep a custom duration the user already entered when it is still in range (e.g. a price-tier change).
        secInput.value = wasShown && Number.isFinite(keep) && keep >= lo && keep <= hi ? raw : String(m.default_duration);
        $("#calc-sec-help").textContent = `${m.name} accepts any duration from ${lo} to ${hi} s (fractions allowed).`;
      }
    }
    function readSeconds(m) {
      if (m.durations_by_tier) {
        const choices = choicesOf(m);
        const v = Number(secChoice.value);
        return secChoice.value !== "" && choices.includes(v) ? { ok: v } : { error: `Choose one of ${choices.join(", ")} s for ${m.name} at ${tSel.value}.` };
      }
      const [lo, hi] = m.duration_range;
      const raw = String(secInput.value ?? "").trim();
      const v = raw === "" ? NaN : Number(raw);
      if (!Number.isFinite(v) || v < lo || v > hi) {
        return { error: `Enter a duration from ${lo} to ${hi} seconds for ${m.name}.`, field: true };
      }
      return { ok: v };
    }
    function readClips() {
      const raw = String(nIn.value ?? "").trim();
      if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw)) || Number(raw) < 1) {
        return { error: "Enter a whole number of clips (1 or more)." };
      }
      return { ok: Number(raw) };
    }
    function calc() {
      const m = model();
      const s = readSeconds(m), n = readClips();
      secInput.setAttribute("aria-invalid", String(!!s.field));
      nIn.setAttribute("aria-invalid", String(!!n.error));
      const errors = [s.error, n.error].filter(Boolean);
      if (errors.length) {
        $("#calc-out").textContent = "No estimate";
        $("#calc-error").textContent = errors.join(" ");
        return;
      }
      const price = tierPrice(m);
      if (typeof price !== "number") {
        $("#calc-out").textContent = "No estimate";
        $("#calc-error").textContent = "Choose a price tier.";
        return;
      }
      $("#calc-error").textContent = "";
      $("#calc-out").textContent = `${usd(price * s.ok * n.ok)} estimated for ${n.ok.toLocaleString("en-US")} × ${s.ok} s`;
    }
    mSel.addEventListener("change", () => { fillTiers(); fillDurations(); calc(); });
    tSel.addEventListener("change", () => { fillDurations(); calc(); });
    $("#calc").addEventListener("input", calc);
    $("#calc").addEventListener("change", calc);
    $("#calc").addEventListener("submit", (e) => e.preventDefault());
    fillTiers(); fillDurations(); calc();
  }

  // ---------- recorded QA screening ----------
  function initQa(data, clips, products) {
    const all = data.clips;
    const pass = all.filter((c) => c.qa.verdict === "pass").length;
    const sev = all.map((c) => c.qa.content_safety_max_severity).filter((s) => s !== null);
    $("#qa-summary").replaceChildren(
      h("div", { class: "stat" }, h("b", {}, "2 / 8"), "original clips passed; baseline unchanged"),
      h("div", { class: "stat" }, h("b", {}, `${pass} / ${all.length}`), "passed automated screening"),
      h("div", { class: "stat" }, h("b", {}, `${all.filter((c) => c.qa.verdict === "fail").length}`), "failed at least one threshold"),
      h("div", { class: "stat" }, h("b", {}, sev.length ? String(Math.max(...sev)) : "n/a"), "max Content Safety severity"),
      h("div", { class: "stat" }, h("b", {}, `${all.filter((c) => c.qa.human_signoff_required).length}`), "require human sign-off"));

    $("#qa-table").append(
      h("thead", {}, h("tr", {}, ["Clip", "Model", "Verdict", ...CHECKS.map((c) => CHECK_LABEL[c]), "Safety max", "Request ID"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, all.map((c) => h("tr", {},
        h("th", { scope: "row" }, c.id, h("div", { class: "hint" }, c.concept || products[c.sku].name),
          c.withheld_reason ? h("p", {}, h("b", {}, "Withheld; media not published: "), c.withheld_reason) : null,
          c.learning_note ? h("p", {}, h("b", {}, `${LEARNING_LABEL}: `), c.learning_note) : null,
          c.account ? inspect("Screening findings", h("ul", {}, c.qa.findings.map((f) => h("li", {}, f)))) : null),
        h("td", {}, c.model_name),
        h("td", {}, h("span", { class: `pill ${c.qa.verdict === "pass" ? "pass" : "fail"}` }, c.qa.verdict)),
        CHECKS.map((k) => scoreCell(c.qa, k)),
        h("td", {}, c.qa.content_safety_max_severity ?? "n/a"),
        h("td", { class: "mono" }, c.request_id)))));

    const n = data.negative_control;
    if (n) {
      $("#neg-control").replaceChildren(
        h("p", { class: "eyebrow" }, "Negative control (not a failed render)"),
        h("h3", {}, "Cold brew clip scored against the drill reference"),
        h("p", {}, n.description),
        verdictPill(n.qa.verdict),
        kv([
          ["Scores", CHECKS.map((k) => `${CHECK_LABEL[k]} ${n.qa.scores[k]}`).join(" · ")],
          ["Reference SKU", n.reference_sku],
          ["Takeaway", "The evaluator rejected an obvious product mismatch, as expected. This shows the fail path works; it is not a calibration."],
        ]));
    }
  }

  // ---------- AI evaluations (recorded Foundry Evals runs) ----------
  const MEDIA_CHECKS = [
    ["concept_adherence", "Concept adherence", "visual"],
    ["product_identity", "Product identity", "visual"],
    ["brand_marks", "Brand marks", "visual"],
    ["audio_signal", "Audio signal", "audio signal"],
  ];
  const WHY_FAIL = {
    "lto-draft-1": "Measured QA found warped/blurred branding, partially legible text, product differences and missing scene details.",
    "lto-draft-2": "Measured QA found garbled, unreadable lettering, product color/branding differences and incomplete scene adherence.",
    "lto-draft-3": "Measured QA found an altered logo, illegible text, product differences and missing prompt details.",
    "hero-home-kling": "Prompt adherence 0.72 vs 0.75 threshold: job-site scene and tracking motion not clearly shown.",
    "hero-patio-h3max": "Text-to-video with no PIM input: no FABRIKAM label rendered, so logo and label checks score 0.",
    "hero-grocery-turbo": "Genuine product failure: the bundle omits the thermometer and honey from the approved PIM image.",
  };

  function repeatsDetail(chk) {
    const reps = chk.repeats || chk.cloud || [];
    return h("ol", { class: "reps" }, reps.map((r) => h("li", {},
      h("span", { class: "mono" }, r.run_id), " · grader ", h("b", {}, r.grader_label || "n/a"),
      ` · service ${r.service_label} (score ${r.service_score})`,
      r.reasons && r.reasons.length ? h("ul", {}, r.reasons.map((t) => h("li", {}, t))) : null)));
  }

  function humanFindings() {
    if (!hrAvailable()) {
      return h("div", { class: "readiness unavailable", role: "note", "data-readiness": "unavailable" },
        h("b", {}, "Human-review evidence unavailable."),
        " Human feedback and evaluator/agent findings could not be loaded; their absence here is not a clean result.");
    }
    return h("div", {},
      h("h3", { class: "sub" }, "Human feedback and evaluator/agent findings"),
      h("div", { class: "findings" }, HR.findings.map((f) => h("article", { class: `card finding ${isBlocker(f) ? "blocking" : ""}` },
        h("p", { class: "eyebrow" }, `${f.severity} · ${f.status}`),
        h("h4", {}, f.clip || f.case),
        h("p", {}, f.observation),
        f.measured_signal ? h("p", { class: "hint" }, f.measured_signal) : null,
        f.handling || f.mitigation_in_demo ? h("p", { class: "hint" }, f.handling || f.mitigation_in_demo) : null,
        h("p", { class: "hint" }, `Source: ${f.source}`)))));
  }

  function initEvals(data, clips) {
    const root = $("#evals-body");
    if (!EV) {
      root.replaceChildren(
        h("div", { class: "readiness unavailable", role: "note" }, h("b", {}, "AI evaluation evidence unavailable."),
          " The recorded evaluation results could not be loaded."),
        humanFindings());
      return;
    }
    const totalRuns = Object.values(EV.runs).reduce((n, r) => n + r.runs.length, 0);
    const completed = Object.values(EV.runs).reduce((n, r) => n + r.runs.filter((x) => x.status === "completed").length, 0);
    const neg = EV.negative_control;
    root.replaceChildren(
      h("div", { class: "qa-summary" },
        h("div", { class: "stat" }, h("b", {}, `${completed} / ${totalRuns}`),
          `Foundry Evals runs completed (+${EV.superseded_audio_runs.runs.length} failed audio runs superseded)`),
        h("div", { class: "stat" }, h("b", {}, `${EV.repeats}×`), "repeats per LLM check; one audio-signal run"),
        h("div", { class: "stat" }, h("b", {}, neg.expected_behavior_met ? "rejected" : "MISSED"), `negative control (${neg.agreement})`),
        h("div", { class: "stat" }, h("b", {}, usd(EV.cost.estimated_usd_this_run)), `estimated spend (cap ${usd(EV.cost.cap_usd)})`)),

      h("div", { class: "card method" },
        h("h3", {}, "How these evaluations work"),
        h("ol", {},
          h("li", {}, h("b", {}, "Stage A, vision observation: "), `the brand-qa-vision deployment describes ${EV.frames_per_clip} sampled frames per clip, with an approved PIM reference only where supplied. It writes neutral observations, not scores.`),
          h("li", {}, h("b", {}, "Stage B, Foundry Evals: "), "text graders in Microsoft Foundry score those observations against stage-aware rubrics, three repeats each. Routing decisions are evaluated separately, and a Python grader checks audio signal measurements."),
          h("li", {}, h("b", {}, "Why two stages: "), `${EV.image_input_spikes.length} native image-input grader spikes were rejected by the service ("${EV.image_input_spikes[0].error}"). Visual checks therefore depend on Stage A's text observations and can miss details a direct visual judge would catch.`)),
        h("p", { class: "hint" }, "Scope: visual checks judge frames, not motion or full clips. The audio check measures stream, loudness and true peak only; " +
          "it cannot tell whether sounds match the picture. None of this replaces human review, and none of it changes the original QA verdicts.")),

      h("div", { class: "card why" },
        h("h3", {}, "Why does the original QA show so many fails?"),
        h("p", {}, "The original @brand-qa screen applies per-brand final-brand thresholds. Six of eight recorded clips fail measured criteria, for different reasons; text-only drafts are not required to fail:"),
        h("ul", {}, Object.entries(WHY_FAIL).map(([id, why]) => h("li", {}, h("b", {}, clips[id] ? (clips[id].concept || id) : id), `: ${why}`))),
        h("p", { class: "hint" }, "The AI evaluations below separate concept adherence from final-brand fidelity and mark checks that do not apply as N/A. " +
          "Concept adherence is 'partial' for all eight clips: the Foundry Evals service reports any non-passing label as 'fail' (score 0), so the grader's own label is shown here, with the service label alongside.")),

      h("div", { class: "table-wrap" },
        h("table", { class: "evals-table" },
          h("caption", {}, "Media checks: grader label (agreement across repeats). Hover N/A for the reason."),
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Clip"), h("th", { scope: "col" }, "Stage"),
            MEDIA_CHECKS.map(([, name, scope]) => h("th", { scope: "col" }, name, h("div", { class: "hint" }, scope))))),
          h("tbody", {}, Object.entries(EV.media).map(([id, m]) => h("tr", {},
            h("th", { scope: "row" }, id, h("div", { class: "hint" }, clips[id] ? (clips[id].concept || clips[id].sku) : "cold brew frames vs drill reference")),
            h("td", {}, m.stage),
            MEDIA_CHECKS.map(([key]) => {
              const chk = m.checks[key];
              if (!chk) return h("td", {}, "n/a");
              const expectedBad = id === "negative-control" && key === "product_identity" && chk.label === "mismatch";
              if (!chk.applicable) return h("td", {}, h("span", { class: "pill" }, "N/A"), h("div", { class: "hint" }, chk.na_reason));
              const svc = [...new Set((chk.repeats || chk.cloud || []).map((r) => r.service_label))];
              return h("td", {}, labelPill(chk.label, `${chk.label} (${chk.agreement})`, expectedBad),
                svc.length && svc.join() !== chk.label ? h("div", { class: "hint" }, `service label: ${svc.join("/")}`) : null,
                chk.needs_human_review ? h("div", { class: "hint warn-text" }, "Needs human review") : null,
                expectedBad ? h("div", { class: "hint" }, "Expected: control rejected") : null);
            })))))),

      h("details", { class: "card" },
        h("summary", {}, "Per-check reasons, observations and run IDs"),
        Object.entries(EV.media).map(([id, m]) => h("div", { class: "clip-detail" },
          h("h4", {}, id),
          m.observation ? h("p", { class: "hint" }, h("b", {}, "Stage A observation: "), m.observation.scene_summary, " ", m.observation.comparison_notes) : null,
          MEDIA_CHECKS.filter(([key]) => m.checks[key] && m.checks[key].applicable).map(([key, name]) => {
            const chk = m.checks[key];
            return h("div", {}, h("b", {}, `${name}: ${chk.label} (${chk.agreement})`),
              chk.scope ? h("span", { class: "hint" }, ` · ${chk.scope}`) : null,
              chk.local ? h("p", { class: "hint" }, `Local ffmpeg check: ${chk.local.label}${chk.local.reasons.length ? ` (${chk.local.reasons.join("; ")})` : ""}`) : null,
              repeatsDetail(chk));
          })))),

      h("h3", { class: "sub" }, "Routing evaluation (@foundry-router)"),
      h("div", { class: "table-wrap" },
        h("table", {},
          h("caption", {}, "Recorded routing decisions vs expected rules"),
          h("thead", {}, h("tr", {}, ["Case", "Rule", "Expected", "Actual", "Model", "Mode", "Rationale grounded"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", {}, Object.entries(EV.routing).map(([id, r]) => h("tr", {},
            h("th", { scope: "row" }, id), h("td", {}, r.case.rule),
            h("td", {}, `${r.case.expected_model} · ${r.case.expected_mode}`),
            h("td", {}, `${r.case.actual_model} · ${r.case.actual_mode}`),
            ["model_matches_expected", "mode_matches_expected", "rationale_grounded"].map((k) =>
              h("td", {}, labelPill(r[k].label, `${r[k].label} (${r[k].agreement})`)))))))),

      humanFindings(),

      h("details", { class: "card" },
        h("summary", {}, "Run evidence, versions and cost"),
        h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ["Eval", "Eval ID", "Dataset", "Run ID", "Status", "Passed / total"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", {}, Object.entries(EV.runs).flatMap(([name, r]) => r.runs.map((x) => h("tr", {},
            h("td", {}, name), h("td", { class: "mono" }, r.eval_id), h("td", {}, `${r.dataset.kind}, ${r.dataset.rows} rows`),
            h("td", { class: "mono" }, x.run_id), h("td", {}, x.status),
            h("td", {}, x.result_counts ? `${x.result_counts.passed} / ${x.result_counts.total}` : "n/a"))))))),
        kv([
          ["Grader model", EV.grader_model.join(", ")],
          ["Versions", Object.entries(EV.versions).map(([k, v]) => `${k}=${v}`).join(" · ")],
          ["Hashes", h("span", { class: "mono" }, Object.entries(EV.hashes).filter(([k]) => k !== "note").map(([k, v]) => `${k}: ${v}`).join(" · "))],
          ["Cost", `${usd(EV.cost.estimated_usd_this_run)} estimated (${EV.cost.input_tokens.toLocaleString()} input + ${EV.cost.output_tokens.toLocaleString()} output tokens at an assumed $${EV.cost.assumed_usd_per_m_input}/M input, $${EV.cost.assumed_usd_per_m_output}/M output, plus a ${usd(EV.cost.spike_reservation_usd)} spike reservation). ${EV.cost.correction}`],
          ["Superseded audio runs", `${EV.superseded_audio_runs.runs.length} failed runs kept as evidence. ${EV.superseded_audio_runs.diagnosis}`],
          ["Recorded", EV.created_at],
        ])));
  }
})();
