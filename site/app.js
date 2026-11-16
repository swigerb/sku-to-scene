/* SKU to Scene browser demo: static replay of recorded Foundry renders. No network calls beyond loading
   this site's own files; nothing is generated or evaluated in the browser. */
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
  const verdictPill = (v) => h("span", { class: `pill ${v === "pass" ? "pass" : v === "fail" ? "fail" : "warn"}` },
    v === "pass" ? "QA screening: pass" : v === "fail" ? "QA screening: fail" : `QA: ${v || "not evaluated"}`);

  // Presentation-only playback level for the Kling hero: its native track peaks at +2.0 dBTP and a reviewer found
  // the ambience too loud. This lowers loudness only; the file and its native audio are unchanged.
  const PRESENTATION_VOLUME = { "lto-hero-kling": 0.5 };
  let EV = null; // sanitized Foundry Evals results (evaluations/foundry-evals-v1.json)
  let HR = null; // human-review findings (evaluations/human-review.json)

  function video(clip, opts = {}) {
    const el = h("video", {
      src: clip.file, controls: true, playsinline: true, preload: "metadata", loop: opts.loop,
      "data-clip": clip.id, "data-variant": opts.variant,
      "aria-label": `${clip.model_name} render of ${clip.sku}${clip.concept ? `, ${clip.concept}` : ""}` +
        (clip.has_audio ? "" : " (no audio track)"),
    });
    el.muted = !soundOn();
    if (PRESENTATION_VOLUME[clip.id]) el.volume = PRESENTATION_VOLUME[clip.id];
    return el;
  }
  const soundOn = () => $("#sound") && $("#sound").checked;

  function pausePlayers(except = null) {
    document.querySelectorAll("video").forEach((v) => { if (v !== except && !v.paused) v.pause(); });
  }

  // One player at a time; the Sound toggle and each player's native mute control stay in sync.
  let syncingMute = false;
  function setSound(on) {
    $("#sound").checked = on;
    syncingMute = true;
    document.querySelectorAll("video").forEach((v) => { v.muted = !on; });
    syncingMute = false;
  }
  document.addEventListener("play", (e) => {
    if (!(e.target instanceof HTMLVideoElement)) return;
    pausePlayers(e.target);
  }, true);
  document.addEventListener("volumechange", (e) => {
    if (syncingMute || !(e.target instanceof HTMLVideoElement)) return;
    if (e.target.muted === !soundOn()) return;
    setSound(!e.target.muted);
  }, true);

  const evalCheck = (clipId, check) => (EV && EV.media && EV.media[clipId] ? EV.media[clipId].checks[check] : null);
  const finding = (id) => (HR ? HR.findings.find((f) => f.id === id) : null);
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
    const a = evalCheck(c.id, "audio_signal");
    const m = a && a.measurements;
    if (!c.has_audio) {
      return h("p", { class: "audio-note none" }, h("b", {}, "No recorded audio track. "),
        `Audio was ${String(c.audio || "").startsWith("native") ? "requested" : "not requested"} for this ${c.model_name} render and the file has no audio stream, so the Sound toggle cannot add one.`);
    }
    const level = m ? ` ${m.integrated_lufs} LUFS, true peak ${m.true_peak_dbtp > 0 ? "+" : ""}${m.true_peak_dbtp} dBTP.` : "";
    if (String(c.audio || "").startsWith("native")) {
      return h("p", { class: "audio-note" }, h("b", {}, "Native audio requested."), level,
        PRESENTATION_VOLUME[c.id] ? ` Played here at ${PRESENTATION_VOLUME[c.id] * 100}% volume (presentation only; original file unchanged).` : "");
    }
    return h("p", { class: "audio-note" }, h("b", {}, "Unrequested model audio track."), level,
      " Not reviewed for meaning.");
  }

  function kv(rows) {
    return h("dl", { class: "kv" }, rows.filter(Boolean).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  }

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

  // ---------- theme ----------
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("s2s-theme", next); } catch (_) { /* storage unavailable */ }
  });

  const optionalJson = (url) => fetch(url, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  Promise.all([
    fetch("data.json", { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`data.json ${r.status}`);
      return r.json();
    }),
    optionalJson("evaluations/foundry-evals-v1.json"),
    optionalJson("evaluations/human-review.json"),
  ]).then(([data, ev, hr]) => { EV = ev; HR = hr; init(data); }).catch((err) => {
    $("#main").prepend(h("p", { class: "notice" }, `Could not load demo data (${err.message}).`));
  });

  function init(data) {
    const clips = Object.fromEntries(data.clips.map((c) => [c.id, c]));
    const products = data.products;
    const modelName = Object.fromEntries(data.models.map((m) => [m.key, m.name]));
    initLto(data, clips, products);
    initScenarios(data, clips, products);
    initRouting(data, modelName);
    initQa(data, clips, products);
    initEvals(data, clips);
    $("#sound").addEventListener("change", () => setSound(soundOn()));
  }

  // ---------- LTO walkthrough ----------
  function initLto(data, clips, products) {
    const lto = data.lto;
    const product = products[lto.sku];
    const hero = clips[lto.hero_clip];
    let timers = [];
    let selected = null;

    $("#brief-card").replaceChildren(
      h("img", { src: product.image, alt: `Approved PIM image: ${product.name}`, width: 140 }),
      h("div", {},
        h("h3", {}, product.name),
        h("span", { class: "pill auth" }, `PIM image: ${product.image_status}`),
        h("span", { class: "pill" }, "TikTok 9:16"),
        h("span", { class: "pill" }, product.brand),
        h("blockquote", {}, lto.presenter_prompt)));

    function setStep(n) {
      document.querySelectorAll(".steps li").forEach((li) => {
        const s = Number(li.dataset.step);
        li.classList.toggle("active", s === n);
        li.classList.toggle("done", s < n);
      });
    }
    function log(who, text) {
      $("#log").append(h("li", {}, h("span", { class: "who" }, who), " ", text));
      $("#log").scrollTop = $("#log").scrollHeight;
    }

    function renderDrafts() {
      $("#drafts").replaceChildren(...lto.drafts.map((id) => {
        const c = clips[id];
        const v = video(c, { loop: true, variant: c.variant });
        v.addEventListener("play", () => { if (selected !== c.variant) choose(c.variant, true, v); });
        return h("article", { class: "card draft vertical", "data-variant": c.variant },
          h("h3", {}, `#${c.variant} · ${c.concept}`),
          v,
          h("p", { class: "meta" }, h("b", {}, c.model_name), ` · ${c.mode} · ${c.aspect_ratio}`),
          h("p", { class: "meta" }, `Recorded: ${secs(c.accepted_to_completed_s)} accepted→completed · est. ${usd(c.estimate_usd)}`),
          audioNote(c),
          c.variant === lto.hero_variant && !c.has_audio && hero.has_audio
            ? h("p", { class: "hint" }, `The recorded ${hero.model_name} hero for this concept is a separate render that did request native audio.`)
            : null,
          h("div", {},
            verdictPill(c.qa.verdict),
            evalPill(evalCheck(c.id, "concept_adherence"), "AI eval · concept")),
          h("p", { class: "hint" }, "These recorded drafts failed measured final-brand criteria, including garbled lettering in concept #2; text-only drafts are not required to fail. " +
            "The AI evaluation judges concept adherence instead; see AI evaluations."),
          h("button", { type: "button", class: "choose", "aria-pressed": "false", onclick: () => choose(c.variant, true) },
            `Choose concept #${c.variant}`));
      }));
    }

    function choose(variant, manual, playingDraft = null) {
      if (manual) cancel();
      pausePlayers(playingDraft);
      selected = variant;
      setStep(3);
      document.querySelectorAll(".draft").forEach((el) => {
        const on = Number(el.dataset.variant) === variant;
        el.classList.toggle("selected", on);
        el.classList.toggle("dim", !on);
        const b = el.querySelector("button.choose");
        b.setAttribute("aria-pressed", String(on));
        b.textContent = on ? `✓ Concept #${el.dataset.variant} selected` : `Choose concept #${el.dataset.variant}`;
      });
      const concept = lto.concepts[variant - 1];
      log("presenter", `selects concept #${variant} (${concept.title}).`);
      renderHero(variant);
    }

    function renderHero(variant) {
      const out = $("#hero-out");
      out.hidden = false;
      setStep(4);
      if (variant === lto.hero_variant) {
        log("@foundry-router", `upgrade → ${hero.model_name} ${hero.mode} from the approved hero image, native audio.`);
        log("@brand-qa", `recorded verdict: ${hero.qa.verdict} (automated screening; human sign-off required).`);
        const blocker = finding("hero-audio-semantic-mismatch");
        out.className = "hero-out vertical";
        out.replaceChildren(
          h("div", {}, video(hero)),
          h("div", { class: "card" },
            h("p", { class: "eyebrow" }, "Recorded hero render"),
            h("h3", {}, `#${variant} · ${hero.concept}`),
            verdictPill(hero.qa.verdict),
            h("span", { class: "pill" }, "Human sign-off required"),
            h("div", {},
              evalPill(evalCheck(hero.id, "product_identity"), "AI eval · identity"),
              evalPill(evalCheck(hero.id, "brand_marks"), "AI eval · brand marks"),
              evalPill(evalCheck(hero.id, "audio_signal"), "Audio signal")),
            blocker ? h("div", { class: "blocker", role: "note" },
              h("b", {}, `Publication blocker (${blocker.source}): `), blocker.observation, " ",
              h("span", { class: "hint" }, blocker.mitigation_in_demo)) : null,
            kv([
              ["Model", `${hero.model_name} (${hero.mode})`],
              ["Source", "Approved PIM hero image (start frame)"],
              ["Audio", audioNote(hero)],
              ["Recorded latency", `${secs(hero.accepted_to_completed_s)} accepted→completed`],
              ["Estimate", `${usd(hero.estimate_usd)} (preview list price × requested seconds)`],
              ["Request ID", h("span", { class: "mono" }, hero.request_id)],
              ["Rendered", hero.rendered_at],
            ]),
            h("p", { class: "hint" }, "Turn on Sound (or unmute the player) to hear the native track. Signal checks measure loudness and peaks only; " +
              "whether the sounds match the picture needs a human listener.")));
      } else {
        const concept = lto.concepts[variant - 1];
        log("@foundry-router", `no recorded hero exists for concept #${variant}; nothing is generated in this replay.`);
        out.className = "hero-out no-hero";
        out.replaceChildren(h("div", { class: "card" },
          h("p", { class: "eyebrow" }, "No recorded hero for this concept"),
          h("h3", {}, `#${variant} · ${concept.title}`),
          h("p", {}, `The recorded run rendered a hero only for concept #${lto.hero_variant} (${lto.concepts[lto.hero_variant - 1].title}). ` +
            "This static page cannot and does not generate new video. In live mode, @foundry-router would route this choice to " +
            `${hero.model_name} image-to-video with native audio, which is a new billable Foundry job.`),
          h("button", { type: "button", onclick: () => choose(lto.hero_variant, true) },
            `Show the recorded hero (concept #${lto.hero_variant})`)));
      }
    }

    function cancel() { timers.forEach(clearTimeout); timers = []; }
    function reset() {
      cancel();
      pausePlayers();
      selected = null;
      $("#log").replaceChildren();
      $("#hero-out").hidden = true;
      renderDrafts();
      setStep(1);
    }
    function at(ms, fn) { timers.push(setTimeout(fn, ms)); }

    $("#replay-reset").addEventListener("click", reset);
    $("#replay-play").addEventListener("click", () => {
      reset();
      const d = lto.drafts.map((id) => clips[id]);
      at(0, () => log("@retail-merchandiser", `brief for ${products[lto.sku].name}: three 9:16 concepts with camera and audio cues.`));
      at(1200, () => {
        setStep(2);
        log("@foundry-router", `drafting stage → fast tiers: ${[...new Set(d.map((c) => c.model_name))].join(" + ")}.`);
      });
      d.forEach((c, i) => at(2200 + i * 900, () => log("@foundry-router",
        `#${c.variant} ${c.concept}: ${c.model_name}, recorded ${secs(c.accepted_to_completed_s)}, est. ${usd(c.estimate_usd)}.`)));
      at(5200, () => log("@brand-qa", `recorded draft verdicts: ${d.map((c) => `#${c.variant} ${c.qa.verdict}`).join(", ")}.`));
      at(6600, () => choose(lto.hero_variant, false));
      at(7000, () => $("#hero-out").scrollIntoView({ behavior: "smooth", block: "nearest" }));
    });
    reset();
  }

  // ---------- Scenarios ----------
  function initScenarios(data, clips, products) {
    const tabs = $("#scenario-tabs");
    const body = $("#scenario-body");
    function show(i) {
      pausePlayers();
      tabs.querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-selected", String(i === j)));
      const s = data.scenarios[i];
      body.replaceChildren(
        h("p", { class: "lede small" }, h("b", {}, s.use_case), " ", s.why,
          h("span", { class: "hint" }, ` Representative account types: ${s.accounts}.`)),
        h("div", { class: "scenario" }, s.clips.map((id) => {
          const c = clips[id];
          const p = products[c.sku];
          const pim = c.source_image
            ? h("img", { class: "pim", src: c.source_image, alt: `Approved PIM image: ${p.name}` })
            : h("div", { class: "placeholder" }, "Text brief only: no PIM image was used (text-to-video).");
          return h("article", { class: `card${c.aspect_ratio === "9:16" ? " vertical" : ""}` },
            h("h3", {}, p.name),
            h("div", { class: "pair" },
              h("div", {}, h("p", { class: "hint" }, "Input"), pim),
              h("div", {}, h("p", { class: "hint" }, "Recorded Foundry render"), video(c))),
            verdictPill(c.qa.verdict),
            h("div", {},
              evalPill(evalCheck(c.id, "concept_adherence"), "AI eval · concept"),
              evalPill(evalCheck(c.id, "product_identity"), "identity"),
              evalPill(evalCheck(c.id, "brand_marks"), "brand marks")),
            kv([
              ["Model", `${c.model_name} · ${c.mode} · ${c.aspect_ratio}`],
              ["Recorded latency", `${secs(c.accepted_to_completed_s)} accepted→completed`],
              ["Estimate", usd(c.estimate_usd)],
              c.qa.failed_checks.length ? ["Failed checks", c.qa.failed_checks.join(", ")] : null,
              c.qa.findings.length ? ["Top finding", c.qa.findings[0]] : null,
            ]));
        })));
    }
    tabs.replaceChildren(...data.scenarios.map((s, i) =>
      h("button", { type: "button", role: "tab", onclick: () => show(i) }, s.title)));
    show(0);
  }

  // ---------- Routing & cost ----------
  function initRouting(data) {
    const table = $("#models-table");
    table.append(
      h("thead", {}, h("tr", {}, ["Model", "Modes", "Offering", "Speed tier", "Native audio", "Price tiers", "Strengths"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, data.models.map((m) => h("tr", {},
        h("th", { scope: "row" }, m.name), h("td", {}, m.modes.join(", ")), h("td", {}, m.offering),
        h("td", {}, m.speed_tier), h("td", {}, m.native_audio ? "yes" : "no"),
        h("td", {}, Object.entries(m.price_per_second_usd).map(([k, v]) => h("div", { class: "mono" }, `${k}: $${v}/s`))),
        h("td", {}, m.strengths.join("; "))))));

    const mSel = $("#calc-model"), tSel = $("#calc-tier");
    mSel.replaceChildren(...data.models.map((m) => h("option", { value: m.key }, m.name)));
    const fill = () => {
      const m = data.models.find((x) => x.key === mSel.value);
      tSel.replaceChildren(...Object.entries(m.price_per_second_usd).map(([k, v]) => h("option", { value: v }, `${k} ($${v}/s)`)));
    };
    const calc = () => {
      const sec = Math.max(0, Number($("#calc-sec").value) || 0);
      const n = Math.max(0, Math.floor(Number($("#calc-n").value) || 0));
      const total = Number(tSel.value) * sec * n;
      $("#calc-out").textContent = `${usd(total)} estimated for ${n} × ${sec} s`;
    };
    mSel.addEventListener("change", () => { fill(); calc(); });
    $("#calc").addEventListener("input", calc);
    $("#calc").addEventListener("submit", (e) => e.preventDefault());
    fill(); calc();
  }

  // ---------- QA evidence ----------
  function initQa(data, clips, products) {
    const all = data.clips;
    const pass = all.filter((c) => c.qa.verdict === "pass").length;
    const sev = all.map((c) => c.qa.content_safety_max_severity).filter((s) => s !== null);
    $("#qa-summary").replaceChildren(
      h("div", { class: "stat" }, h("b", {}, `${pass} / ${all.length}`), "passed automated screening"),
      h("div", { class: "stat" }, h("b", {}, `${all.length - pass}`), "failed at least one threshold"),
      h("div", { class: "stat" }, h("b", {}, sev.length ? String(Math.max(...sev)) : "n/a"), "max Content Safety severity"),
      h("div", { class: "stat" }, h("b", {}, `${all.filter((c) => c.qa.human_signoff_required).length}`), "require human sign-off"));

    $("#qa-table").append(
      h("thead", {}, h("tr", {}, ["Clip", "Model", "Verdict", ...CHECKS.map((c) => CHECK_LABEL[c]), "Safety max", "Request ID"].map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, all.map((c) => h("tr", {},
        h("th", { scope: "row" }, c.id, h("div", { class: "hint" }, c.concept || products[c.sku].name)),
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

  function initEvals(data, clips) {
    const root = $("#evals-body");
    if (!EV) {
      root.replaceChildren(h("p", { class: "notice" }, "Evaluation results are not available in this build."));
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

      HR ? h("div", {},
        h("h3", { class: "sub" }, "Human feedback and evaluator/agent findings"),
        h("div", { class: "findings" }, HR.findings.map((f) => h("article", { class: `card finding ${f.severity === "publication blocker" ? "blocking" : ""}` },
          h("p", { class: "eyebrow" }, `${f.severity} · ${f.status}`),
          h("h4", {}, f.clip || f.case),
          h("p", {}, f.observation),
          f.measured_signal ? h("p", { class: "hint" }, f.measured_signal) : null,
          f.handling || f.mitigation_in_demo ? h("p", { class: "hint" }, f.handling || f.mitigation_in_demo) : null,
          h("p", { class: "hint" }, `Source: ${f.source}`))))) : null,

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
