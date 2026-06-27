/* Tablero de Oleaje — SPA web (pywebview) */

const ICONS = {
  analizar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/></svg>`,
  modelar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 15c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/><path d="M2 19c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/></svg>`,
  ver: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/></svg>`,
};

const WIZARDS = {
  analizar: {
    titulo: "Analizar oleaje en un punto",
    pasos: [
      { id: "origen", titulo: "Origen" },
      { id: "revision", titulo: "Revisión" },
      { id: "tablero", titulo: "Tablero" },
    ],
  },
  modelar: {
    titulo: "Modelar propagación con SWAN",
    pasos: [
      { id: "malla", titulo: "Malla" },
      { id: "bati", titulo: "Batimetría" },
      { id: "borde", titulo: "Borde" },
      { id: "nido", titulo: "Nido" },
      { id: "correr", titulo: "Correr" },
      { id: "mapas", titulo: "Mapas" },
    ],
  },
  ver: {
    titulo: "Ver corrida SWAN",
    pasos: [
      { id: "carpeta", titulo: "Carpeta" },
      { id: "tipo", titulo: "Tipo" },
      { id: "generar", titulo: "Generar" },
    ],
  },
};

const state = {
  vista: "inicio",
  wizard: null,
  step: 0,
  ctx: {},
  busy: false,
  log: "",
  tableroGenerado: false,
  productoGenerado: false,
  swanCorrido: false,
  swanOk: false,
};

const main = document.getElementById("main");
const windowEl = document.getElementById("window");

function api() {
  return window.pywebview?.api;
}

async function py(fn, ...args) {
  const a = api();
  if (!a || typeof a[fn] !== "function") {
    console.warn("API no disponible:", fn);
    return null;
  }
  return await a[fn](...args);
}

const taskWaiters = {};

window.dispatchPyEvent = function (payload) {
  const { event, data } = payload;
  if (event === "log") appendLog(data.msg);
  if (event === "progress") setProgress(data.i, data.n);
  if (event === "task_start") setBusy(true, true);
  if (event === "task_done") {
    setBusy(false);
    const w = taskWaiters[data.id];
    if (w) { w(data); delete taskWaiters[data.id]; }
  }
};

function waitTask(id) {
  return new Promise((resolve) => { taskWaiters[id] = resolve; });
}

function setBusy(on, indeterminate = false) {
  state.busy = on;
  const bar = document.querySelector(".progress-wrap");
  const inner = document.querySelector(".progress-bar");
  if (!bar) return;
  bar.classList.toggle("visible", on);
  if (inner) {
    inner.classList.toggle("indeterminate", on && indeterminate);
    if (!on) inner.style.width = "0%";
  }
  document.querySelectorAll(".btn.primary").forEach((b) => {
    b.disabled = on;           // deshabilita al ocupar y RE-HABILITA al terminar
  });
}

function setProgress(i, n) {
  const bar = document.querySelector(".progress-wrap");
  const inner = document.querySelector(".progress-bar");
  if (!bar || !inner) return;
  bar.classList.add("visible");
  inner.classList.remove("indeterminate");
  inner.style.width = `${Math.round(((i + 1) / n) * 100)}%`;
}

function setStatus(text, kind = "listo") {
  const el = document.querySelector(".status-bar");
  if (!el) return;
  el.textContent = text;
  el.className = "status-bar" + (kind === "proc" ? " processing" : kind === "err" ? " error" : "");
}

function appendLog(msg) {
  state.log += msg + (msg.endsWith("\n") ? "" : "\n");
  const pre = document.querySelector(".log-pre");
  if (pre) {
    pre.textContent = state.log;
    pre.scrollTop = pre.scrollHeight;
  }
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

function renderStepper(pasos, step) {
  return pasos.map((p, i) => {
    const cls = i < step ? "done" : i === step ? "active" : "";
    const line = i < pasos.length - 1
      ? `<div class="step-line ${i < step ? "done" : ""}"></div>` : "";
    const label = p.titulo.length > 10 ? p.titulo.slice(0, 9) + "…" : p.titulo;
    const num = i < step ? "✓" : i + 1;
    return `<div class="step-item ${cls}"><div class="step-node">
      <div class="step-circle">${num}</div>
      <div class="step-label">${esc(label)}</div>
    </div></div>${line}`;
  }).join("");
}

function renderInicio() {
  state.vista = "inicio";
  state.wizard = null;
  updateNav();
  main.innerHTML = `
    <h2 class="hero-title">¿Qué quieres hacer?</h2>
    <p class="hero-sub">Elige un flujo guiado o abre las herramientas sueltas.</p>
    <div class="cards">
      <article class="card analizar" data-wizard="analizar">
        <div class="card-head">
          <div class="card-icon">${ICONS.analizar}</div>
          <h3>Analizar oleaje<br>en un punto</h3>
        </div>
        <p>Datos propios o ERA5 → curvas, régimen extremo y espectro.</p>
        <span class="card-link">Empezar →</span>
      </article>
      <article class="card modelar" data-wizard="modelar">
        <div class="card-head">
          <div class="card-icon">${ICONS.modelar}</div>
          <h3>Modelar propagación<br>con SWAN</h3>
        </div>
        <p>Malla → batimetría → borde → correr → mapas.</p>
        <span class="card-link">Empezar →</span>
      </article>
      <article class="card ver" data-wizard="ver">
        <div class="card-head">
          <div class="card-icon">${ICONS.ver}</div>
          <h3>Ver una corrida<br>SWAN ya hecha</h3>
        </div>
        <p>Graficar mapas o video desde una carpeta existente.</p>
        <span class="card-link">Empezar →</span>
      </article>
    </div>
    <footer class="footer">
      <span>Creado por Javier Tarrazón</span>
      <button type="button" class="btn link" id="go-avanzado">Herramientas sueltas →</button>
    </footer>`;
  main.querySelectorAll(".card").forEach((c) =>
    c.addEventListener("click", () => startWizard(c.dataset.wizard)));
  document.getElementById("go-avanzado").onclick = renderAvanzado;
}

function startWizard(id) {
  state.wizard = id;
  state.step = 0;
  state.ctx = id === "modelar" ? { dominios: [{}] } : {};
  state.log = "";
  state.tableroGenerado = false;
  state.productoGenerado = false;
  state.swanCorrido = false;
  state.swanOk = false;
  renderWizard();
}

function renderWizard() {
  state.vista = "wizard";
  updateNav();
  const w = WIZARDS[state.wizard];
  const paso = w.pasos[state.step];
  setStatus("Listo.");
  main.innerHTML = `
    <h2 class="hero-title" style="font-size:22px">${esc(w.titulo)}</h2>
    <div class="stepper">${renderStepper(w.pasos, state.step)}</div>
    <p class="hint">Paso ${state.step + 1} de ${w.pasos.length}: ${esc(paso.titulo)}</p>
    <div class="progress-wrap"><div class="progress-bar"></div></div>
    <div class="status-bar">Listo.</div>
    <div id="step-body"></div>
    <div class="log-panel hidden" id="log-panel"><pre class="log-pre"></pre></div>
    <div class="wizard-foot">
      <button type="button" class="btn secondary" id="wiz-home">← Inicio</button>
      <div class="wizard-foot-right">
        <button type="button" class="btn secondary" id="wiz-back" ${state.step === 0 ? "disabled" : ""}>Atrás</button>
        <button type="button" class="btn primary" id="wiz-next">${state.step === w.pasos.length - 1 ? "Finalizar" : "Siguiente →"}</button>
      </div>
    </div>`;
  document.getElementById("wiz-home").onclick = renderInicio;
  document.getElementById("wiz-back").onclick = () => { state.step--; renderWizard(); };
  document.getElementById("wiz-next").onclick = wizardNext;
  renderStepContent(paso.id);
}

async function wizardNext() {
  const ok = await validateStep();
  if (!ok) return;
  collectStep();
  const w = WIZARDS[state.wizard];
  if (state.step >= w.pasos.length - 1) {
    renderInicio();
    return;
  }
  state.step++;
  if (state.wizard === "analizar" && w.pasos[state.step].id === "revision") {
    await runRevision();
  }
  if (state.wizard === "ver" && w.pasos[state.step].id === "tipo") {
    await runDetectTipo();
  }
  renderWizard();
}

function showLog() {
  document.getElementById("log-panel")?.classList.remove("hidden");
}

function renderStepContent(id) {
  const body = document.getElementById("step-body");
  if (!body) return;

  if (state.wizard === "analizar") {
    if (id === "origen") body.innerHTML = stepAnalizarOrigen();
    if (id === "revision") body.innerHTML = stepAnalizarRevision();
    if (id === "tablero") body.innerHTML = stepAnalizarTablero();
    bindAnalizar(id);
  }
  if (state.wizard === "modelar") {
    body.innerHTML = stepModelar(id);
    bindModelar(id);
  }
  if (state.wizard === "ver") {
    body.innerHTML = stepVer(id);
    bindVer(id);
  }
}

/* --- ANALIZAR --- */
function stepAnalizarOrigen() {
  const c = state.ctx;
  return `<div class="form-card">
    <label class="radio"><input type="radio" name="modo" value="archivo" ${c.modo !== "era5" ? "checked" : ""}/> Tengo un archivo (.mat / .csv / .nc)</label>
    <div class="field-row" style="margin-left:20px;margin-bottom:12px">
      <input type="text" id="ruta-arch" readonly placeholder="Ningún archivo" value="${esc(c.ruta_datos || "")}" style="flex:1"/>
      <button type="button" class="btn secondary" id="pick-arch">Archivo…</button>
    </div>
    <label class="radio"><input type="radio" name="modo" value="era5" ${c.modo === "era5" ? "checked" : ""}/> Descargar de ERA5</label>
    <div id="era5-fields" class="${c.modo === "era5" ? "" : "hidden"}" style="margin-left:20px">
      <div class="field-row">
        <label class="field">Latitud<input id="era5-lat" value="${esc(c.era5?.lat ?? "-37.0")}"/></label>
        <label class="field">Longitud<input id="era5-lon" value="${esc(c.era5?.lon ?? "-73.5")}"/></label>
      </div>
      <div class="field-row">
        <label class="field">Inicio<input id="era5-ini" value="${esc(c.era5?.inicio ?? "2024-07-28")}"/></label>
        <label class="field">Fin<input id="era5-fin" value="${esc(c.era5?.fin ?? "2024-07-29")}"/></label>
      </div>
      <label class="radio"><input type="checkbox" id="era5-viento" ${c.era5?.viento !== false ? "checked" : ""}/> Incluir viento</label>
      <button type="button" class="btn primary" id="era5-dl" style="margin-top:10px">Descargar serie ERA5</button>
      <p class="hint ${c.era5_descargado ? "ok" : ""}" id="era5-hint">${c.era5_descargado ? "Serie descargada." : ""}</p>
    </div>
  </div>`;
}

function bindAnalizar(id) {
  if (id === "origen") {
    document.querySelectorAll('input[name="modo"]').forEach((r) =>
      r.onchange = () => {
        document.getElementById("era5-fields").classList.toggle("hidden", r.value !== "era5" || !r.checked);
        if (r.checked) state.ctx.modo = r.value;
      });
    document.getElementById("pick-arch").onclick = async () => {
      const r = await py("elegir_archivo", "oleaje");
      if (r) { document.getElementById("ruta-arch").value = r; state.ctx.ruta_datos = r; }
    };
    document.getElementById("era5-dl").onclick = async () => {
      collectEra5Fields();
      const e = state.ctx.era5;
      showLog();
      setStatus("Descargando ERA5…", "proc");
      const start = await py("descargar_era5", e.lat, e.lon, e.inicio, e.fin, e.viento, false);
      if (!start?.ok) { setStatus(start?.error || "Error", "err"); return; }
      const done = await waitTask("era5");
      if (done.ok) {
        state.ctx.ruta_datos = done.result.ruta;
        state.ctx.era5_descargado = true;
        appendLog(done.result.log || "");
        document.getElementById("era5-hint").textContent = "Serie descargada: " + done.result.ruta;
        document.getElementById("era5-hint").classList.add("ok");
        setStatus("Listo.");
      } else {
        appendLog(done.error);
        setStatus("Error al descargar.", "err");
      }
    };
  }
  if (id === "tablero") {
    document.getElementById("gen-tablero").onclick = async () => {
      showLog();
      setStatus("Generando tablero…", "proc");
      const start = await py("generar_tablero_oleaje", state.ctx.ruta_datos);
      if (!start?.ok) return;
      const done = await waitTask("tablero_oleaje");
      if (done.ok) {
        state.tableroGenerado = true;
        appendLog("Resultado: " + done.result.ruta);
        setStatus("Listo.");
      } else {
        appendLog(done.error);
        setStatus("Error.", "err");
      }
    };
  }
}

function collectEra5Fields() {
  state.ctx.modo = document.querySelector('input[name="modo"]:checked')?.value || "archivo";
  state.ctx.era5 = {
    lat: document.getElementById("era5-lat")?.value,
    lon: document.getElementById("era5-lon")?.value,
    inicio: document.getElementById("era5-ini")?.value,
    fin: document.getElementById("era5-fin")?.value,
    viento: document.getElementById("era5-viento")?.checked,
  };
}

function stepAnalizarRevision() {
  return `<div class="form-card"><pre class="log-pre">${esc(state.ctx.reporte || "Cargando…")}</pre></div>`;
}

function stepAnalizarTablero() {
  return `<div class="form-card">
    <p>Genera el tablero de curvas y se abrirá al terminar.</p>
    <button type="button" class="btn primary" id="gen-tablero">Generar tablero</button>
  </div>`;
}

async function runRevision() {
  const res = await py("revision_datos", state.ctx.ruta_datos);
  state.ctx.reporte = res?.reporte || "";
  state.ctx.revision_ok = res?.ok;
  state.ctx.revision_motivo = res?.motivo || "";
}

async function validateStep() {
  if (state.wizard === "analizar") {
    if (state.step === 0) {
      const modo = document.querySelector('input[name="modo"]:checked')?.value || state.ctx.modo || "archivo";
      state.ctx.modo = modo;
      if (modo === "archivo") {
        const r = document.getElementById("ruta-arch")?.value || state.ctx.ruta_datos;
        if (!r) { alert("Selecciona un archivo."); return false; }
        state.ctx.ruta_datos = r;
      } else {
        if (!state.ctx.era5_descargado) { alert("Descarga la serie ERA5 primero."); return false; }
      }
      return true;
    }
    if (state.step === 1) {
      if (!state.ctx.revision_ok) { alert(state.ctx.revision_motivo || "Revisión no superada."); return false; }
      return true;
    }
    if (state.step === 2) {
      if (!state.tableroGenerado) { alert("Genera el tablero y espera a que termine."); return false; }
      return true;
    }
  }

  if (state.wizard === "modelar") {
    const id = WIZARDS.modelar.pasos[state.step].id;
    return validateModelar(id);
  }

  if (state.wizard === "ver") {
    const id = WIZARDS.ver.pasos[state.step].id;
    if (id === "carpeta") {
      const d = document.getElementById("ver-carpeta")?.value || state.ctx.carpeta;
      if (!d) { alert("Elige una carpeta."); return false; }
      state.ctx.carpeta = d;
      return true;
    }
    if (id === "tipo") return true;
    if (id === "generar") {
      if (!state.productoGenerado) { alert("Genera el producto primero."); return false; }
      return true;
    }
  }
  return true;
}

function collectStep() {
  if (state.wizard === "analizar" && state.step === 0 && state.ctx.modo === "era5") collectEra5Fields();
  if (state.wizard === "modelar") collectModelar(WIZARDS.modelar.pasos[state.step].id);
  if (state.wizard === "ver" && state.step === 0) {
    state.ctx.carpeta = document.getElementById("ver-carpeta")?.value || state.ctx.carpeta;
  }
  if (state.wizard === "ver" && state.step === 1) {
    state.ctx.utm_x = document.getElementById("utm-x")?.value;
    state.ctx.utm_y = document.getElementById("utm-y")?.value;
    try {
      state.ctx.utm_large = [parseFloat(state.ctx.utm_x), parseFloat(state.ctx.utm_y)];
    } catch { state.ctx.utm_large = null; }
  }
}

/* --- MODELAR --- */
function mallaFields(prefix, vals = {}) {
  const v = (k, d) => esc(vals[k] ?? d);
  return `<div class="field-row">
    <label class="field">Lat centro<input id="${prefix}-lat" value="${v("lat", "-32.97")}"/></label>
    <label class="field">Lon centro<input id="${prefix}-lon" value="${v("lon", "-71.55")}"/></label>
  </div>
  <div class="field-row">
    <label class="field">Ancho [km]<input id="${prefix}-ancho" value="${v("ancho", "8")}"/></label>
    <label class="field">Alto [km]<input id="${prefix}-alto" value="${v("alto", "8")}"/></label>
    <label class="field">Celda [m]<input id="${prefix}-celda" value="${v("celda", "100")}"/></label>
  </div>
  <button type="button" class="btn secondary" id="${prefix}-calc">Calcular malla</button>
  <p class="hint ${vals.resumen ? "ok" : ""}" id="${prefix}-hint">${esc(vals.resumen || "")}</p>`;
}

function stepModelar(id) {
  const dom = state.ctx.dominios?.[0] || {};
  if (id === "malla") return `<div class="form-card">${mallaFields("malla", dom.malla_ui || {})}</div>`;
  if (id === "bati") return `<div class="form-card">
    <p>Necesitas un .bot que cubra la malla.</p>
    <button type="button" class="btn primary" id="bati-dl">Descargar batimetría automática</button>
    <button type="button" class="btn secondary" id="bati-pick">Usar .bot propio…</button>
    <p class="hint" id="bati-hint">${esc(dom.bot || "")}</p>
  </div>`;
  if (id === "borde") return `<div class="form-card">
    <div class="field-row">
      <label class="field">Hs [m]<input id="b-hs" value="${dom.borde_ui?.hs ?? "3.0"}"/></label>
      <label class="field">Tp [s]<input id="b-per" value="${dom.borde_ui?.per ?? "12.0"}"/></label>
      <label class="field">Dir [°]<input id="b-dir" value="${dom.borde_ui?.dir ?? "290"}"/></label>
      <label class="field">Disp [°]<input id="b-dd" value="${dom.borde_ui?.dd ?? "20"}"/></label>
    </div>
    <div class="check-row">Lados:
      ${["N","S","E","W"].map(s => `<label><input type="checkbox" class="b-lado" value="${s}" ${["N","W"].includes(s)?"checked":""}/> ${s}</label>`).join("")}
    </div>
    <button type="button" class="btn secondary" id="b-derivar" style="margin-top:12px">Derivar de ERA5/serie…</button>
  </div>`;
  if (id === "nido") return `<div class="form-card">
    <label class="radio"><input type="checkbox" id="nido-on" ${state.ctx.nido_activo ? "checked" : ""}/> Agregar dominio anidado (nido)</label>
    <div id="nido-box" class="${state.ctx.nido_activo ? "" : "hidden"}">
      ${mallaFields("nido", state.ctx.dominios?.[1]?.malla_ui || { lat:"-36.97", lon:"-73.15", ancho:"9", alto:"10", celda:"200" })}
      <button type="button" class="btn secondary" id="nido-bati">Batimetría del nido</button>
      <button type="button" class="btn secondary" id="nido-pick">.bot propio…</button>
      <p class="hint" id="nido-bot-hint">${esc(state.ctx.dominios?.[1]?.bot || "")}</p>
    </div>
  </div>`;
  if (id === "correr") return `<div class="form-card">
    <label class="field">Nombre del caso<input id="caso-nom" value="${esc(state.ctx.nombre_caso || "MiCaso")}"/></label>
    <button type="button" class="btn primary" id="swan-run">Generar .swn y correr</button>
    <p class="hint ${state.swanCorrido ? (state.swanOk ? "ok" : "") : ""}" id="swan-hint">${state.swanCorrido ? (state.swanOk ? "SWAN terminó bien." : "SWAN terminó con errores.") : ""}</p>
  </div>`;
  if (id === "mapas") return `<div class="form-card">
    <p>Genera el tablero de mapas de la corrida.</p>
    <button type="button" class="btn primary" id="gen-mapas">Generar mapas</button>
  </div>`;
  return "";
}

function bindModelar(id) {
  if (id === "malla") {
    document.getElementById("malla-calc").onclick = () => calcMalla("malla", 0);
  }
  if (id === "bati") {
    document.getElementById("bati-dl").onclick = async () => {
      if (!state.ctx.carpeta_caso) {
        const d = await py("elegir_carpeta", "swan");
        if (!d) return;
        state.ctx.carpeta_caso = d;
      }
      const dom = state.ctx.dominios[0];
      if (!dom.malla) { alert("Calcula la malla primero."); return; }
      showLog();
      setStatus("Generando batimetría…", "proc");
      const start = await py("generar_batimetria", JSON.stringify(dom.malla), dom.zona_utm, state.ctx.carpeta_caso);
      if (!start?.ok) return;
      const done = await waitTask("batimetria");
      if (done.ok) {
        dom.bot = done.result.ruta;
        appendLog(done.result.log);
        document.getElementById("bati-hint").textContent = done.result.ruta;
        setStatus("Listo.");
      } else { appendLog(done.error); setStatus("Error.", "err"); }
    };
    document.getElementById("bati-pick").onclick = async () => {
      const d = await py("elegir_carpeta", "swan");
      if (d) state.ctx.carpeta_caso = d;
      const r = await py("elegir_archivo", "bot");
      if (r) {
        state.ctx.dominios[0].bot = r;
        document.getElementById("bati-hint").textContent = r;
      }
    };
  }
  if (id === "borde") {
    document.getElementById("b-derivar").onclick = async () => {
      const r = await py("elegir_archivo", "serie");
      if (!r) return;
      const cond = await askBordeCondicion();
      if (!cond) return;
      const res = await py("derivar_borde", r, cond.modo, cond.tr);
      if (res?.ok) {
        document.getElementById("b-hs").value = res.hs;
        document.getElementById("b-per").value = res.per;
        document.getElementById("b-dir").value = res.dir;
        showLog();
        appendLog("Borde derivado — " + (res.descripcion || ""));
      } else alert(res?.error || "Error");
    };
  }
  if (id === "nido") {
    document.getElementById("nido-on").onchange = (e) => {
      state.ctx.nido_activo = e.target.checked;
      document.getElementById("nido-box").classList.toggle("hidden", !e.target.checked);
    };
    document.getElementById("nido-calc")?.addEventListener("click", () => calcMalla("nido", 1));
    document.getElementById("nido-bati")?.addEventListener("click", async () => {
      if (!state.ctx.dominios[1]?.malla) { alert("Calcula malla del nido."); return; }
      showLog();
      const start = await py("generar_batimetria", JSON.stringify(state.ctx.dominios[1].malla),
        state.ctx.dominios[1].zona_utm, state.ctx.carpeta_caso, "bati_nido.bot");
      if (!start?.ok) return;
      const done = await waitTask("batimetria");
      if (done.ok) {
        state.ctx.dominios[1].bot = done.result.ruta;
        document.getElementById("nido-bot-hint").textContent = done.result.ruta;
      }
    });
    document.getElementById("nido-pick")?.addEventListener("click", async () => {
      const r = await py("elegir_archivo", "bot");
      if (r) {
        if (!state.ctx.dominios[1]) state.ctx.dominios[1] = {};
        state.ctx.dominios[1].bot = r;
        document.getElementById("nido-bot-hint").textContent = r;
      }
    });
  }
  if (id === "correr") {
    document.getElementById("swan-run").onclick = runSwan;
  }
  if (id === "mapas") {
    document.getElementById("gen-mapas").onclick = async () => {
      showLog();
      setStatus("Generando mapas…", "proc");
      const start = await py("generar_mapas_swan", state.ctx.carpeta_resultado || state.ctx.carpeta_caso);
      if (!start?.ok) return;
      const done = await waitTask("mapas_swan");
      if (done.ok) {
        state.productoGenerado = true;
        appendLog("Resultado: " + done.result.ruta);
        setStatus("Listo.");
      } else { appendLog(done.error); setStatus("Error.", "err"); }
    };
  }
}

async function calcMalla(prefix, domIdx) {
  const lat = document.getElementById(`${prefix}-lat`).value;
  const lon = document.getElementById(`${prefix}-lon`).value;
  const ancho = document.getElementById(`${prefix}-ancho`).value;
  const alto = document.getElementById(`${prefix}-alto`).value;
  const celda = document.getElementById(`${prefix}-celda`).value;
  const res = await py("calcular_malla", lat, lon, ancho, alto, celda);
  if (!res?.ok) { alert(res?.error || "Error"); return; }
  if (!state.ctx.dominios[domIdx]) state.ctx.dominios[domIdx] = {};
  state.ctx.dominios[domIdx].malla = res.malla;
  state.ctx.dominios[domIdx].zona_utm = res.malla.zona_utm;
  state.ctx.dominios[domIdx].malla_ui = { lat, lon, ancho, alto, celda, resumen: res.resumen };
  document.getElementById(`${prefix}-hint`).textContent = res.resumen;
  document.getElementById(`${prefix}-hint`).classList.add("ok");
}

function collectModelar(id) {
  const dom = state.ctx.dominios[0];
  if (id === "borde") {
    const lados = [...document.querySelectorAll(".b-lado:checked")].map((c) => c.value);
    const hs = parseFloat(document.getElementById("b-hs").value);
    const per = parseFloat(document.getElementById("b-per").value);
    const dir = parseFloat(document.getElementById("b-dir").value);
    const dd = parseFloat(document.getElementById("b-dd").value);
    dom.bordes = lados.map((s) => ({ lado: s, hs, per, dir, dd }));
    dom.borde_ui = { hs, per, dir, dd };
  }
  if (id === "nido") {
    state.ctx.nido_activo = document.getElementById("nido-on")?.checked;
    if (!state.ctx.nido_activo && state.ctx.dominios.length > 1) {
      state.ctx.dominios = [state.ctx.dominios[0]];
    }
  }
  if (id === "correr") {
    state.ctx.nombre_caso = document.getElementById("caso-nom")?.value || "MiCaso";
    state.ctx.carpeta_resultado = state.ctx.carpeta_caso;
  }
}

async function validateModelar(id) {
  if (id === "malla") {
    if (!state.ctx.dominios[0]?.malla) { alert("Calcula la malla."); return false; }
    return true;
  }
  if (id === "bati") {
    if (!state.ctx.dominios[0]?.bot) { alert("Genera o elige batimetría."); return false; }
    return true;
  }
  if (id === "borde") {
    collectModelar("borde");
    const b = state.ctx.dominios[0].bordes;
    if (!b?.length) { alert("Elige al menos un lado de borde."); return false; }
    return true;
  }
  if (id === "nido") {
    collectModelar("nido");
    if (state.ctx.nido_activo) {
      const n = state.ctx.dominios[1];
      if (!n?.malla) { alert("Calcula malla del nido o desactívalo."); return false; }
      if (!n?.bot) { alert("Batimetría del nido requerida."); return false; }
      const val = await py("validar_nido", JSON.stringify(state.ctx.dominios[0].malla), JSON.stringify(n.malla));
      if (val?.errores?.length) { alert(val.errores.join("\n")); return false; }
    } else if (state.ctx.dominios.length > 1) {
      state.ctx.dominios = [state.ctx.dominios[0]];
    }
    return true;
  }
  if (id === "correr") {
    if (!state.swanCorrido) { alert("Corre SWAN primero."); return false; }
    if (!state.swanOk) { alert("SWAN falló; revisa el log."); return false; }
    return true;
  }
  if (id === "mapas") {
    if (!state.productoGenerado) { alert("Genera los mapas."); return false; }
    return true;
  }
  return true;
}

async function runSwan() {
  collectModelar("borde");
  collectModelar("nido");
  const val = await py("validar_correr_swan", JSON.stringify(state.ctx));
  if (val?.errores?.length) { alert(val.errores.join("\n\n")); return; }
  if (val?.avisos?.length) {
    const ok = await askConfirm(val.avisos.join("\n\n") + "\n\n¿Continuar?");
    if (!ok) return;
  }
  showLog();
  setStatus("Corriendo SWAN…", "proc");
  const nom = document.getElementById("caso-nom")?.value || "MiCaso";
  const start = await py("escribir_y_correr_swan", JSON.stringify(state.ctx), nom);
  if (!start?.ok) { alert(start?.error); return; }
  const done = await waitTask("swan");
  state.swanCorrido = true;
  if (done.ok) {
    state.swanOk = done.result.ok;
    appendLog(done.result.log);
    document.getElementById("swan-hint").textContent = state.swanOk ? "SWAN terminó bien." : "SWAN terminó con errores.";
    setStatus(state.swanOk ? "Listo." : "Error.", state.swanOk ? "listo" : "err");
  } else {
    state.swanOk = false;
    appendLog(done.error);
    setStatus("Error.", "err");
  }
}

/* --- VER --- */
function stepVer(id) {
  if (id === "carpeta") return `<div class="form-card">
    <label class="field">Carpeta SWAN
      <div class="field-row">
        <input id="ver-carpeta" readonly value="${esc(state.ctx.carpeta || "")}"/>
        <button type="button" class="btn secondary" id="ver-pick">Carpeta…</button>
      </div>
    </label>
    <p class="hint" id="ver-casos">${esc(state.ctx.casos_txt || "")}</p>
  </div>`;
  if (id === "tipo") return `<div class="form-card">
    <pre class="log-pre">${esc(state.ctx.tipo_resumen || "")}</pre>
    <div class="field-row" style="margin-top:12px">
      <label class="field">UTM X<input id="utm-x" value="${state.ctx.utm_x ?? "620494"}"/></label>
      <label class="field">UTM Y<input id="utm-y" value="${state.ctx.utm_y ?? "5876451"}"/></label>
    </div>
  </div>`;
  if (id === "generar") {
    const prod = state.ctx.nonst ? "video" : "tablero de mapas";
    return `<div class="form-card">
      <p>Genera el ${prod} y se abrirá al terminar.</p>
      <button type="button" class="btn primary" id="ver-gen">Generar ${prod}</button>
    </div>`;
  }
  return "";
}

function bindVer(id) {
  if (id === "carpeta") {
    document.getElementById("ver-pick").onclick = async () => {
      const d = await py("elegir_carpeta", "swan");
      if (d) {
        document.getElementById("ver-carpeta").value = d;
        state.ctx.carpeta = d;
        const info = await py("info_carpeta_swan", d);
        state.ctx.casos_txt = info?.casos?.length
          ? "Casos: " + info.casos.join(", ") : "Sin .swn detectados.";
        document.getElementById("ver-casos").textContent = state.ctx.casos_txt;
      }
    };
  }
  if (id === "generar") {
    document.getElementById("ver-gen").onclick = async () => {
      showLog();
      setStatus("Generando…", "proc");
      const start = await py("generar_producto_ver", JSON.stringify(state.ctx));
      if (!start?.ok) return;
      const done = await waitTask("ver_producto");
      if (done.ok) {
        state.productoGenerado = true;
        appendLog("Resultado: " + done.result.ruta);
        setStatus("Listo.");
      } else { appendLog(done.error); setStatus("Error.", "err"); }
    };
  }
}

async function runDetectTipo() {
  const info = await py("info_carpeta_swan", state.ctx.carpeta);
  state.ctx.nonst = info?.nonst;
  state.ctx.tipo_resumen = info?.resumen || "";
}

/* --- AVANZADO --- */
function renderAvanzado() {
  state.vista = "avanzado";
  state.wizard = null;
  updateNav();
  main.innerHTML = `
    <h2 class="hero-title" style="font-size:22px">Modo avanzado</h2>
    <p class="hero-sub">Serie → curvas · SWAN estacionaria → mapas · no estacionaria → video.</p>
    <div class="form-card">
      <div class="field-row">
        <input type="text" id="adv-ruta" placeholder="Archivo o carpeta SWAN" style="flex:1"/>
        <button type="button" class="btn secondary" id="adv-arch">Archivo…</button>
        <button type="button" class="btn secondary" id="adv-dir">Carpeta…</button>
      </div>
      <div class="field-row" style="margin-top:12px">
        <button type="button" class="btn primary" id="adv-crear">Crear</button>
        <button type="button" class="btn secondary" id="adv-swan">Procesar SWAN…</button>
      </div>
      <div class="field-row" style="margin-top:12px">
        <label class="field">UTM X<input id="adv-ux" value="620494"/></label>
        <label class="field">UTM Y<input id="adv-uy" value="5876451"/></label>
      </div>
    </div>
    <div class="progress-wrap"><div class="progress-bar"></div></div>
    <div class="status-bar">Listo.</div>
    <div class="log-panel"><pre class="log-pre"></pre></div>`;
  state.log = "";
  document.getElementById("adv-arch").onclick = async () => {
    const r = await py("elegir_archivo", "oleaje");
    if (r) document.getElementById("adv-ruta").value = r;
  };
  document.getElementById("adv-dir").onclick = async () => {
    const r = await py("elegir_carpeta", "swan");
    if (r) document.getElementById("adv-ruta").value = r;
  };
  document.getElementById("adv-swan").onclick = () => py("abrir_procesar_swan_legacy");
  document.getElementById("adv-crear").onclick = async () => {
    const ruta = document.getElementById("adv-ruta").value;
    if (!ruta) { alert("Selecciona entrada."); return; }
    showLog();
    setStatus("Procesando…", "proc");
    const start = await py("despachar_avanzado", ruta,
      document.getElementById("adv-ux").value,
      document.getElementById("adv-uy").value);
    if (!start?.ok) { alert(start?.error); return; }
    const done = await waitTask("avanzado");
    if (done.ok) {
      appendLog("Resultado: " + done.result.ruta);
      setStatus("Listo.");
    } else {
      appendLog(done.error);
      setStatus("Error.", "err");
    }
  };
}

/* --- Modals --- */
function askBordeCondicion() {
  return new Promise((resolve) => {
    const dlg = document.getElementById("dlg-borde");
    let cancelled = false;
    document.getElementById("borde-cancel").onclick = () => {
      cancelled = true;
      dlg.close();
      resolve(null);
    };
    dlg.onclose = () => {
      if (cancelled) return;
      const modo = dlg.querySelector('input[name="modo"]:checked')?.value;
      const tr = document.getElementById("borde-tr").value;
      resolve({ modo, tr });
    };
    dlg.showModal();
  });
}

function askConfirm(text) {
  return new Promise((resolve) => {
    const dlg = document.getElementById("dlg-confirm");
    let no = false;
    document.getElementById("confirm-text").textContent = text;
    document.getElementById("confirm-no").onclick = () => {
      no = true;
      dlg.close();
      resolve(false);
    };
    dlg.onclose = () => { if (!no) resolve(true); };
    dlg.showModal();
  });
}

function updateNav() {
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active",
      (n.dataset.nav === "inicio" && state.vista === "inicio") ||
      (n.dataset.nav === "avanzado" && state.vista === "avanzado"));
  });
}

function onResize() {
  windowEl.classList.toggle("narrow", window.innerWidth < 720);
}

document.querySelectorAll(".nav-item").forEach((n) => {
  n.onclick = () => {
    if (n.dataset.nav === "inicio") renderInicio();
    if (n.dataset.nav === "avanzado") renderAvanzado();
  };
});

window.addEventListener("resize", onResize);
onResize();
renderInicio();

// pywebview ready
window.addEventListener("pywebviewready", () => console.log("API lista"));
