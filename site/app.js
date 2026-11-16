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

  function video(clip, opts = {}) {
    const el = h("video", {
      src: clip.file, controls: true, playsinline: true, preload: "metadata", loop: opts.loop,
      muted: !soundOn(), "aria-label": `${clip.model_name} render of ${clip.sku}${clip.concept ? `, ${clip.concept}` : ""}`,
    });
    el.muted = !soundOn();
    return el;
  }
  const soundOn = () => $("#sound") && $("#sound").checked;

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

  fetch("data.json").then((r) => {
    if (!r.ok) throw new Error(`data.json ${r.status}`);
    return r.json();
  }).then(init).catch((err) => {
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
    $("#sound").addEventListener("change", () => {
      document.querySelectorAll("video").forEach((v) => { v.muted = !soundOn(); });
    });
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
        return h("article", { class: "card draft vertical", "data-variant": c.variant },
          h("h3", {}, `#${c.variant} · ${c.concept}`),
          video(c, { loop: true }),
          h("p", { class: "meta" }, h("b", {}, c.model_name), ` · ${c.mode} · ${c.aspect_ratio}`),
          h("p", { class: "meta" }, `Recorded: ${secs(c.accepted_to_completed_s)} accepted→completed · est. ${usd(c.estimate_usd)}`),
          verdictPill(c.qa.verdict),
          h("button", { type: "button", onclick: () => choose(c.variant, true) }, `Choose concept #${c.variant}`));
      }));
    }

    function choose(variant, manual) {
      if (manual) cancel();
      selected = variant;
      setStep(3);
      document.querySelectorAll(".draft").forEach((el) => {
        const on = Number(el.dataset.variant) === variant;
        el.classList.toggle("selected", on);
        el.classList.toggle("dim", !on);
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
        out.className = "hero-out vertical";
        out.replaceChildren(
          h("div", {}, video(hero)),
          h("div", { class: "card" },
            h("p", { class: "eyebrow" }, "Recorded hero render"),
            h("h3", {}, `#${variant} · ${hero.concept}`),
            verdictPill(hero.qa.verdict),
            h("span", { class: "pill" }, "Human sign-off required"),
            kv([
              ["Model", `${hero.model_name} (${hero.mode})`],
              ["Source", "Approved PIM hero image (start frame)"],
              ["Audio", hero.has_audio ? "Native audio requested; audio stream present" : "No audio stream"],
              ["Recorded latency", `${secs(hero.accepted_to_completed_s)} accepted→completed`],
              ["Estimate", `${usd(hero.estimate_usd)} (preview list price × requested seconds)`],
              ["Request ID", h("span", { class: "mono" }, hero.request_id)],
              ["Rendered", hero.rendered_at],
            ]),
            h("p", { class: "hint" }, "Turn on Sound above to hear the native audio track. Review the full clip and audio before any approval.")));
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
})();
