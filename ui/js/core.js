/* Núcleo compartido — API, estado, eventos, utilidades */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;

  T.ICONS = {
    analizar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/></svg>`,
    modelar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 15c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/><path d="M2 19c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/></svg>`,
    ver: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/></svg>`,
    procesar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="8 5 19 12 8 19 8 5"/></svg>`,
  };

  T.WIZARDS = {
    analizar: {
      titulo: "Analizar oleaje en un punto",
      ayuda: "Carga tu serie o descárgala de ERA5. Dir es convención náutica (de dónde viene el oleaje).",
      pasos: [
        { id: "origen", titulo: "Origen", ayuda: "Archivo local o descarga ERA5 por coordenada. Para Gumbel y climatología hacen falta ≥2 años (730 días). La descarga no se puede cancelar; si se cuelga, cierra y reabre la app." },
        { id: "revision", titulo: "Revisión", ayuda: "Chequeos físicos automáticos y productos disponibles según la duración de los datos." },
        { id: "tablero", titulo: "Tablero", ayuda: "Genera el PNG multipanel. Los paneles omitidos se anotan al pie de la figura." },
      ],
    },
    modelar: {
      titulo: "Modelar propagación con SWAN",
      ayuda: "Dominio UTM desde lat/lon. SWAN necesita un .bot (profundidad por nodo). Dir de borde: convención náutica.",
      pasos: [
        { id: "malla", titulo: "Malla", ayuda: "Define el dominio grande y la carpeta del caso. Usa una plantilla o ajusta lat/lon/tamaño/celda." },
        { id: "nido", titulo: "Nido", ayuda: "Opcional: dominio fino dentro del grande. Debe quedar contenido y con celda más fina." },
        { id: "bati", titulo: "Batimetría", ayuda: "Genera el .bot desde ETOPO (~2 km) o raster/.bot propio. Revisa % tierra antes de avanzar." },
        { id: "borde", titulo: "Borde", ayuda: "Se rellena solo desde ERA5 (centro de la malla) si ya descargaste esa serie; si no, un clic descarga y deriva. Modo auto: oleaje reinante." },
        { id: "correr", titulo: "Correr", ayuda: "Genera .swn y ejecuta SWAN. Si falla, abre la carpeta y revisa .prt/.erf." },
        { id: "mapas", titulo: "Mapas", ayuda: "Tablero de mapas Hs/Tp/Dir/Setup desde la corrida." },
      ],
    },
    ver: {
      titulo: "Ver corrida SWAN",
      ayuda: "Autodetecta estacionaria (mapas) o no estacionaria (video multipanel sincronizado).",
      pasos: [
        { id: "carpeta", titulo: "Carpeta", ayuda: "Carpeta con .swn y salidas BLOCK o .mat temporales." },
        { id: "tipo", titulo: "Tipo", ayuda: "Offset UTM del nodo (0,0) del dominio grande; se infiere del caso si existe meta." },
        { id: "generar", titulo: "Generar", ayuda: "Mapas PNG o video MP4/GIF según el tipo detectado." },
      ],
    },
  };

  T.state = {
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
    prefs: {},
  };

  T.main = () => document.getElementById("main");
  T.windowEl = () => document.getElementById("window");

  T.api = () => window.pywebview?.api;

  T.py = async (fn, ...args) => {
    const a = T.api();
    if (!a || typeof a[fn] !== "function") {
      console.warn("API no disponible:", fn);
      return null;
    }
    try {
      return await a[fn](...args);
    } catch (e) {
      console.error(e);
      T.notify("Error interno: " + (e?.message || e));
      return null;
    }
  };

  const taskWaiters = {};
  const taskRenewals = {};

  window.dispatchPyEvent = function (payload) {
    const { event, data } = payload;
    if (event === "log") {
      T.appendLog(data.msg);
      if (data.msg && /Tramo \d+\/\d+/i.test(data.msg)) {
        T.setStatus(data.msg.trim(), "proc");
      }
      Object.values(taskRenewals).forEach((arm) => arm());
    }
    if (event === "progress") T.setProgress(data.i, data.n);
    if (event === "task_start") T.setBusy(true, true);
    if (event === "task_done") {
      T.setBusy(false);
      const w = taskWaiters[data.id];
      if (w) { w(data); delete taskWaiters[data.id]; delete taskRenewals[data.id]; }
    }
  };

  T.waitTask = (id, timeoutMs = 600000, opts = {}) => {
    const renewOnActivity = Boolean(opts.renewOnActivity);
    const msgTimeout = opts.timeoutMessage || "Tiempo de espera agotado.";
    return new Promise((resolve) => {
      let timer;
      const arm = () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          if (taskWaiters[id]) {
            delete taskWaiters[id];
            delete taskRenewals[id];
            T.setBusy(false);
            resolve({ ok: false, error: msgTimeout });
          }
        }, timeoutMs);
      };
      taskWaiters[id] = (data) => {
        clearTimeout(timer);
        delete taskRenewals[id];
        resolve(data);
      };
      if (renewOnActivity) taskRenewals[id] = arm;
      arm();
    });
  };

  T.diasEntre = (inicio, fin) => {
    const t0 = Date.parse(String(inicio).trim());
    const t1 = Date.parse(String(fin).trim());
    if (Number.isNaN(t0) || Number.isNaN(t1) || t1 < t0) return 1;
    return Math.max(1, Math.round((t1 - t0) / 86400000) + 1);
  };

  setInterval(() => { T.py("poll_eventos").catch(() => {}); }, 150);

  T.setBusy = (on, indeterminate = false) => {
    T.state.busy = on;
    const bar = document.querySelector(".progress-wrap");
    const inner = document.querySelector(".progress-bar");
    if (!bar) return;
    bar.classList.toggle("visible", on);
    if (inner) {
      inner.classList.toggle("indeterminate", on && indeterminate);
      if (!on) inner.style.width = "0%";
    }
    document.querySelectorAll(".btn.primary").forEach((b) => { b.disabled = on; });
  };

  T.setProgress = (i, n) => {
    const bar = document.querySelector(".progress-wrap");
    const inner = document.querySelector(".progress-bar");
    if (!bar || !inner) return;
    bar.classList.add("visible");
    inner.classList.remove("indeterminate");
    inner.style.width = `${Math.round(((i + 1) / n) * 100)}%`;
  };

  T.setStatus = (text, kind = "listo") => {
    const el = document.querySelector(".status-bar");
    if (!el) return;
    el.textContent = text;
    el.className = "status-bar" + (kind === "proc" ? " processing" : kind === "err" ? " error" : "");
  };

  T.appendLog = (msg) => {
    T.state.log += msg + (msg.endsWith("\n") ? "" : "\n");
    const pre = document.querySelector(".log-pre");
    if (pre) {
      pre.textContent = T.state.log;
      pre.scrollTop = pre.scrollHeight;
    }
  };

  T.clearLog = () => {
    T.state.log = "";
    const pre = document.querySelector(".log-pre");
    if (pre) pre.textContent = "";
  };

  T.esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

  T.renderStepper = (pasos, step) => pasos.map((p, i) => {
    const cls = i < step ? "done" : i === step ? "active" : "";
    const line = i < pasos.length - 1
      ? `<div class="step-line ${i < step ? "done" : ""}"></div>` : "";
    const label = p.titulo.length > 10 ? p.titulo.slice(0, 9) + "…" : p.titulo;
    const num = i < step ? "✓" : i + 1;
    return `<div class="step-item ${cls}"><div class="step-node">
      <div class="step-circle">${num}</div>
      <div class="step-label">${T.esc(label)}</div>
    </div></div>${line}`;
  }).join("");

  T.showLog = () => document.getElementById("log-panel")?.classList.remove("hidden");

  T.showPreview = (containerId, imgData, ruta) => {
    const box = document.getElementById(containerId);
    if (!box) return;
    if (!imgData) { box.innerHTML = ""; box.classList.add("hidden"); return; }
    box.classList.remove("hidden");
    box.innerHTML = `
      <div class="preview-panel">
        <img src="${imgData}" alt="Vista previa" class="preview-img"/>
        <div class="preview-actions">
          <button type="button" class="btn secondary btn-sm" data-open="${T.esc(ruta)}">Abrir archivo</button>
          <button type="button" class="btn secondary btn-sm" data-folder="${T.esc(ruta)}">Abrir carpeta</button>
        </div>
      </div>`;
    box.querySelector("[data-open]")?.addEventListener("click", (ev) => {
      T.py("abrir_archivo", ev.target.dataset.open);
    });
    box.querySelector("[data-folder]")?.addEventListener("click", (ev) => {
      T.py("abrir_en_explorador", ev.target.dataset.folder);
    });
  };

  T.guardarPrefs = async () => {
    await T.py("guardar_preferencias", JSON.stringify(T.state.prefs));
  };

  T.cargarPrefs = async () => {
    const res = await T.py("obtener_preferencias");
    if (res?.prefs) T.state.prefs = res.prefs;
  };

  T.persistirSesion = () => {
    if (!T.state.wizard) return;
    T.py("guardar_sesion_wizard", T.state.wizard, T.state.step, JSON.stringify(T.state.ctx));
  };

  T.updateNav = () => {
    document.querySelectorAll(".nav-item").forEach((n) => {
      n.classList.toggle("active",
        (n.dataset.nav === "inicio" && T.state.vista === "inicio") ||
        (n.dataset.nav === "avanzado" && T.state.vista === "avanzado") ||
        (n.dataset.nav === "credenciales" && T.state.vista === "credenciales") ||
        (n.dataset.nav === "cache" && T.state.vista === "cache") ||
        (n.dataset.nav === "acerca" && T.state.vista === "acerca"));
    });
  };

  T.askBordeCondicion = () => new Promise((resolve) => {
    const dlg = document.getElementById("dlg-borde");
    let cancelled = false;
    document.getElementById("borde-cancel").onclick = () => {
      cancelled = true;
      dlg.close();
      resolve(null);
    };
    dlg.onclose = () => {
      if (cancelled) return;
      resolve({
        modo: dlg.querySelector('input[name="modo"]:checked')?.value,
        tr: document.getElementById("borde-tr").value,
      });
    };
    dlg.showModal();
  });

  T.askConfirm = (text) => new Promise((resolve) => {
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

  T.renderWizardShell = () => {
    const w = T.WIZARDS[T.state.wizard];
    const paso = w.pasos[T.state.step];
    T.setStatus("Listo.");
    T.main().innerHTML = `
      <h2 class="hero-title" style="font-size:22px">${T.esc(w.titulo)}</h2>
      <p class="hint wizard-ayuda">${T.esc(paso.ayuda || w.ayuda || "")}</p>
      <div class="stepper">${T.renderStepper(w.pasos, T.state.step)}</div>
      <p class="hint">Paso ${T.state.step + 1} de ${w.pasos.length}: ${T.esc(paso.titulo)}</p>
      <div class="inline-error hidden" id="inline-error"></div>
      <div class="progress-wrap"><div class="progress-bar"></div></div>
      <div class="status-bar">Listo.</div>
      <div id="step-body"></div>
      <div id="preview-box" class="hidden"></div>
      <div class="log-panel hidden" id="log-panel"><pre class="log-pre"></pre></div>
      <div class="wizard-foot">
        <button type="button" class="btn secondary" id="wiz-home">← Inicio</button>
        <div class="wizard-foot-right">
          <button type="button" class="btn secondary" id="wiz-back" ${T.state.step === 0 ? "disabled" : ""}>Atrás</button>
          <button type="button" class="btn primary" id="wiz-next">${T.state.step === w.pasos.length - 1 ? "Finalizar" : "Siguiente →"}</button>
        </div>
      </div>`;
    document.getElementById("wiz-home").onclick = () => {
      T.py("limpiar_sesion_wizard");
      T.views.renderInicio();
    };
    document.getElementById("wiz-back").onclick = () => {
      T.wizard.collectStep();
      T.state.step--;
      T.renderWizard();
    };
    document.getElementById("wiz-next").onclick = () => T.wizard.next();
  };

  T.renderWizard = () => {
    T.state.vista = "wizard";
    T.updateNav();
    T.renderWizardShell();
    const paso = T.WIZARDS[T.state.wizard].pasos[T.state.step];
    if (T.state.wizard === "analizar") T.wizardAnalizar.renderStep(paso.id);
    if (T.state.wizard === "modelar") T.wizardModelar.renderStep(paso.id);
    if (T.state.wizard === "ver") T.wizardVer.renderStep(paso.id);
  };

  T.startWizard = (id, ctx = null, step = 0) => {
    T.state.wizard = id;
    T.state.step = step;
    T.state.ctx = ctx || (id === "modelar" ? { dominios: [{}] } : {});
    T.state.log = "";
    T.state.tableroGenerado = false;
    T.state.productoGenerado = false;
    T.state.swanCorrido = false;
    T.state.swanOk = false;
    T.applyPrefsToWizard();
    T.renderWizard();
  };

  T.applyPrefsToWizard = () => {
    const p = T.state.prefs;
    if (T.state.wizard === "analizar" && T.state.step === 0) {
      T.state.ctx.era5 = T.state.ctx.era5 || {};
      if (p.era5_lat) T.state.ctx.era5.lat = p.era5_lat;
      if (p.era5_lon) T.state.ctx.era5.lon = p.era5_lon;
      if (p.era5_inicio) T.state.ctx.era5.inicio = p.era5_inicio;
      if (p.era5_fin) T.state.ctx.era5.fin = p.era5_fin;
    }
  };

  T.onResize = () => {
    T.windowEl()?.classList.toggle("narrow", window.innerWidth < 720);
  };
})();
