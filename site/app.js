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
  let DISPOSITIONS = null;

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
  const DECISION_REASON = {
    "drill-reference-vs-brand-rule": "Reference image conflicts with the written brand rule.",
    "grocery-qa-vs-eval-disagreement": "Original QA and later identity evaluation disagree.",
  };
  const decisionReason = (r) => (r.findings || []).map((f) => DECISION_REASON[f.id]).filter(Boolean).join(" ");
  const accountForClip = (data, c) => data.accounts.find((a) =>
    a.recorded_clip === c.id || a.id === c.account || a.draft_clips.includes(c.id));
  function recordingName(data, c) {
    const a = accountForClip(data, c);
    return `${a ? `${a.fictional_brand} · ` : ""}${c.concept || c.id}`;
  }
  function failedScreening(q) {
    return q.failed_checks.map((k) =>
      `${k === "prompt_adherence" ? "Prompt adherence" : CHECK_LABEL[k] || k}: ${q.scores[k]?.toFixed(2) ?? "unavailable"} / ${q.thresholds[k] ?? "unavailable"} threshold`).join("; ");
  }

  function readiness(clip) {
    if (!hrAvailable()) {
      return {
        level: "unavailable", title: "Human-review evidence unavailable.",
        text: "The review record could not be loaded, so open publication blockers can't be shown. Treat this clip as not approved.",
      };
    }
    if (clip.withheld_reason) {
      return { level: "withheld", title: "Rejected / unselected evidence only.", text: clip.withheld_reason };
    }
    if (clip.demo_disposition) {
      const d = clip.demo_disposition;
      return {
        level: d.status === "replacement_required" ? "replacement" : d.status === "demo_variance" ? "variance" : "demo",
        title: d.status === "replacement_required" ? "Current demo: replacement required." : "Current fictional-demo disposition.",
        text: `${d.summary} ${d.limitation ? `${d.limitation} ` : ""}Not approved for customer-campaign publication.`,
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
    replacement: ["fail", "Replacement required"], variance: ["warn", "Demo-specific variance"],
    demo: ["", "Retained for fictional demo only"],
    withheld: ["fail", "Withheld; not an approval backlog"],
  };
  function readinessPill(clip) {
    const r = readiness(clip);
    const [cls, label] = READINESS_PILL[r.level];
    return h("span", { class: `pill ${cls}`, "data-readiness": r.level, title: `${r.title} ${r.text}` }, label);
  }

  function video(clip, opts = {}) {
    const el = h("video", {
      src: clip.file, controls: true, playsinline: true, preload: "metadata", loop: opts.loop,
      poster: opts.poster,
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
    if (c.presentation) {
      // The disclosure already names the variant in its first sentence; emphasise it rather than repeating a label.
      const [lead, ...rest] = c.presentation.audio_disclosure.split(/(?<=\.) /);
      return h("p", { class: "audio-note none" }, h("b", {}, lead), rest.length ? ` ${rest.join(" ")}` : "",
        " ", h("a", { href: c.original_file }, "Native original retained"));
    }
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
  // Citations and separately opened recordings use a new browsing context, say so visibly, and drop the opener.
  const ext = (href, label) => h("a", { href, target: "_blank", rel: "noopener noreferrer", class: "ext" },
    label, h("span", { class: "ext-note" }, " (opens in new tab)"));
  const citations = (sources) => sources.flatMap((s, i) => [i ? " · " : null, ext(s.url, `${s.publisher} (${s.published})`)]);

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
  // Hash-routed views: Home, guided demo, scenario gallery, technical evidence and About are shown one at a
  // time. Evidence deep links (#routing, #qa, #evals) open the evidence view with that section expanded. Players in
  // a view that is being hidden are paused (one player at a time), so no invisible audio keeps going.
  const VIEWS = { home: "#view-home", guide: "#guide", scenarios: "#scenarios", evidence: "#evidence", about: "#about" };
  const VIEW_HEADINGS = { home: "#hero-title", guide: "#guide-heading", scenarios: "#scenarios-heading", evidence: "#evidence-heading", about: "#about-heading" };
  const VIEW_ALIASES = { "": "home", top: "home", "about-demo": "about", routing: "evidence", qa: "evidence", evals: "evidence" };
  let currentView = null;
  let routeGuide = () => {};
  let routeGallery = () => {};
  let setEvidenceClip = () => {};
  let galleryReturn = null;
  window.history.scrollRestoration = "manual";
  function viewFor(id) {
    if (id.startsWith("guide/")) return "guide";
    if (id.startsWith("scenarios/")) return "scenarios";
    if (id === "main") return currentView || "home";
    if (VIEWS[id]) return id;
    if (id in VIEW_ALIASES) return VIEW_ALIASES[id];
    const el = typeof document.getElementById === "function" ? document.getElementById(id) : null;
    const host = el && typeof el.closest === "function" ? el.closest("[data-view]") : null;
    return host && VIEWS[host.dataset.view] ? host.dataset.view : "home";
  }
  function showView(id, focus, startGuide = false) {
    const name = viewFor(id);
    const changed = name !== currentView;
    if (changed && currentView === "scenarios") galleryReturn = { y: window.scrollY, focus: document.activeElement };
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
    if (id === "guide" || id.startsWith("guide/")) routeGuide(id.split("/")[1] || "qsr", id.split("/")[2], startGuide);
    if (name === "scenarios") routeGallery(id.split("/")[1]);
    openDetails(id);
    const target = id && typeof document.getElementById === "function" ? document.getElementById(id) : null;
    if (target && target.tagName === "DETAILS") {
      if (typeof target.scrollIntoView === "function") target.scrollIntoView();
    } else if (focus && (changed || name === "home")) {
      if (name === "scenarios" && galleryReturn) {
        galleryReturn.focus?.focus({ preventScroll: true });
        window.scrollTo({ top: galleryReturn.y, behavior: "instant" });
        return;
      }
      const heading = $(VIEW_HEADINGS[name]);
      if (heading) heading.focus({ preventScroll: true });
      if (typeof window.scrollTo === "function") window.scrollTo(0, 0);
    }
  }
  const hashId = () => decodeURIComponent(window.location.hash.slice(1));
  function navigateTo(id) {
    window.history.pushState(null, "", `#${id}`);
    setMenu(false);
    showView(id, true, true);
  }
  document.addEventListener("click", (e) => {
    const a = e.target && typeof e.target.closest === "function" ? e.target.closest('a[href^="#"]') : null;
    if (!a) return;
    e.preventDefault();
    navigateTo(decodeURIComponent(a.getAttribute("href").slice(1)));
  });
  // Traversal emits both events before Chromium finishes fragment scrolling and focus restoration.
  // Route once on the next frame, so the gallery's saved position and focus are applied last.
  let historyPending = false;
  function routeHistory() {
    if (historyPending) return;
    historyPending = true;
    requestAnimationFrame(() => {
      historyPending = false;
      showView(hashId(), true);
    });
  }
  window.addEventListener("hashchange", routeHistory);
  window.addEventListener("popstate", routeHistory);
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
  overview.addEventListener("close", () => { overviewVideo.pause(); $("#watch-overview").focus({ preventScroll: true }); });
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
    DISPOSITIONS = data.demo_dispositions;
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
    initReadinessSummary(data, clips);
    const routeCalculator = initRouting(data);
    initEvidence(data, clips, products, routeCalculator);
    initLanding(data, clips, products);
    routeGallery = initScenarios(data, clips);
    if (viewFor(hashId()) === "scenarios") routeGallery(hashId().split("/")[1]);
    initEntry(data, clips, products);
    routeGuide = initGuide(data, clips, products);
    if (viewFor(hashId()) === "guide") routeGuide(hashId().split("/")[1] || "qsr", hashId().split("/")[2]);
    $("#fictional-brands").textContent = `Fictional retail examples: ${data.accounts.map((a) => a.fictional_brand).join(", ")}.`;
    $("#public-sources").replaceChildren(...data.accounts.map((a) => h("p", {},
      h("b", {}, `${a.fictional_brand}. `), `Inspired by publicly reported priorities of ${a.real_company}. `, citations(a.sources))));
    $("#sound").addEventListener("change", () => setSound(soundOn()));
    // Evidence sections fill in after the data loads, so land a deep link (#qa, #evals) again once they have.
    const deep = hashId() && typeof document.getElementById === "function" ? document.getElementById(hashId()) : null;
    if (deep && deep.tagName === "DETAILS" && typeof deep.scrollIntoView === "function") deep.scrollIntoView({ behavior: "instant" });
  }

  // ---------- landing ----------
  function initLanding(data, clips, products) {
    const hero = clips[data.lto.hero_clip];
    const p = products[data.lto.sku];
    const player = video(hero, { label: p.name, title: "hero video", poster: `posters/${hero.id}.jpg` });
    const button = h("button", { id: "hero-play", type: "button", class: "hero-play", onclick: () => {
      if (player.paused) playSafely(player, "#hero-status"); else player.pause();
    } }, `▶ Play ${hero.requested_duration_s}-second example`);
    for (const event of ["play", "pause", "ended"]) player.addEventListener(event, () => {
      button.textContent = player.paused ? `▶ Play ${hero.requested_duration_s}-second example` : "Pause short example";
    });
    $("#hero-compare").replaceChildren(
      h("div", { class: "compare-pair" },
        h("figure", {}, h("img", { src: p.image, alt: `Approved product image: ${p.name}` }), h("figcaption", {}, "Product image")),
        h("span", { class: "arrow", "aria-hidden": "true" }, "→"),
        h("figure", { class: "vertical hero-recording" }, player, button,
          h("figcaption", {}, `Recorded video · ${hero.model_name}`))),
      h("p", { id: "hero-status", class: "issue", role: "alert", hidden: true }),
      ...heroDisposition(hero));
  }

  // One concise visible statement; the transformation, the native source's finding and retained visual caveats
  // stay available in a disclosure rather than as competing boxes.
  function heroDisposition(hero) {
    if (!hero.presentation) return [audioNote(hero), readinessBox(hero)];
    const why = hero.presentation.audio_disclosure.split(/(?<=\.) /).slice(1).join(" ");
    return [h("div", { class: "hero-disposition", role: "note", "data-readiness": readiness(hero).level },
      h("p", { class: "hero-statement" }, h("b", {}, "Silent fictional-demo presentation."),
        " Original model audio was removed; this is not customer-campaign approval."),
      hrAvailable() ? null : readinessBox(hero),
      h("details", { class: "inspect source-history" }, h("summary", {}, "Source history and limitations"),
        h("p", {}, h("b", {}, "Transformation. "), hero.presentation.transformation),
        why ? h("p", {}, h("b", {}, "Why audio was removed. "), why) : null,
        ...findingsFor(hero.parent_clip).filter(isBlocker).map((f) => h("p", {},
          h("b", {}, "Historical finding on the native original. "), f.observation,
          " It applies to the retained native file, not to this silent presentation.")),
        hero.demo_disposition?.limitation ? h("p", {}, h("b", {}, "Retained visual caveat. "), hero.demo_disposition.limitation) : null,
        h("p", {}, h("b", {}, "Review scope. "), hero.presentation.review),
        h("p", {}, h("a", { href: hero.original_file }, "Native original retained"), " as historical evidence.")))];
  }

  function initEntry(data, clips, products) {
    $("#entry-grid").replaceChildren(...data.scenarios.map((s) => {
      const c = clips[s.clips[0]];
      const img = c.source_image || products[c.sku].image;
      const dest = `scenarios/${s.guide}`;
      return h("a", { class: "entry-card card", href: `#${dest}` },
        h("span", { class: "entry-title" }, s.label || s.title),
        img ? h("img", { src: img, alt: "" }) : null,
        h("span", { class: "hint" }, s.story || s.use_case));
    }));
  }

  const EXAMPLE_SUMMARY = {
    northwind: "Turn a seasonal cold-brew offer into a short social concept.",
    tailspin: "Introduce a value meal with a warm, appetizing social preview.",
    coho: "Spotlight a toasted sandwich for an evening convenience-store offer.",
    fabrikam: "Bring a quilted jacket's texture and shape to a product-page lookbook.",
    vanarsdel: "Invite discovery of tactile home accessories in a short social vignette.",
    tailwind: "Explore a refreshed home-decor endcap in daylight.",
    "wide-world": "Present warehouse essentials together on a flatbed cart.",
    alpine: "Explore a cordless drill in a job-site product demonstration.",
    zava: "Preview a teak dining set in a relaxed patio setting.",
    southridge: "Explore a laptop and accessories in a compact home-office concept.",
    proseware: "Explore a small-office product bundle in a naturally lit workspace.",
    woodgrove: "Introduce a seasonal wellness bundle without medical or efficacy claims.",
    "best-for-you": "Present a vegetarian meal kit for a seasonal grocery promotion.",
    munson: "Showcase neighborhood-grocery staples in a simple shopping basket.",
  };
  const formatOf = (c) => `${Number(c.media_duration_s.toFixed(1))} sec · ${
    c.aspect_ratio === "9:16" ? "Vertical social" : c.aspect_ratio === "1:1" ? "Square product page" : "Landscape"}`;
  function compactReadiness(c) {
    const r = readiness(c);
    return h("div", { class: `card-readiness ${r.level}`, "data-readiness": r.level },
      h("span", {}, READINESS_PILL[r.level][1]),
      r.level === "blocked" ? h("span", {}, c.id === "lto-hero-kling"
        ? "Loud ambience; frothing sound mismatches the picture." : r.text) : null,
      r.level === "decision" && decisionReason(r) ? h("span", {}, decisionReason(r)) : null);
  }
  function accountBrief(a) {
    return inspect("Brief and public sources",
      h("blockquote", {}, a.brief),
      h("p", { class: "sources" }, `Inspired by publicly reported priorities of ${a.real_company}. `, citations(a.sources)),
      h("p", {}, a.need),
      kv([["Channel", `${a.channel} · ${a.aspect_ratio}`], ["Routed model", a.model_name], ["Why", a.why],
        ["Estimate", `${usd(a.estimate_usd)}; list-price estimate, not a bill`]]));
  }
  function accountCard(a, clips, onPreview) {
    const recorded = a.recorded_clip && clips[a.recorded_clip];
    const learningCase = a.curation === "learning";
    return h("article", { class: `card account-card${learningCase ? " learning-card" : ""}`, "data-account": a.id },
      h("button", { type: "button", class: "poster-preview", "aria-label": `Preview ${a.fictional_brand}${learningCase ? " learning case" : ""}`,
        onclick: (e) => onPreview(a, e.currentTarget || e.target) },
        h("img", { src: `posters/${recorded.id}.jpg`, alt: "", loading: "lazy", width: "320", height: "180" }),
        h("span", {}, "▶ Preview")),
      h("h3", {}, a.fictional_brand),
      h("p", { class: "example-summary" }, recorded.demo_disposition?.creative_summary || EXAMPLE_SUMMARY[a.id]),
      h("p", { class: "format" }, formatOf(recorded)),
      compactReadiness(recorded),
      learningCase ? h("p", { class: "learning-defect" }, h("b", {}, "Known limitation: "), a.learning_defect) : null,
      learningCase
        ? h("a", { class: "button ghost", href: `#guide/${a.area}/${a.id}` }, "Inspect learning case")
        : h("a", { class: "button ghost", href: `#guide/${a.area}/${a.id}` }, "Open guided demo"));
  }
  // Learning cases keep their identity and deep links, and always say why they are not featured.
  // The defect is named once: omit it here when the adjacent readiness note already states it.
  function learningNotice(a, shownWith) {
    if (a.curation !== "learning") return null;
    const named = Boolean(shownWith && shownWith.includes(a.learning_defect));
    return h("p", { class: "learning-notice", role: "note" },
      h("b", {}, "Learning case — not a featured presentation. "),
      ...(named ? ["Retained to show what review caught; the replacement-required defect still needs future remediation."]
        : ["Unresolved defect: ", a.learning_defect, " Retained to show what review caught; future remediation is required."]));
  }

  // Safe attempts that failed automated screening, shown only to explain what the QA gate caught.
  const learningOf = (a, clips) => (a.learning_clips || []).map((e) => clips[e.id]).filter((c) => c && c.file);
  const LEARNING_LABEL = "QA learning example — failed screening; not approved";

  // ---------- one example at a time; scroll/focus changes only on explicit navigation ----------
  function initGuide(data, clips, products) {
    const lto = data.lto;
    const needs = {
      northwind: "Promote a seasonal pumpkin cold brew with a short vertical social ad.",
      tailspin: "Promote an everyday meal bundle through value-focused digital offers.",
      coho: "Make fresh grab-and-go food easy to discover during an evening convenience stop.",
      fabrikam: "Help online shoppers inspect a jacket beyond a static catalog photo.",
      vanarsdel: "Encourage discovery as a value retailer's home and accessories assortment changes.",
      tailwind: "Bring new home-decor arrivals to in-store screens and retail-media placements.",
      "wide-world": "Support member discovery of bulk essentials through digital shopping and retail media.",
      alpine: "Help professional contractors assess a tool before choosing it.",
      zava: "Help shoppers picture a coordinated outdoor dining purchase.",
      southridge: "Give technology shoppers richer product content for a home-office purchase.",
      proseware: "Help small businesses evaluate a practical workplace-supplies bundle.",
      woodgrove: "Make seasonal self-care essentials easier to find in store, without health claims.",
      "best-for-you": "Promote convenient owned-brand meal solutions through weekly offers.",
      munson: "Make localized weekly offers relevant to neighborhood grocery shoppers.",
    };
    const summaries = {
      northwind: "The approved Northwind cold-brew cup on a cream backdrop as maple leaves drift past and a pale cream pour settles on the foam.",
      tailspin: "A value meal on a wooden counter: burger, fries and drink, warm light and gentle steam.",
      coho: "A toasted sandwich and a plain takeaway bag, framed as a warm evening food moment.",
      fabrikam: "Explore the jacket's quilting, collar and fabric movement in a studio lookbook.",
      vanarsdel: "A tactile discovery of home accessories, from ceramic vase to knit throw and tote.",
      tailwind: "A daylight tour of lamps, pillows and a woven basket in a refreshed home-decor endcap.",
      "wide-world": "Warehouse essentials on a flatbed cart, with plain multipack packaging.",
      alpine: "Put the approved cordless drill into a sunlit job-site scene.",
      zava: "A text-led patio layout: one teak table and four chairs at dusk.",
      southridge: "A laptop and accessories in a studio desk scene; inspect the recorded layout caveat.",
      proseware: "A stationary office kit in natural light: coffee, cleaning supplies, task chair and printer paper.",
      woodgrove: "A camera push toward the wellness bundle gradually crops products; pharmacy-endcap context is not established.",
      "best-for-you": "A playful vegetarian meal-kit arrangement under warm holiday light.",
      munson: "A bakery loaf, pasta and olive oil in a simple neighborhood-grocery basket.",
    };
    let account = data.accounts.find((a) => a.curation === "featured") || data.accounts[0];
    const state = { step: 0, selected: null, preview: null };
    const result = () => clips[account.hero_clip || account.recorded_clip];
    const concepts = () => account.draft_clips.filter((id) => id !== result()?.id)
      .map((id) => clips[id]).filter((c) => c?.file && !c.withheld_reason);
    const steps = () => ["brief", ...(concepts().length ? ["concepts"] : []), "result", "review"];
    const titles = { brief: "Brief", concepts: "Concepts", result: "Recorded result", review: "Review" };
    const needsSelection = () => concepts().length > 0 && !!account.hero_clip;
    const eligible = (c) => account.id === "northwind" && c.variant === lto.hero_variant && !!result()?.source_image;
    const canEnter = (i) => !needsSelection() || !["result", "review"].includes(steps()[i]) || state.selected !== null;
    let player = null;
    let selectButton = null;
    const stage = $("#guide-stage");
    const prev = $("#guide-prev"), next = $("#guide-next"), play = $("#guide-play");
    const full = $("#guide-full"), wrap = $("#guide-wrap");
    const playback = $("#guide-playback"), chooser = $("#guide-example");
    const areaNames = { qsr: "QSR", apparel: "Apparel", home: "Home improvement", grocery: "Grocery/pharmacy" };
    const byCuration = (learning) => data.accounts.filter((a) => (a.curation === "learning") === learning);
    chooser.replaceChildren(...[["Featured presentations", false], ["Learning cases", true]].map(([label, learning]) =>
      h("optgroup", { label }, byCuration(learning).map((a) => h("option", { value: a.id },
        `${areaNames[a.area]} / ${a.fictional_brand}`)))));
    chooser.addEventListener("change", () => {
      const a = data.accounts.find((item) => item.id === chooser.value);
      if (a) navigateTo(`guide/${a.area}/${a.id}`);
    });
    function updateControls() {
      prev.disabled = state.step === 0;
      next.disabled = !canEnter(state.step + 1);
      next.textContent = state.step === steps().length - 1 ? "Gallery →" : "Next →";
      next.setAttribute("aria-label", state.step === steps().length - 1 ? "Explore examples in Scenario gallery"
        : `Next: ${titles[steps()[state.step + 1]]}`);
      const verb = player && !player.paused ? "Pause" : "Play";
      play.disabled = !player;
      play.textContent = verb;
      play.setAttribute("aria-label", player ? `${verb} ${player.dataset.title}` : "No video in this step");
      $("#guide-clip").textContent = !player ? "" : player.error ? "Clip failed to load"
        : player.readyState >= 1 ? "Recorded clip" : "Loading clip…";
      const active = player && clips[player.dataset.clip];
      $("#sound").disabled = !active?.has_audio;
      $("#sound-label").textContent = active?.has_audio ? "Sound" : "Sound unavailable";
      $("#guide-next-hint").hidden = !next.disabled;
      $("#guide-next-hint").textContent = next.disabled ? `Select concept #${lto.hero_variant} to continue to the recorded result.` : "";
    }
    onPlayState = updateControls;
    function evidence(c) {
      return inspect("Inspect evidence: screening, evaluations and full prompt",
        verdictPill(c.qa.verdict),
        h("p", {}, c.qa.findings.join(" ")),
        EV ? (evalPill(evalCheck(c.id, "product_identity"), "AI eval · identity")
          || h("p", {}, "Not yet evaluated in Foundry Evaluations."))
          : h("p", { class: "issue" }, "Evaluation evidence unavailable."),
        audioNote(c), audioMetrics(c),
        kv([["Model", `${c.model_name} · ${c.mode} · ${c.aspect_ratio}`], ["Estimate", usd(c.estimate_usd)],
          ["Recorded generation time", secs(c.accepted_to_completed_s)],
          ["Request ID", h("span", { class: "mono" }, c.request_id)]]),
        h("blockquote", {}, c.prompt));
    }
    function history() {
      const earlier = learningOf(account, clips);
      const attempts = (DISPOSITIONS?.replacement_attempts || []).filter(r => r.account === account.id);
      return earlier.length || account.excluded_clips?.length || attempts.length ? inspect("QA learning examples and withheld attempts",
        attempts.map(r => h("p", {}, h("b", {}, "Targeted release attempt: "), r.disposition, " ",
          h("a", { href: "#qa", onclick: () => setEvidenceClip(r.clip) }, "Inspect this unselected attempt"))),
        earlier.map((c) => inspect(`${c.id} — failed screening; not approved`,
          h("p", {}, c.learning_note), evidence(c),
          ext(c.file, "Open this earlier recording separately"))),
        (account.excluded_clips || []).map((c) => h("p", {}, h("b", {}, `${c.id}: `), c.reason,
          " Media withheld; recorded evidence remains in ", h("a", { href: "#qa" }, "Technical evidence"), "."))) : null;
    }
    function select(c) {
      if (!eligible(c)) return;
      state.selected = c.id;
      selectButton.setAttribute("aria-pressed", "true");
      selectButton.textContent = `Concept #${c.variant} selected`;
      selectButton.classList.add("ghost");
      $("#guide-status").textContent = `Concept #${c.variant} selected. Next opens its recorded result.`;
      updateControls();
    }
    function brief(c) {
      const p = products[account.sku], image = c.source_image || p.image;
      return h("div", { class: "brief-layout" },
        image ? h("figure", {}, h("img", { src: image, alt: `Product reference: ${p.name}` }),
          h("figcaption", {}, "Approved product reference"))
          : h("div", { class: "text-product" }, h("span", { class: "eyebrow" }, "Text-led example"),
            h("p", {}, "No approved product image was used.")),
        h("div", { class: "brief-copy" }, h("h3", {}, p.name), learningNotice(account, readiness(c).text), h("p", { class: "business-need" }, needs[account.id]),
          h("p", { class: "creative-summary" }, c.demo_disposition?.creative_summary || summaries[account.id]),
          h("p", { class: "hint" }, `${account.channel} · ${account.aspect_ratio} · ` +
            (concepts().length ? "Three drafts → explicit choice → recorded result"
              : account.hero_clip ? "One recorded PIM result; no separate drafts" : "One preview-only recording; no PIM hero")),
          inspect("Brief details: prompt, public sources, routing and estimate",
            h("blockquote", {}, account.brief),
            h("p", {}, `Inspired by publicly reported priorities of ${account.real_company}. ${account.need}`),
            account.sources.map((s) => h("p", { class: "sources" }, ext(s.url, `${s.publisher} (${s.published})`))),
            kv([["Model", account.model_name], ["Why", account.why], ["Estimate", `${usd(account.estimate_usd)}; list price, not a bill`]]),
            h("p", {}, "Fictional brands and products. Real names cite public sources only; no affiliation, endorsement, trademarks or customer data.")),
          history()));
    }
    function media(c, key) {
      if (!c?.file || c.withheld_reason) return h("p", { class: "issue" }, "Recording unavailable or withheld — not approved.");
      player = video(c, { title: key === "concepts" ? `concept #${c.variant} preview` : `${account.fictional_brand} recorded result`,
        poster: `posters/${c.id}.jpg` });
      player.addEventListener("loadedmetadata", updateControls);
      player.addEventListener("error", updateControls);
      const isConcept = key === "concepts";
      const strip = isConcept ? h("div", { class: "concept-strip", role: "group", "aria-label": "Preview a concept (does not select)" },
        concepts().map((draft) => h("button", {
          type: "button", class: "ghost concept-thumb", "data-concept": draft.id,
          "aria-pressed": String(draft.id === c.id), onclick: () => preview(draft.id),
        }, h("img", { src: `posters/${draft.id}.png`, alt: "", width: "90", height: "160" }),
        h("span", {}, `#${draft.variant} · ${draft.concept}`, h("small", {},
          eligible(draft) ? "Recorded result available" : "Preview only"))))) : null;
      selectButton = isConcept && eligible(c) ? h("button", {
        type: "button", class: `select${state.selected ? " ghost" : ""}`, "aria-pressed": String(state.selected === c.id),
        onclick: () => select(c),
      }, state.selected === c.id ? `Concept #${c.variant} selected` : `Select concept #${c.variant} for recorded result`) : null;
      const source = !isConcept && c.source_image ? h("figure", { class: "result-reference" },
        h("img", { src: c.source_image, alt: `Approved product reference: ${products[c.sku].name}` }),
        h("figcaption", {}, "Source image")) : null;
      if (key === "review") {
        const r = readiness(c);
        const guidance = c.demo_disposition?.guidance || (account.id === "northwind"
          ? "Review and resolve the audio/picture mismatch before sign-off. Lowering playback volume alone does not resolve it."
          : account.id === "southridge"
            ? "Verify laptop/accessory placement against the brief before sign-off."
            : decisionReason(r) ? `${decisionReason(r)} Review the full recording and reconcile the evidence before sign-off.`
              : c.qa.failed_checks.length
                ? "Review the full recording against the product reference and brand rules; resolve the failed checks before sign-off."
                : "Review the full video for product identity, lettering, motion and any audio before human sign-off.");
        return h("div", { class: "review-layout" },
          h("div", { class: "player-column" }, playback, player),
          h("div", { class: "review-copy" },
            h("div", { class: "review-summary" },
              h("section", {}, h("h3", {}, c.source_qa_clip ? "Historical source screening" : "Recorded screening"), verdictPill(c.qa.verdict),
                h("p", {}, c.qa.failed_checks.length ? failedScreening(c.qa)
                  : "Sampled frames passed the recorded checks; this is not full-video approval.")),
              h("section", {}, h("h3", {}, "Current fictional-demo disposition"),
                r.title === "Current fictional-demo disposition." ? null : h("p", {}, r.title),
                c.demo_disposition ? h("p", {}, c.demo_disposition.summary) : null,
                account.curation === "learning" ? h("p", {}, h("b", {}, "Learning case: "),
                  c.demo_disposition?.summary === account.learning_defect
                    ? "not a featured presentation; retained to show what review caught." : account.learning_defect) : null),
              h("section", { class: "campaign-approval" }, h("h3", {}, "Customer-campaign approval"),
                h("p", {}, hrAvailable() ? "Not approved. No publication approval is granted by this page." : r.text)),
              h("section", { class: "review-guidance" }, h("h3", {}, "What needs checking next"),
                h("p", {}, h("b", {}, "Review guidance: "), guidance))),
            evidence(c),
            inspect("Full review findings and resolution options",
              findingsFor(c.id).map((f) => {
                const decision = (DISPOSITIONS?.adjudications || []).find(a => a.id === f.id);
                return h("div", {}, h("p", {}, `Historical source finding: ${f.observation}`),
                  decision ? h("p", {}, "Versioned adjudication: ", decision.decision, " ", decision.scope)
                    : f.resolution_options ? h("ul", {}, f.resolution_options.map((t) => h("li", {}, t))) : null);
              }),
              account.review_note ? h("p", {}, account.review_note) : null,
              h("a", { href: "#evidence" }, "Inspect technical evidence for this recording")),
            history()));
      }
      return h("div", { class: `media-layout ${isConcept ? "concepts-layout " : ""}${c.aspect_ratio === "9:16" ? "portrait" : c.aspect_ratio === "1:1" ? "square" : "landscape"}` },
        h("div", { class: "player-column" }, playback, h("div", { class: "result-picture" }, source, player)),
        isConcept ? h("div", { class: "concept-controls" }, strip, selectButton) : null,
        h("div", { class: "media-context" }, h("h3", {}, isConcept ? `Concept #${c.variant} · ${c.concept}`
          : account.hero_clip ? "Recorded image-to-video result" : "Recorded preview — no PIM hero"),
          h("p", { class: "takeaway" }, isConcept
            ? (eligible(c) ? "Watching is not selecting. Choose this concept explicitly to unlock its recorded result."
              : `Preview only. Use concept #${lto.hero_variant} for the available recorded result.`)
            : c.demo_disposition?.creative_summary || summaries[account.id]),
          h("p", { class: "audio-caveat" }, c.has_audio
            ? PRESENTATION_VOLUME[c.id] ? "Native audio · played at 50% volume; mismatch remains unresolved."
              : String(c.audio || "").startsWith("native") ? "Native model audio · human listening review required."
                : "Unrequested model audio · not reviewed for meaning."
            : c.presentation ? c.presentation.audio_disclosure
              : c.presentation_audio_removed ? "Silent presentation edit · unexpected model audio removed." : "No audio track · the Sound control cannot add one."),
          evidence(c),
          account.review_note ? inspect("Recorded visual-review caveats", h("p", {}, account.review_note)) : null,
          history()));
    }
    function focusStart() {
      $("#guide-heading").focus({ preventScroll: true });
      if (document.fullscreenElement === wrap) wrap.scrollTo({ top: 0, behavior: "instant" });
      else wrap.scrollIntoView({ block: "start", behavior: "instant" });
    }
    function preview(id) {
      state.preview = id;
      render(false);
      stage.querySelectorAll("button.concept-thumb").forEach((b) => {
        if (b.dataset.concept === id) b.focus({ preventScroll: true });
      });
    }
    function render(focus = false) {
      pausePlayers();
      player = null;
      playback.hidden = true;
      wrap.append(playback); // retain the controls and handlers when replacing a step
      const key = steps()[state.step], c = key === "concepts" ? clips[state.preview] : result();
      wrap.setAttribute("data-step", key);
      stage.setAttribute("data-account", account.id);
      stage.replaceChildren(key === "brief" ? brief(c) : media(c, key));
      playback.hidden = !player;
      chooser.value = account.id;
      $("#guide-full-example").textContent = account.fictional_brand;
      $("#guide-heading").textContent = `${state.step + 1} / ${steps().length} · ${titles[key]}`;
      $("#guide-status").textContent = `${account.fictional_brand}. Step ${state.step + 1} of ${steps().length}: ${titles[key]}`;
      $("#guide-readiness").replaceChildren(readinessBox(c));
      setEvidenceClip(c.id);
      updateControls();
      if (focus) focusStart();
    }
    function go(i) {
      if (i < 0 || i >= steps().length || i === state.step || !canEnter(i)) return;
      state.step = i;
      $("#guide-options").open = false;
      render(true);
    }
    function changeAccount(a, focus) {
      account = a;
      state.step = 0;
      state.selected = null;
      state.preview = concepts()[0]?.id || result()?.id;
      $("#guide-options").open = false;
      render(focus);
    }
    prev.addEventListener("click", () => go(state.step - 1));
    next.addEventListener("click", () => {
      if (state.step === steps().length - 1) navigateTo("scenarios");
      else go(state.step + 1);
    });
    play.addEventListener("click", () => { if (player) togglePlay(player); });
    $("#guide-restart").addEventListener("click", () => changeAccount(account, true));
    wrap.addEventListener("keydown", (e) => {
      if (e.target?.classList?.contains("concept-thumb")) {
        const choices = concepts(), i = choices.findIndex((c) => c.id === state.preview);
        const at = { ArrowRight: (i + 1) % choices.length, ArrowLeft: (i + choices.length - 1) % choices.length,
          Home: 0, End: choices.length - 1 }[e.key];
        if (at !== undefined) { e.preventDefault(); preview(choices[at].id); }
        return;
      }
      const tag = e.target && e.target.tagName;
      if (["VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "SUMMARY", "A"].includes(tag)) return;
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
      $("#guide-options").open = false;
      focusStart();
    });

    // Options is a disclosure whose panel is absolutely positioned, so opening it never moves the story.
    // Escape closes it and returns focus to its toggle; clicking or tabbing outside, or choosing an item, closes it.
    const options = $("#guide-options"), optionsToggle = $("#guide-options-toggle");
    const inOptions = (el) => !!el && typeof options.contains === "function" && options.contains(el);
    const closeOptions = (refocus) => {
      if (!options.open) return;
      options.open = false;
      if (refocus) optionsToggle.focus();
    };
    options.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !options.open) return;
      e.preventDefault();
      closeOptions(true);
    });
    options.addEventListener("focusout", (e) => { if (e.relatedTarget && !inOptions(e.relatedTarget)) closeOptions(false); });
    document.addEventListener("click", (e) => { if (options.open && e.target && !inOptions(e.target)) closeOptions(false); });
    // Actions inside the panel close it; Restart and view changes move focus to their own start point.
    for (const sel of ["#guide-restart", "#guide-gallery"]) $(sel).addEventListener("click", () => closeOptions(false));
    changeAccount(account, false);
    return (area, id, restart = false) => {
      // Area shortcuts and unknown ids always land on a featured presentation, never a learning case.
      const a = data.accounts.find((a) => a.area === area && a.id === id)
        || data.accounts.find((a) => a.area === area && a.curation === "featured")
        || data.accounts.find((a) => a.curation === "featured") || data.accounts[0];
      if (restart || a.id !== account.id) changeAccount(a, true);
    };
  }

  // ---------- scenario gallery ----------
  function initScenarios(data, clips) {
    const tabs = $("#scenario-tabs");
    const panel = $("#scenario-panel");
    const category = $("#scenario-category");
    const dialog = $("#scenario-preview");
    const body = $("#preview-body");
    let opener = null, previewPlayer = null;
    function closePreview() {
      previewPlayer?.pause();
      body.replaceChildren();
      previewPlayer = null;
      opener?.focus({ preventScroll: true });
    }
    dialog.addEventListener("close", closePreview);
    $("#preview-close").addEventListener("click", () => {
      if (typeof dialog.close === "function") dialog.close();
      else { dialog.removeAttribute("open"); closePreview(); }
    });
    function preview(a, from) {
      opener = from;
      const selected = clips[a.recorded_clip];
      const alternatives = data.clips.filter((c) => c.id !== selected.id &&
        (c.account === a.id || a.draft_clips.includes(c.id) || c.id === selected.parent_clip));
      function showRecording(c, focus = false) {
        if (!c.file || c.withheld_reason) {
          showIssue("#preview-status", "Recording unavailable or withheld — not approved.");
          return;
        }
        previewPlayer?.pause();
        setEvidenceClip(c.id);
        const kind = c.id === selected.id ? c.presentation ? "Selected silent presentation"
          : a.curation === "learning" ? "Learning case recording" : "Selected example"
          : c.id === selected.parent_clip ? "Native original — historical evidence"
            : a.draft_clips.includes(c.id) ? "Alternative concept" : "Earlier attempt";
        $("#preview-title").textContent = `${a.fictional_brand} · ${kind}`;
        previewPlayer = video(c, { title: a.fictional_brand,
          poster: c.id === selected.id || a.draft_clips.includes(c.id) ? `posters/${c.id}.jpg` : null });
        body.replaceChildren(
          h("div", { class: "preview-layout" },
            h("div", { class: "preview-media" },
              h("h3", { class: "preview-recording-name" }, `${kind} · ${c.concept || c.id}`), previewPlayer),
            h("div", { class: "preview-copy" },
              learningNotice(a, readiness(c).text),
              h("p", {}, c.demo_disposition?.creative_summary || EXAMPLE_SUMMARY[a.id]),
              h("p", { class: "format" }, formatOf(c)),
              c.id !== selected.id ? h("p", { class: "hint" }, a.draft_clips.includes(c.id)
                ? "Alternative draft concept — previewing does not select it." : "Earlier attempt — not the selected example.") : null,
              readinessBox(c), audioNote(c),
              h("p", { class: "hint" }, "Recorded Foundry replay; no live generation. fal preview models process data outside Microsoft facilities."),
              h("a", { class: "button", href: `#guide/${a.area}/${a.id}`,
                onclick: () => { if (typeof dialog.close === "function") dialog.close(); else closePreview(); } },
                a.curation === "learning" ? "Inspect learning case" : "Open guided demo"),
              accountBrief(a),
              inspect("Technical evidence",
                verdictPill(c.qa.verdict), h("p", {}, c.qa.findings.join(" ")),
                c.id === selected.id && a.review_note ? h("p", {}, a.review_note) : null,
                EV ? h("p", {}, EV.media[c.id] ? "Recorded AI evaluations available." : "Not yet evaluated in Foundry Evaluations.")
                  : h("p", { class: "issue" }, "Evaluation evidence unavailable."),
                h("blockquote", {}, c.prompt),
                kv([["Model", c.model_name], ["Request ID", h("span", { class: "mono" }, c.request_id)]]),
                h("a", { href: "#qa", onclick: () => { if (typeof dialog.close === "function") dialog.close(); else closePreview(); } }, "Read this recording's evidence")),
              inspect("Alternative recordings and history",
                c.id !== selected.id ? h("button", { class: "ghost", type: "button", onclick: () => showRecording(selected, true) }, "Return to selected recording") : null,
                alternatives.length ? alternatives.map((old) => h("div", { class: "history-item" },
                  h("p", {}, h("b", {}, old.id), " · ", old.withheld_reason ? "Withheld — media not published"
                    : old.concept || (old.qa.verdict === "fail" ? LEARNING_LABEL : "Earlier recording — human review required")),
                  h("p", {}, old.withheld_reason || old.learning_note || old.qa.findings.join(" ")),
                  old.file && !old.withheld_reason
                    ? h("button", { type: "button", class: "ghost", onclick: () => showRecording(old, true) }, "Preview this recording") : null))
                  : h("p", {}, "No alternative recordings on file.")))));
        if (focus) {
          dialog.scrollTo({ top: 0, behavior: "instant" });
          $("#preview-title").focus({ preventScroll: true });
          playSafely(previewPlayer, "#preview-status");
        }
      }
      showRecording(selected);
      if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
      playSafely(previewPlayer, "#preview-status");
    }
    let current = 0;
    const buttons = data.scenarios.map((s, i) => h("button", {
      type: "button", role: "tab", id: `tab-${s.vertical}`, "aria-controls": "scenario-panel",
      "aria-selected": "false", tabindex: "-1", onclick: () => select(i, false),
    }, s.label || s.title));
    tabs.replaceChildren(...buttons);
    category.replaceChildren(...data.scenarios.map((s, i) => h("option", { value: String(i) }, s.label || s.title)));
    category.addEventListener("change", () => select(Number(category.value), false));
    tabs.addEventListener("keydown", (e) => {
      const n = buttons.length;
      const target = { ArrowRight: (current + 1) % n, ArrowLeft: (current - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
      if (target === undefined) return;
      e.preventDefault();
      select(target, true);
    });

    function select(i, focus) {
      pausePlayers();
      current = i;
      category.value = String(i);
      galleryReturn = null;
      buttons.forEach((b, j) => {
        b.setAttribute("aria-selected", String(i === j));
        b.setAttribute("tabindex", i === j ? "0" : "-1");
      });
      panel.setAttribute("aria-labelledby", buttons[i].getAttribute("id"));
      if (focus) buttons[i].focus();
      const s = data.scenarios[i];
      const inArea = data.accounts.filter((a) => a.area === s.guide);
      const learning = inArea.filter((a) => a.curation === "learning");
      panel.replaceChildren(
        h("div", { class: "account-grid" }, inArea.filter((a) => a.curation !== "learning").map((a) => accountCard(a, clips, preview))),
        learning.length ? h("details", { class: "learning-cases", "data-area": s.guide },
          h("summary", {}, `Learning cases and known limitations (${learning.length})`),
          h("p", { class: "hint" }, "Original recordings retained to show what review caught. Each still needs a replacement; " +
            "they are not featured presentations, repaired examples or approvals."),
          h("div", { class: "account-grid" }, learning.map((a) => accountCard(a, clips, preview)))) : null);
    }
    const featuredCount = data.accounts.filter((a) => a.curation !== "learning").length;
    const featuredAreas = new Set(data.accounts.filter((a) => a.curation !== "learning").map((a) => a.area)).size;
    $("#scenario-coverage").textContent = `${featuredCount} featured presentations across ${featuredAreas} categories, ` +
      `with ${data.accounts.length - featuredCount} additional learning cases.`;
    select(0, false);
    return (area) => {
      const index = data.scenarios.findIndex((s) => s.guide === area);
      if (index >= 0 && index !== current) select(index, false);
    };
  }

  // ---------- readiness summary (always visible in the evidence section) ----------
  // Account coverage and attempts on file use different totals; say so once, beside the counts.
  function denominatorNote(data) {
    const all = data.clips.filter((c) => c.record_kind !== "presentation");
    const original = all.filter((c) => c.baseline_original).length;
    const derivatives = data.clips.length - all.length;
    return h("p", { class: "summary-note" }, h("b", {}, "Two different totals. "),
      `${data.accounts.length} is account coverage: one retained recording per fictional account ` +
      `(${data.accounts.filter((a) => a.curation !== "learning").length} featured presentations, ` +
      `${data.accounts.filter((a) => a.curation === "learning").length} learning cases). ` +
      `${all.length} counts every recorded clip and attempt on file (${original} original + ${all.length - original} account clips), ` +
      `including historical and withheld attempts, so it is not the number of selected examples. ${derivatives} presentation derivatives are not additional generations.`);
  }

  function initReadinessSummary(data, clips) {
    const all = data.clips.filter((c) => c.record_kind !== "presentation");
    const original = all.filter((c) => c.baseline_original);
    const pass = original.filter((c) => c.qa.verdict === "pass").length;
    const stat = (big, text) => h("div", { class: "stat" }, h("b", {}, big), text);
    const playable = data.accounts.filter((a) => a.recorded_clip && clips[a.recorded_clip] && clips[a.recorded_clip].file).length;
    const base = [
      stat(`${pass} of ${original.length}`, "original recorded clips passed automated screening"),
      stat(String(all.length), "recorded attempts retained as evidence, not a current approval backlog"),
      stat(`${all.filter((c) => c.withheld_reason).length} of ${all.length}`, "attempts withheld; evidence only, media not published"),
    ];
    const coverage = h("p", { class: "example-coverage" },
      h("b", {}, `${playable} of ${data.accounts.length} fictional accounts keep a playable recording.`),
      " Playable is not repaired: learning cases keep their original defects, and no example has customer-campaign approval.");
    const support = inspect("Supporting populations: original eight and all recorded attempts",
      h("div", { class: "qa-summary" }, base), denominatorNote(data));
    const box = $("#readiness-summary");
    if (!hrAvailable()) {
      box.replaceChildren(
        h("div", { class: "readiness unavailable", role: "note", "data-readiness": "unavailable" },
          h("b", {}, "Human-review evidence unavailable."),
          " Publication blockers and pending decisions can't be shown, so their count is unknown, not zero."),
        coverage, support);
      return;
    }
    const blockers = HR.findings.filter(isBlocker);
    const decisions = HR.findings.filter((f) => isOpen(f) && f.severity === "needs human decision");
    const currentActions = data.accounts.filter((a) => a.curation === "learning").map((a) => clips[a.recorded_clip]);
    const name = (id) => (clips[id] ? recordingName(data, clips[id]) : id);
    const featured = data.accounts.filter((a) => a.curation !== "learning");
    const attempts = DISPOSITIONS?.replacement_attempts || [];
    const chosen = attempts.filter((r) => data.accounts.some((a) => a.recorded_clip === r.clip)).length;
    box.replaceChildren(
      h("div", { class: "qa-summary readiness-counts" },
        stat(String(featured.length), "featured fictional-demo presentations; no customer-campaign approval"),
        stat(String(data.accounts.length - featured.length), "learning cases with known limitations; future remediation required"),
        stat(String(attempts.length), `rejected replacement attempts; ${chosen ? `${chosen} selected` : "none selected"}`)),
      h("p", { class: "population-note" }, h("b", {}, "Different populations, not a total. "),
        `Featured presentations and learning cases are the ${data.accounts.length} fictional accounts. ` +
        "The rejected attempts tried to replace learning-case recordings and are evidence only. " +
        "The original-eight baseline and all-attempt totals are reported separately below."),
      h("h3", { class: "population-heading" }, "Learning cases requiring future remediation"),
      ...currentActions.map((c) => h("p", {}, h("a", { href: "#qa", onclick: () => setEvidenceClip(c.id) }, name(c.id)),
        " — ", accountForClip(data, c)?.learning_defect || c.demo_disposition?.summary || readiness(c).text)),
      inspect("Six targeted replacement attempts — none selected",
        h("p", {}, "Complete assistant frame review and unchanged automated screening gates were both considered. " +
          "These rejected attempts are evidence, not six additional selected examples awaiting approval."),
        (DISPOSITIONS?.replacement_attempts || []).map(r => h("p", {},
          h("a", { href: "#qa", onclick: () => setEvidenceClip(r.clip) }, name(r.clip)), " — ", r.disposition))),
      inspect("Historical source findings and versioned adjudications",
      // Native replaceChildren does not flatten arrays; spread the nodes or the browser prints "[object HTMLDivElement]".
      ...blockers.map((f) => h("div", { class: "readiness blocked", role: "note", "data-readiness": "blocked" },
        h("b", {}, `Publication blocker · ${name(f.clip)}: `), f.observation, " ",
        h("span", { class: "hint" }, f.mitigation_in_demo || ""))),
      ...(decisions.length ? [h("details", { class: "inspect pending-decisions" },
        h("summary", {}, "Original policy / evaluator questions (historical)"),
        decisions.map((f) => h("p", {},
          h("a", { href: "#qa", onclick: () => setEvidenceClip(f.clip) }, name(f.clip)), " — ",
          DECISION_REASON[f.id] || f.observation)))] : []),
      (DISPOSITIONS?.adjudications || []).map((a) => h("p", {}, h("b", {}, `${a.clip}: `), a.decision, " ", a.scope))),
      coverage, support);
  }

  // One scope drives route explanation, recorded QA and AI evaluations. This never changes the guide's selection.
  function initEvidence(data, clips, products, routeCalculator) {
    const selector = $("#evidence-scope");
    const selectedIds = new Set(data.accounts.map((a) => a.recorded_clip));
    const groupOf = (learning) => data.accounts.filter((a) => (a.curation === "learning") === learning).map((a) =>
      h("option", { value: a.recorded_clip }, a.fictional_brand));
    selector.replaceChildren(
      h("optgroup", { label: "Featured presentations" }, groupOf(false)),
      h("optgroup", { label: "Learning cases" }, groupOf(true)),
      h("option", { value: "all" }, "All attempts, including withheld"),
      h("optgroup", { label: "Other recorded clips and attempts" }, data.clips.filter((c) => !selectedIds.has(c.id)).map((c) =>
        h("option", { value: c.id }, `${recordingName(data, c)}${c.withheld_reason ? " — withheld" : " — alternative / historical"}`))));
    let currentRecording = null;
    $("#calc-reset").addEventListener("click", () => { if (currentRecording) routeCalculator(currentRecording); });
    function update(id) {
      selector.value = id;
      const c = clips[id], a = c && accountForClip(data, c);
      currentRecording = c || null;
      $("#calc-reset").disabled = !c;
      $("#evidence-current").textContent = c ? `Showing ${recordingName(data, c)} · ID: ${c.id}`
        : `Showing all ${data.clips.length} recorded clips and attempts, including historical and withheld media evidence.`;
      for (const section of ["routing", "qa", "evals"]) {
        $(`#${section}-context`).textContent = c ? `Selected recording: ${recordingName(data, c)}` : "All recorded attempts";
      }
      $("#selected-route").replaceChildren(c
        ? h("div", {}, h("h3", {}, `Retained recording · ${a?.fictional_brand || c.id}`),
          h("p", {}, `${c.model_name} · ${c.mode}`),
          h("p", {}, a && !a.hero_clip ? a.why : c.mode === "image-to-video"
            ? "This recorded route uses a supplied product reference image." : "This recorded route starts from a text brief."),
          h("p", { class: "hint" }, `Recorded estimate ${usd(c.estimate_usd)} · not a bill. ` +
            (c.has_audio ? "The retained file has audio; listening review is still required." : "The presentation recording has no audio track.")),
          a?.id === "woodgrove" ? h("p", {}, "Rationale v2: the brief requests high-volume weekly promos and supplies a product image. " +
            "Turbo image-to-video at 768P is $0.04/s versus H3 Max at $0.08/s in the preview registry. " +
            "This cost/mode decision does not guarantee exact products, readable labels or campaign readiness.") : null)
        : h("p", {}, "All routes on file. Select an example or clip above for its recorded model choice and estimate."));
      if (c) routeCalculator(c);
      initQa(data, clips, products, c ? [c] : data.clips);
      initEvals(data, clips, products, c?.id || null);
    }
    selector.addEventListener("change", () => update(selector.value));
    setEvidenceClip = (id) => { if (clips[id] && selector.value !== id) update(id); };
    update(data.accounts[0].recorded_clip);
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
    return (c) => {
      nIn.value = "1";
      mSel.value = c.model;
      fillTiers();
      if (Object.hasOwn(model().price_per_second_usd, c.price_key)) tSel.value = c.price_key;
      fillDurations();
      if (model().durations_by_tier && choicesOf(model()).includes(c.requested_duration_s)) secChoice.value = String(c.requested_duration_s);
      else if (!model().durations_by_tier) secInput.value = String(c.requested_duration_s);
      calc();
    };
  }

  // ---------- recorded QA screening ----------
  function initQa(data, clips, products, all) {
    const screened = [...new Map(all.map((c) => [c.source_qa_clip || c.id, clips[c.source_qa_clip || c.id]])).values()];
    const pass = screened.filter((c) => c.qa.verdict === "pass").length;
    const sev = screened.map((c) => c.qa.content_safety_max_severity).filter((s) => s !== null);
    const attempts = "distinct source recordings";
    $("#qa-summary").replaceChildren(
      h("div", { class: "stat" }, h("b", {}, `${pass} / ${screened.length}`), `${attempts} passed automated screening`),
      h("div", { class: "stat" }, h("b", {}, `${screened.filter((c) => c.qa.verdict === "fail").length} / ${screened.length}`), `${attempts} failed at least one threshold`),
      h("div", { class: "stat" }, h("b", {}, sev.length ? String(Math.max(...sev)) : "n/a"),
        `max Content Safety severity across ${all.length === 1 ? "sampled frames of the source recording" : `all ${screened.length} attempts, including historical and withheld attempts`}`),
      h("div", { class: "stat" }, h("b", {}, "No campaign approval"), "Demo dispositions and historical screening are separate"));
    $("#qa-summary-note").replaceChildren(denominatorNote(data));

    $("#qa-recordings").replaceChildren(...all.map((c) => {
      const a = data.accounts.find((a) => a.recorded_clip === c.id);
      const findings = findingsFor(c.id).filter((f) => isOpen(f) && f.severity !== "informational");
      return h("article", { class: "card qa-recording", "data-clip": c.id },
        h("p", { class: "eyebrow" }, c.withheld_reason ? "Withheld attempt — no media" : a ? "Selected example" : "Alternative / historical attempt"),
        h("h3", {}, recordingName(data, c)),
        c.demo_disposition ? h("section", {}, h("h4", {}, "Current fictional-demo disposition"),
          h("p", {}, c.demo_disposition.summary), h("p", {}, c.demo_disposition.guidance),
          h("p", { class: "hint" }, "Owner-delegated assistant review, not customer-campaign publication approval.")) : null,
        c.presentation ? h("p", {}, c.presentation.transformation, " Source QA belongs to ", c.source_qa_clip,
          "; this derivative is not a new generation or a new v1 screening.") : null,
        h("section", { class: "original-screening" }, h("h4", {}, "Original recorded screening"), verdictPill(c.qa.verdict),
          h("p", {}, c.qa.failed_checks.length ? failedScreening(c.qa)
            : c.qa.verdict === "pass" ? "Sampled frames passed the recorded checks; this is not full-video approval."
              : "No recorded screening verdict is available.")),
        findings.length || a?.review_note ? h("section", { class: "additional-finding" },
          h("h4", {}, "Additional evaluator / review finding"),
          h("p", { class: "hint" }, "Separate evidence; this does not change or explain the original screening verdict."),
          findings.map((f) => h("div", {}, h("p", {}, f.observation), h("p", { class: "hint" }, `Source: ${f.source}`))),
          a?.review_note ? h("p", {}, a.review_note) : null) : null,
        (DISPOSITIONS?.adjudications || []).filter((a) => a.clip === (c.source_qa_clip || c.id)).map((a) =>
          h("section", {}, h("h4", {}, "Versioned adjudication"), h("p", {}, a.decision), h("p", { class: "hint" }, a.scope))),
        c.withheld_reason ? h("p", { class: "warn-text" }, c.withheld_reason) : null,
        c.independent_review ? inspect("Complete-frame review and grader-calibration evidence",
          h("p", {}, "Independent assistant review, not owner human approval. All decoded frames reviewed; exact source/presentation hashes verified."),
          h("p", {}, c.independent_review.independent_disposition),
          h("ul", {}, (c.independent_review.findings || []).concat(c.independent_review.other_deviations || []).map(t => h("li", {}, t))),
          c.independent_review.criteria ? kv(Object.entries(c.independent_review.criteria)) : null,
          c.independent_review.qa_assessment ? h("p", {}, c.independent_review.qa_assessment) : null) : null,
        inspect("Exact scores, thresholds, findings and request ID",
          h("p", {}, c.id), h("p", {}, c.model_name),
          c.learning_note ? h("p", {}, c.learning_note) : null,
          h("ul", {}, c.qa.findings.map((f) => h("li", {}, f))),
          h("div", { class: "table-wrap" }, h("table", {},
            h("caption", {}, "Recorded scores / per-brand thresholds"),
            h("thead", {}, h("tr", {}, CHECKS.map((k) => h("th", { scope: "col" }, CHECK_LABEL[k])))),
            h("tbody", {}, h("tr", {}, CHECKS.map((k) => scoreCell(c.qa, k)))))),
          kv([["Content Safety maximum for this recording", c.qa.content_safety_max_severity ?? "n/a"],
            ["Request ID", h("span", { class: "mono" }, c.request_id)]])));
    }));

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
    "hero-grocery-turbo": "Original QA reported thermometer/honey omissions. Frame adjudication contradicts that blanket claim: both appear early; later cropping and weak pharmacy context remain. Original scores are unchanged.",
  };

  // Plain-language questions, so each check card says what was asked before it says what was found.
  const CHECK_QUESTION = {
    concept_adherence: "Does the clip show the concept requested for its stage?",
    product_identity: "Does the product match the approved reference image?",
    brand_marks: "Are logos and label marks consistent with the approved product?",
    audio_signal: "Is there a usable audio signal? (stream, loudness and true peak only)",
  };
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  function runList(reps, shown) {
    return h("ol", { class: "reps" }, reps.map((r) => h("li", {},
      h("p", { class: "run-line" }, h("b", {}, `Run ${r.repeat}`), ` · grader ${r.grader_label || "n/a"} · service ${r.service_label} (score ${r.service_score})`),
      h("p", { class: "run-id" }, "Run ID ", h("span", { class: "mono" }, r.run_id)),
      r === shown ? h("p", { class: "hint" }, "Reasons shown above.")
        : r.reasons && r.reasons.length ? h("ul", {}, r.reasons.map((t) => h("li", {}, t)))
          : h("p", { class: "hint" }, "No written reasons were recorded for this run."))));
  }

  function checkCard(id, key, name, chk) {
    const expectedBad = id === "negative-control" && key === "product_identity" && chk.label === "mismatch";
    const reps = chk.repeats || chk.cloud || [];
    const svc = [...new Set(reps.map((r) => r.service_label))];
    const shown = reps.find((r) => r.reasons && r.reasons.length);
    const m = chk.measurements;
    return h("article", { class: "check-card", "data-check": key },
      h("div", { class: "check-head" }, h("h5", {}, name), labelPill(chk.label, `${chk.label} · ${chk.agreement}`, expectedBad)),
      h("p", { class: "check-question" }, CHECK_QUESTION[key]),
      expectedBad ? h("p", { class: "check-note" }, h("b", {}, "Expected result: "), "the control was correctly rejected.") : null,
      chk.needs_human_review ? h("p", { class: "check-note warn-text" }, "Needs human review: the repeated runs disagree.") : null,
      svc.length && svc.join() !== chk.label ? h("p", { class: "check-note" }, h("b", {}, `Service label: ${svc.join(" / ")}. `),
        // Only a non-passing service record needs the "recorded as fail" explanation.
        svc.includes("fail") ? "The Foundry Evals service records any non-passing grader label as fail (score 0), so the grader's own label is shown first."
          : "The grader's own label is shown first.") : null,
      chk.scope ? h("p", { class: "check-note" }, h("b", {}, "Scope: "), chk.scope, ". It cannot tell whether sounds match the picture.") : null,
      m ? kv([["Measured", `${m.integrated_lufs} LUFS integrated · ${m.true_peak_dbtp > 0 ? "+" : ""}${m.true_peak_dbtp} dBTP true peak · ${m.loudness_range_lu} LU loudness range`]]) : null,
      chk.local ? h("p", { class: "check-note" }, h("b", {}, `Local ffmpeg check: ${chk.local.label}. `), chk.local.reasons.join("; ")) : null,
      shown ? h("div", { class: "check-why" },
        h("p", { class: "check-why-head" }, `Why · grader's reasons from run ${shown.repeat} of ${reps.length}`),
        h("ul", {}, shown.reasons.map((t) => h("li", {}, t)))) : null,
      reps.length ? h("details", { class: "runs" },
        h("summary", {}, reps.length > 1 ? `All ${reps.length} runs, labels and run IDs` : "Run label and run ID"),
        runList(reps, shown)) : null);
  }

  function clipCard(id, m, name) {
    const applicable = MEDIA_CHECKS.filter(([key]) => m.checks[key] && m.checks[key].applicable);
    const na = MEDIA_CHECKS.filter(([key]) => m.checks[key] && !m.checks[key].applicable);
    const byReason = new Map();
    na.forEach(([key, label]) => byReason.set(m.checks[key].na_reason, [...(byReason.get(m.checks[key].na_reason) || []), label]));
    const o = m.observation;
    return h("section", { class: "clip-card", "data-clip": id },
      h("h4", {},
        h("span", { class: "clip-title" }, name),
        h("span", { class: "clip-meta" }, `${m.stage} · ${id}`),
        h("span", { class: "clip-pills" }, MEDIA_CHECKS.map(([key, label]) =>
          evalPill(m.checks[key], label, id === "negative-control" && key === "product_identity" && m.checks[key]?.label === "mismatch")))),
      o ? h("section", { class: "observed" },
        h("h5", {}, "What the vision model saw"),
        h("p", {}, o.scene_summary),
        o.comparison_notes ? h("p", {}, h("b", {}, "Compared with the reference: "), o.comparison_notes) : null,
        h("p", { class: "hint" }, `${plural(o.frames, "sampled frame")}${o.reference_image ? ` · reference image ${o.reference_image}` : " · no reference image"} · ${o.model}`)) : null,
      h("div", { class: "check-grid" }, applicable.map(([key, label]) => checkCard(id, key, label, m.checks[key]))),
      byReason.size ? h("div", { class: "check-na" }, [...byReason].map(([why, labels]) =>
        h("p", {}, h("b", {}, `Not applicable · ${labels.join(", ")}: `), why))) : null,
      o ? h("details", { class: "runs" }, h("summary", {}, "Observation request and hash"),
        kv([["Request ID", h("span", { class: "mono" }, o.request_id)], ["Observations hash", h("span", { class: "mono" }, o.observations_sha256)],
          ["Tokens", `${o.usage.input_tokens.toLocaleString()} input · ${o.usage.output_tokens.toLocaleString()} output`]])) : null);
  }

  function humanFindings(scope = null) {
    if (!hrAvailable()) {
      return h("div", { class: "readiness unavailable", role: "note", "data-readiness": "unavailable" },
        h("b", {}, "Human-review evidence unavailable."),
        " Human feedback and evaluator/agent findings could not be loaded; their absence here is not a clean result.");
    }
    const findings = HR.findings.filter((f) => !scope || f.clip === scope);
    if (!findings.length) return h("p", { class: "review-empty" },
      "No additional review notes are recorded for this recording. This does not imply campaign approval.");
    return h("div", { class: "findings" }, findings.map((f) => h("article", { class: `card finding ${isBlocker(f) ? "blocking" : ""}` },
        h("p", { class: "eyebrow" }, `Historical source record · ${f.severity} · original status: ${f.status}`),
        h("h4", {}, f.clip || f.case),
        h("p", {}, f.observation),
        f.measured_signal ? h("p", { class: "hint" }, f.measured_signal) : null,
        f.handling || f.mitigation_in_demo ? h("p", { class: "hint" }, f.handling || f.mitigation_in_demo) : null,
        h("p", { class: "hint" }, `Source: ${f.source}`),
        (DISPOSITIONS?.adjudications || []).filter(a => a.id === f.id).map(a =>
          h("p", {}, h("b", {}, "Current versioned adjudication: "), a.decision, " ", a.scope)))));
  }

  function initEvals(data, clips, products, scope = null) {
    const root = $("#evals-body");
    if (!EV) {
      root.replaceChildren(
        h("div", { class: "readiness unavailable", role: "note" }, h("b", {}, "AI evaluation evidence unavailable."),
          " The recorded evaluation results could not be loaded."),
        h("h3", {}, "Additional review notes"), humanFindings(scope));
      return;
    }
    const nameOf = (id) => {
      if (id === "negative-control") return "Negative control: cold brew frames scored against the drill reference";
      const c = clips[id];
      return c ? c.concept || (products[c.sku] ? products[c.sku].name : c.sku) : id;
    };
    const totalRuns = Object.values(EV.runs).reduce((n, r) => n + r.runs.length, 0);
    const completed = Object.values(EV.runs).reduce((n, r) => n + r.runs.filter((x) => x.status === "completed").length, 0);
    const neg = EV.negative_control;
    const legend = (pill, text) => h("li", {}, pill, " ", text);
    const targeted = data.targeted_evaluations.checks.filter(r => !scope || r.clip === scope ||
      (r.id.startsWith("grocery-") && accountForClip(data, clips[scope])?.id === "woodgrove"));
    const targetedNames = {
      "zava-concept-v2": "Zava: unbranded patio-layout concept",
      "grocery-rationale-v2": "Grocery routing: supported rationale v2",
      "grocery-rationale-unsupported-control": "Grocery routing: unsupported-guarantee control",
    };
    const entries = Object.entries(EV.media).filter(([id]) => !scope || id === scope);
    const runSummary =
      h("div", { class: "qa-summary" },
        h("div", { class: "stat" }, h("b", {}, `${completed} / ${totalRuns}`),
          `Foundry Evals runs completed (+${EV.superseded_audio_runs.runs.length} failed audio runs superseded)`),
        h("div", { class: "stat" }, h("b", {}, `${EV.repeats}×`), "repeats per LLM check; one audio-signal run"),
        h("div", { class: "stat" }, h("b", {}, neg.expected_behavior_met ? "rejected" : "MISSED"), `negative control (${neg.agreement})`),
        h("div", { class: "stat" }, h("b", {}, usd(EV.cost.estimated_usd_this_run)), `estimated spend (cap ${usd(EV.cost.cap_usd)})`));
    root.replaceChildren(
      h("h3", {}, "Evaluation status/results for this recording"),
      ...(targeted.length ? [h("section", { class: "targeted-evaluations" },
        h("h4", {}, "Targeted direct Azure OpenAI review"),
        h("p", { class: "hint" }, "Direct Azure OpenAI calls with explicit token bounds, not Foundry Evals service runs. " +
          "Original results below remain unchanged; one attempt per check is not a reliability study or approval."),
        targeted.map(r =>
          h("article", { class: "card check-card", "data-check": r.id }, h("h4", {}, targetedNames[r.id]), labelPill(r.result.label, r.result.label),
            h("ul", {}, (r.result.observations || []).concat(r.result.reasons || []).map(t => h("li", {}, t))),
            r.expected ? h("p", {}, `Calibration control expected ${r.expected}; observed ${r.result.label}.`) : null,
            r.brand_marks ? h("p", {}, "Brand marks and approved-PIM likeness are not applicable to this unbranded concept.") : null,
            (r.result.limitations || []).map(t => h("p", { class: "hint" }, t)),
            inspect("Request, exact scope and bound", h("p", {}, r.request_id), h("p", {}, r.sha256 || r.rationale_version),
              h("p", {}, `Maximum output ${r.max_output_tokens} tokens; conservative call reserve ${usd(r.reserved_usd)}.`))))
          )] : []),
      h("div", { class: "findings-by-clip" },
        entries.length ? entries.map(([id, m]) => clipCard(id, m, nameOf(id)))
          : h("p", { class: "notice" }, "No Foundry Evaluations run is recorded for this example. Recorded brand screening and Content Safety results are available under Brand QA.")),
      h("section", { class: "additional-review" }, h("h3", {}, "Additional review notes"), humanFindings(scope)),

      h("details", { class: "card legend" },
        h("summary", {}, "How to interpret the results"),
        h("ul", {},
          legend(labelPill("pass", "pass / match / consistent"), "the grader found what the rubric asks for."),
          legend(labelPill("partial", "partial / split"), "partly met, or repeated runs disagree; split results need human review."),
          legend(labelPill("fail", "fail / mismatch"), "not met. For the negative control, a mismatch is the expected result."),
          legend(h("span", { class: "pill" }, "N/A"), "the check does not apply to this clip; the reason is listed with it."),
          legend(h("b", {}, "Service label"), "is the Foundry Evals pass/fail record. It reports any non-passing grader label, including partial, as fail (score 0)."),
          legend(h("b", {}, "3/3, 2/3"), "how many of the repeated runs gave that label.")),
        h("p", { class: "hint" }, "These are AI screening results. None of them is publication approval, and none changes a recorded verdict."),
        h("h4", {}, "Methodology"),
        h("ol", {},
          h("li", {}, h("b", {}, "Stage A, vision observation: "), `the brand-qa-vision deployment describes ${EV.frames_per_clip} sampled frames per clip, with an approved PIM reference only where supplied. It writes neutral observations, not scores.`),
          h("li", {}, h("b", {}, "Stage B, Foundry Evals: "), "text graders in Microsoft Foundry score those observations against stage-aware rubrics, three repeats each. Routing decisions are evaluated separately, and a Python grader checks audio signal measurements."),
          h("li", {}, h("b", {}, "Why two stages: "), `${EV.image_input_spikes.length} native image-input grader spikes were rejected by the service ("${EV.image_input_spikes[0].error}"). Visual checks therefore depend on Stage A's text observations and can miss details a direct visual judge would catch.`)),
        h("p", { class: "hint" }, "Scope: visual checks judge frames, not motion or full clips. The audio check measures stream, loudness and true peak only; " +
          "it cannot tell whether sounds match the picture. None of this replaces human review, and none of it changes the original QA verdicts.")));
    if ($("#historical-evals").children.length) return;
    $("#historical-evals").replaceChildren(
      h("details", { class: "card why" },
        h("summary", {}, "Original-eight baseline: why the QA shows so many fails"),
        h("p", {}, "The original @brand-qa screen applies per-brand final-brand thresholds. Six of eight recorded clips fail measured criteria, for different reasons; text-only drafts are not required to fail:"),
        h("ul", {}, Object.entries(WHY_FAIL).map(([id, why]) => h("li", {}, h("b", {}, clips[id] ? (clips[id].concept || id) : id), `: ${why}`))),
        h("p", { class: "hint" }, "The AI evaluations below separate concept adherence from final-brand fidelity and mark checks that do not apply as N/A. " +
          "Concept adherence is 'partial' for all eight clips: the Foundry Evals service reports any non-passing label as 'fail' (score 0), so the grader's own label is shown here, with the service label alongside.")),

      h("details", { class: "table-wrap inspect" }, h("summary", {}, "Supporting comparison of all original-eight evaluations"),
        h("table", { class: "evals-table" },
          h("caption", {}, "At a glance: grader label per check (agreement across repeats). Select a source recording above for its reasons."),
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, "Clip"), h("th", { scope: "col" }, "Stage"),
            MEDIA_CHECKS.map(([, name, scope]) => h("th", { scope: "col" }, name, h("div", { class: "hint" }, scope))))),
          h("tbody", {}, Object.entries(EV.media).map(([id, m]) => h("tr", {},
            h("th", { scope: "row" }, nameOf(id), h("div", { class: "hint mono" }, id)),
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

      h("details", { class: "table-wrap inspect" }, h("summary", {}, "All routing evaluations (@foundry-router)"),
        h("table", {},
          h("caption", {}, "Recorded routing decisions vs expected rules"),
          h("thead", {}, h("tr", {}, ["Case", "Rule", "Expected", "Actual", "Model", "Mode", "Rationale grounded"].map((t) => h("th", { scope: "col" }, t)))),
          h("tbody", {}, Object.entries(EV.routing).map(([id, r]) => h("tr", {},
            h("th", { scope: "row" }, id), h("td", {}, r.case.rule),
            h("td", {}, `${r.case.expected_model} · ${r.case.expected_mode}`),
            h("td", {}, `${r.case.actual_model} · ${r.case.actual_mode}`),
            ["model_matches_expected", "mode_matches_expected", "rationale_grounded"].map((k) =>
              h("td", {}, labelPill(r[k].label, `${r[k].label} (${r[k].agreement})`)))))))),

      h("details", { class: "card" },
        h("summary", {}, "All original-eight run evidence, versions and cost"),
        runSummary,
        h("div", { class: "table-wrap" }, h("table", { class: "runs-table" },
          h("caption", {}, "Foundry Evals runs, grouped by evaluation"),
          h("thead", {}, h("tr", {}, ["Eval", "Run", "Run ID", "Status", "Passed / total"].map((t) => h("th", { scope: "col" }, t)))),
          Object.entries(EV.runs).map(([name, r]) => h("tbody", {}, r.runs.map((x, i) => h("tr", {},
            i === 0 ? h("th", { scope: "rowgroup", rowspan: String(r.runs.length) }, name,
              h("div", { class: "hint" }, `${r.dataset.kind}, ${r.dataset.rows} rows`), h("div", { class: "hint mono" }, r.eval_id)) : null,
            h("td", {}, `${i + 1} of ${r.runs.length}`),
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
