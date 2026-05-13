/* ObserVIBElity — Use-case wizard
 *
 * Renders the bundled YAML for registry/use_cases/<name>.yaml entirely in
 * the browser. No frameworks. Compatible with the schema at
 * tools/usecase_build/schema.py.
 */
(function () {
  "use strict";

  // ---- Constants -----------------------------------------------------

  var TOTAL_STEPS = 7;

  var STEP_TITLES = {
    1: "Basics",
    2: "Archetype",
    3: "Parameters",
    4: "Evaluator + alert",
    5: "Demo metadata",
    6: "SLO",
    7: "Review & download",
  };

  var KEBAB_RE = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

  // ---- Form state ----------------------------------------------------

  var formState = {
    step: 1,
    archetype: null,
    centerpiece: false,
  };

  // ---- Archetype defaults --------------------------------------------

  function defaultsForArchetype(archetype) {
    switch (archetype) {
      case "trace-and-fix":
        return {
          severity: "medium",
          rate: "1m",
          evaluator_kind: "rule",
          evaluator_spec:
            'span.name =~ "{{trace_filter}}" and span.status == "error" and span.attributes.error_message =~ "{{error_pattern}}"',
          alert_condition:
            'sum(rate(ai_o11y_usecase_errors_total{usecase="<name>"}[5m])) > 0',
        };
      case "per-user-pattern":
        return {
          severity: "high",
          rate: "5m",
          evaluator_kind: "rubric",
          evaluator_spec:
            'count(messages.persona_id = "{{persona}}" and msg.matches_pattern("{{signature}}")) >= 3 in 15m',
          alert_condition:
            'sum by (persona_id) (increase(ai_o11y_signal_total{usecase="<name>"}[15m])) >= 3',
        };
      case "leaderboard":
        return {
          severity: "medium",
          rate: "15m",
          evaluator_kind: "rule",
          evaluator_spec:
            "topk(5, sum by ({{group_by}}) (increase({{rank_by}}[1h])))",
          alert_condition:
            '(topk(1, avg by (model) (rate(ai_o11y_eval_score{usecase="<name>"}[6h]))) - topk(1, avg by (model) (rate(ai_o11y_eval_score{usecase="<name>"}[24h] offset 24h)))) > 0.1',
        };
      case "single-event-severity":
        return {
          severity: "critical",
          rate: "10m",
          evaluator_kind: "rule",
          evaluator_spec:
            'severity == "critical" and event.name == "{{event_pattern}}"',
          alert_condition:
            'sum(increase(ai_o11y_critical_events_total{usecase="<name>"}[1m])) > 0',
        };
      case "cascade":
        return {
          severity: "high",
          rate: "5m",
          evaluator_kind: "rule",
          evaluator_spec:
            'count_per_session({{counter_metric}}) > {{threshold}}',
          alert_condition:
            'sum by (session_id) (increase({{counter_metric}}[5m])) > 10',
        };
      default:
        return {
          severity: "medium",
          rate: "5m",
          evaluator_kind: "rule",
          evaluator_spec: "",
          alert_condition: "",
        };
    }
  }

  // ---- Validation ----------------------------------------------------

  function validateName(value) {
    if (!value) return "name is required";
    if (value !== value.toLowerCase()) return "must be lowercase";
    if (!KEBAB_RE.test(value)) return "must be kebab-case (e.g. data-theft-tim)";
    return null;
  }

  function setError(fieldId, message) {
    var input = document.getElementById(fieldId);
    var err = document.getElementById("err-" + fieldId);
    if (!input) return;
    if (message) {
      input.classList.add("has-error");
      if (err) err.textContent = message;
    } else {
      input.classList.remove("has-error");
      if (err) err.textContent = "";
    }
  }

  // ---- YAML helpers --------------------------------------------------

  // Quote a scalar value if it contains anything yaml-special.
  // Numbers and booleans render bare. Strings that look like numbers / bools
  // get quoted to stay strings.
  function yamlScalar(s) {
    if (s === null || s === undefined) return '""';
    if (typeof s === "number") {
      if (isNaN(s)) return '"NaN"';
      return String(s);
    }
    if (typeof s === "boolean") return s ? "true" : "false";

    var str = String(s);
    if (str === "") return '""';
    // Reserved YAML scalars that would mis-parse if bare
    if (/^(true|false|null|yes|no|on|off|~)$/i.test(str)) return JSON.stringify(str);
    // Whole-string numeric (int / float / scientific) -> must quote to stay string
    if (/^-?(\d+(\.\d+)?|\.\d+)([eE][+-]?\d+)?$/.test(str)) return JSON.stringify(str);
    // Containing newlines: caller should use block scalar; here fall back to JSON
    if (str.indexOf("\n") !== -1) return JSON.stringify(str);
    // Safe-character bare scalars: letters, digits, dashes, dots, underscores,
    // slashes, plus a few non-special punctuation marks.
    if (/^[a-zA-Z0-9_\-./@+]+$/.test(str)) return str;
    // Otherwise double-quote with JSON escapes (valid YAML flow-scalar form)
    return JSON.stringify(str);
  }

  // Block scalar (|) with given indentation prefix
  function yamlBlock(s, indent) {
    var lines = String(s).split("\n");
    return lines.map(function (l) { return indent + l; }).join("\n");
  }

  // ---- YAML generator ------------------------------------------------

  function generateYaml(d) {
    var lines = [];
    lines.push("# Bundled use case — generated by wizard/usecase.html");
    lines.push("# Schema: tools/usecase_build/schema.py");
    lines.push("");
    lines.push("name: " + yamlScalar(d.name));
    lines.push("title: " + yamlScalar(d.title));
    lines.push("app: " + yamlScalar(d.app));
    lines.push("phase: " + d.phase);
    lines.push("centerpiece: " + (d.centerpiece ? "true" : "false"));
    lines.push("archetype: " + yamlScalar(d.archetype));

    if (d.description) {
      lines.push("description: |");
      lines.push(yamlBlock(d.description, "  "));
    }

    // scenarios
    lines.push("");
    lines.push("scenarios:");
    lines.push("  - name: " + yamlScalar(d.scenario_name));
    lines.push("    k6_template: " + yamlScalar(d.k6_template));
    if (d.persona) {
      lines.push("    persona: " + yamlScalar(d.persona));
    }
    lines.push("    rate: " + yamlScalar(d.rate));
    if (d.scenario_params && Object.keys(d.scenario_params).length > 0) {
      lines.push("    params:");
      Object.keys(d.scenario_params).forEach(function (k) {
        var v = d.scenario_params[k];
        if (typeof v === "string" && v.indexOf("\n") !== -1) {
          lines.push("      " + k + ": |");
          lines.push(yamlBlock(v, "        "));
        } else {
          lines.push("      " + k + ": " + yamlScalar(v));
        }
      });
    }

    // evaluators
    lines.push("");
    lines.push("evaluators:");
    lines.push("  - name: " + yamlScalar(d.evaluator_name));
    lines.push("    kind: " + yamlScalar(d.evaluator_kind));
    lines.push("    severity: " + yamlScalar(d.severity));
    if (d.evaluator_spec && d.evaluator_spec.indexOf("\n") !== -1) {
      lines.push("    spec: |");
      lines.push(yamlBlock(d.evaluator_spec, "      "));
    } else {
      lines.push("    spec: " + yamlScalar(d.evaluator_spec));
    }

    // dashboard
    lines.push("");
    lines.push("dashboard:");
    lines.push("  uid: " + yamlScalar("ai-obs-" + d.name));
    lines.push("  title: " + yamlScalar(d.title));
    lines.push("  panels_from_template: " + yamlScalar(d.archetype));
    lines.push("  folder: ai-observability");

    // alerts
    lines.push("");
    lines.push("alerts:");
    lines.push("  - name: " + yamlScalar(d.alert_name));
    if (d.alert_condition && d.alert_condition.indexOf("\n") !== -1) {
      lines.push("    condition: |");
      lines.push(yamlBlock(d.alert_condition, "      "));
    } else {
      lines.push("    condition: " + yamlScalar(d.alert_condition));
    }
    lines.push("    severity: " + yamlScalar(d.severity));
    if (d.alert_route) {
      lines.push("    route: " + yamlScalar(d.alert_route));
    }
    lines.push("    duration: 5m");

    // slo
    if (d.centerpiece && d.slo_objective) {
      lines.push("");
      lines.push("slo:");
      lines.push("  objective: " + yamlScalar(d.slo_objective));
      lines.push("  error_budget: " + d.slo_error_budget);
      lines.push("  window: " + yamlScalar(d.slo_window));
    }

    // demo
    lines.push("");
    lines.push("demo:");
    lines.push("  do: |");
    lines.push(yamlBlock(d.demo_do || "", "    "));
    lines.push("  signal: |");
    lines.push(yamlBlock(d.demo_signal || "", "    "));
    if (d.demo_sell) {
      lines.push("  sell: " + yamlScalar(d.demo_sell));
    }

    lines.push("");
    return lines.join("\n");
  }

  // ---- Clipboard + download ------------------------------------------

  function copyToClipboard(text, btn) {
    var done = function () {
      if (!btn) return;
      var original = btn.textContent;
      btn.textContent = "Copied!";
      btn.classList.add("is-success");
      setTimeout(function () {
        btn.textContent = original;
        btn.classList.remove("is-success");
      }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        legacyCopy(text);
        done();
      });
    } else {
      legacyCopy(text);
      done();
    }
  }
  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta);
  }

  function downloadYaml(content, name) {
    var safeName = (name || "use-case").replace(/[^a-z0-9-_]/gi, "-");
    var blob = new Blob([content], { type: "text/yaml;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = safeName + ".yaml";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 200);
  }

  // ---- Step navigation -----------------------------------------------

  function goToStep(n) {
    if (n < 1) n = 1;
    if (n > TOTAL_STEPS) n = TOTAL_STEPS;
    // Skip step 6 if not centerpiece
    if (n === 6 && !formState.centerpiece) {
      // jump in the direction we were heading
      var goingForward = n > formState.step;
      n = goingForward ? 7 : 5;
    }
    formState.step = n;

    document.querySelectorAll(".wizard-step").forEach(function (sec) {
      sec.classList.toggle(
        "hidden",
        parseInt(sec.getAttribute("data-step"), 10) !== n
      );
    });

    var fill = document.getElementById("progress-fill");
    if (fill) fill.style.width = Math.round((n / TOTAL_STEPS) * 100) + "%";
    var cur = document.getElementById("step-current");
    if (cur) cur.textContent = n;
    var ttl = document.getElementById("step-title");
    if (ttl) ttl.textContent = STEP_TITLES[n] || "";

    var back = document.getElementById("back-btn");
    var next = document.getElementById("next-btn");
    if (back) back.disabled = n === 1;
    if (next) next.textContent = n === TOTAL_STEPS ? "Done" : "Next";

    // On entering review, render YAML
    if (n === TOTAL_STEPS) renderReview();
  }

  // ---- Step transitions / validation ---------------------------------

  function validateCurrentStep() {
    var step = formState.step;
    var ok = true;

    if (step === 1) {
      var name = document.getElementById("uc-name").value.trim();
      var nameErr = validateName(name);
      setError("uc-name", nameErr);
      if (nameErr) ok = false;

      var title = document.getElementById("uc-title").value.trim();
      if (!title) { setError("uc-title", "title is required"); ok = false; }
      else setError("uc-title", null);
    }

    if (step === 2) {
      if (!formState.archetype) {
        // Show a simple alert in the hint area
        alert("Pick an archetype to continue.");
        ok = false;
      }
    }

    return ok;
  }

  // ---- Collect form data --------------------------------------------

  function collectFormData() {
    function v(id) { var el = document.getElementById(id); return el ? el.value.trim() : ""; }
    function vRaw(id) { var el = document.getElementById(id); return el ? el.value : ""; }

    var name = v("uc-name");
    var arch = formState.archetype || "trace-and-fix";

    var d = {
      name: name,
      title: v("uc-title") || name,
      app: (document.querySelector('input[name="uc-app"]:checked') || {}).value || "neoncart",
      phase: parseInt((document.querySelector('input[name="uc-phase"]:checked') || {}).value || "1", 10),
      centerpiece: document.getElementById("uc-centerpiece").checked,
      archetype: arch,
      description: null,
      scenario_name: name ? name.replace(/-/g, "_") : "scenario_1",
      k6_template: defaultK6Template(arch),
      persona: null,
      rate: v("uc-rate") || defaultsForArchetype(arch).rate,
      scenario_params: {},
      evaluator_name: v("ev-name") || (name + "." + arch.replace(/-/g, "_") + "_signal"),
      evaluator_kind: vRaw("ev-kind") || defaultsForArchetype(arch).evaluator_kind,
      evaluator_spec: vRaw("ev-spec") || defaultsForArchetype(arch).evaluator_spec,
      severity: vRaw("uc-severity") || defaultsForArchetype(arch).severity,
      alert_name: v("al-name") || (name + ".detection"),
      alert_condition: vRaw("al-condition") || defaultsForArchetype(arch).alert_condition.replace(/<name>/g, name),
      alert_route: v("al-route") || null,
      demo_do: vRaw("demo-do"),
      demo_signal: vRaw("demo-signal"),
      demo_sell: v("demo-sell"),
      slo_objective: v("slo-objective"),
      slo_error_budget: parseFloat(v("slo-error-budget") || "0.001"),
      slo_window: v("slo-window") || "30d",
    };

    // Archetype-specific scenario params
    if (arch === "trace-and-fix") {
      if (v("taf-trace-filter")) d.scenario_params.trace_filter = v("taf-trace-filter");
      if (v("taf-error-pattern")) d.scenario_params.error_pattern = v("taf-error-pattern");
    } else if (arch === "per-user-pattern") {
      if (v("pup-persona-id")) d.persona = v("pup-persona-id");
      if (vRaw("pup-message-template")) d.scenario_params.message_template = vRaw("pup-message-template");
      if (v("pup-message-count")) d.scenario_params.message_count = parseInt(v("pup-message-count"), 10);
    } else if (arch === "leaderboard") {
      if (v("lb-rank-by")) d.scenario_params.rank_by = v("lb-rank-by");
      if (v("lb-group-by")) d.scenario_params.group_by = v("lb-group-by");
      if (v("lb-regression-threshold")) d.scenario_params.regression_threshold_pct = parseFloat(v("lb-regression-threshold"));
    } else if (arch === "single-event-severity") {
      if (v("ses-event-pattern")) d.scenario_params.event_pattern = v("ses-event-pattern");
    } else if (arch === "cascade") {
      if (v("cas-counter-metric")) d.scenario_params.counter_metric = v("cas-counter-metric");
      if (v("cas-threshold")) d.scenario_params.threshold = parseInt(v("cas-threshold"), 10);
      if (v("cas-window")) d.scenario_params.window = v("cas-window");
    }
    return d;
  }

  function defaultK6Template(arch) {
    switch (arch) {
      case "per-user-pattern": return "sticky-persona";
      case "cascade": return "rate-burst";
      case "leaderboard": return "spread-across-models";
      case "single-event-severity": return "single-trigger";
      default: return "smoke";
    }
  }

  // ---- Render review -------------------------------------------------

  function renderReview() {
    var data = collectFormData();
    var yaml = generateYaml(data);
    var pre = document.getElementById("yaml-out");
    if (pre) pre.textContent = yaml;
    var fn = document.getElementById("yaml-filename");
    if (fn) fn.textContent = (data.name || "use-case") + ".yaml";
  }

  // ---- UI wiring -----------------------------------------------------

  function wireBasicsAutoPrefill() {
    var nameEl = document.getElementById("uc-name");
    var titleEl = document.getElementById("uc-title");
    var personaEl = document.getElementById("pup-persona-id");
    if (!nameEl) return;
    nameEl.addEventListener("input", function () {
      var v = nameEl.value.trim();
      setError("uc-name", validateName(v));
      if (titleEl && !titleEl.dataset.touched) {
        // human-title-ize: split kebab, capitalize, join with em-dash for last word
        var parts = v.split("-").filter(Boolean);
        if (parts.length) {
          var title = parts.map(function (p) {
            return p.charAt(0).toUpperCase() + p.slice(1);
          }).join(" ");
          titleEl.value = title;
        }
      }
      if (personaEl && !personaEl.dataset.touched && v) {
        var slug = v.split("-")[0] || v;
        personaEl.value = "u-" + slug + "-l";
      }
    });
    if (titleEl) titleEl.addEventListener("input", function () { titleEl.dataset.touched = "1"; });
    if (personaEl) personaEl.addEventListener("input", function () { personaEl.dataset.touched = "1"; });
  }

  function wireArchetypeCards() {
    var cards = document.querySelectorAll(".archetype-card");
    cards.forEach(function (card) {
      card.addEventListener("click", function (e) {
        e.preventDefault();
        var arch = card.getAttribute("data-archetype");
        formState.archetype = arch;
        cards.forEach(function (c) { c.classList.remove("is-selected"); });
        card.classList.add("is-selected");
        var radio = card.querySelector('input[type="radio"]');
        if (radio) radio.checked = true;
        // Apply defaults to step 3+ fields if blank
        applyArchetypeDefaults(arch);
        // Show only the matching arch-fields block in step 3
        document.querySelectorAll('[data-arch-fields]').forEach(function (b) {
          b.classList.toggle("hidden", b.getAttribute("data-arch-fields") !== arch);
        });
        var lbl = document.getElementById("step3-archetype-label");
        if (lbl) lbl.textContent = arch;
      });
    });
  }

  function applyArchetypeDefaults(arch) {
    var d = defaultsForArchetype(arch);
    function setIfBlank(id, val) {
      var el = document.getElementById(id);
      if (el && !el.value) el.value = val;
    }
    setIfBlank("uc-rate", d.rate);
    setIfBlank("ev-spec", d.evaluator_spec);
    setIfBlank("al-condition", d.alert_condition.replace(/<name>/g, document.getElementById("uc-name").value.trim() || "<name>"));
    var sev = document.getElementById("uc-severity");
    if (sev && !sev.dataset.touched) sev.value = d.severity;
    var ek = document.getElementById("ev-kind");
    if (ek && !ek.dataset.touched) ek.value = d.evaluator_kind;

    // Evaluator + alert names follow from name + archetype
    var nm = document.getElementById("uc-name").value.trim();
    if (nm) {
      var evName = nm + "." + arch.replace(/-/g, "_") + "_signal";
      var alName = nm + ".detection";
      var evEl = document.getElementById("ev-name");
      var alEl = document.getElementById("al-name");
      if (evEl && !evEl.dataset.touched) evEl.value = evName;
      if (alEl && !alEl.dataset.touched) alEl.value = alName;
    }
  }

  function wireCenterpieceToggle() {
    var cp = document.getElementById("uc-centerpiece");
    if (!cp) return;
    var update = function () {
      formState.centerpiece = cp.checked;
      var fields = document.getElementById("slo-fields");
      var note = document.getElementById("slo-skip-note");
      if (fields) fields.classList.toggle("hidden", !cp.checked);
      if (note) note.classList.toggle("hidden", cp.checked);
    };
    cp.addEventListener("change", update);
    update();
  }

  function wireTouched() {
    ["uc-severity", "ev-kind", "ev-name", "al-name"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", function () { el.dataset.touched = "1"; });
      if (el && el.tagName === "SELECT") el.addEventListener("change", function () { el.dataset.touched = "1"; });
    });
  }

  function wireNav() {
    document.getElementById("back-btn").addEventListener("click", function () {
      goToStep(formState.step - 1);
    });
    document.getElementById("next-btn").addEventListener("click", function () {
      if (formState.step === TOTAL_STEPS) {
        // re-render in case form changed
        renderReview();
        return;
      }
      if (!validateCurrentStep()) return;
      goToStep(formState.step + 1);
    });
    // Prevent form submission via Enter
    document.getElementById("usecase-form").addEventListener("submit", function (e) {
      e.preventDefault();
    });
  }

  function wireReviewActions() {
    var copy = document.getElementById("copy-btn");
    var dl = document.getElementById("download-btn");
    if (copy) copy.addEventListener("click", function () {
      var text = document.getElementById("yaml-out").textContent;
      copyToClipboard(text, copy);
    });
    if (dl) dl.addEventListener("click", function () {
      var text = document.getElementById("yaml-out").textContent;
      var name = (document.getElementById("uc-name").value.trim()) || "use-case";
      downloadYaml(text, name);
    });
  }

  // ---- Boot ----------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    wireBasicsAutoPrefill();
    wireArchetypeCards();
    wireCenterpieceToggle();
    wireTouched();
    wireNav();
    wireReviewActions();
    goToStep(1);
  });

  // Expose helpers for testing in the browser console
  window.__usecaseWizard = {
    validateName: validateName,
    defaultsForArchetype: defaultsForArchetype,
    generateYaml: generateYaml,
    copyToClipboard: copyToClipboard,
    downloadYaml: downloadYaml,
    goToStep: goToStep,
    collectFormData: collectFormData,
    formState: formState,
  };
})();
