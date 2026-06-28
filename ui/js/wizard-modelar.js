/* Wizard — Modelar SWAN (malla → nido → batimetría → borde → correr → mapas) */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;
  const ETOPO_KM = 1.85;

  function mallaFields(prefix, vals = {}) {
    const v = (k, d) => T.esc(vals[k] ?? d);
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
    <p class="hint ${vals.resumen ? "ok" : ""}" id="${prefix}-hint">${T.esc(vals.resumen || "")}</p>
    <div id="${prefix}-avisos"></div>
    <div id="${prefix}-preview" class="preview-inline hidden"></div>`;
  }

  function renderMetaBati(meta, domKey) {
    if (!meta) return "";
    const cls = meta.estado || "ok";
    const adv = (meta.advertencias || []).map((a) => `<li>${T.esc(a)}</li>`).join("");
    const nodosChip = meta.n_esperados
      ? `${meta.n_nodos || "?"} / ${meta.n_esperados} nodos`
      : `${meta.n_nodos || "?"} nodos`;
    const nodosCls = meta.estado === "err" && meta.n_esperados ? "err" : "ok";
    const profChip = Number.isFinite(meta.prof_min)
      ? `<span class="chip ok">Prof. ${meta.prof_min.toFixed(1)}–${meta.prof_max.toFixed(1)} m</span>`
      : "";
    const tierraChip = Number.isFinite(meta.pct_tierra)
      ? `<span class="chip ${meta.pct_tierra > 5 ? "warn" : "ok"}">${meta.pct_tierra.toFixed(0)}% tierra</span>`
      : "";
    return `<div class="bati-resumen ${cls}" id="meta-${domKey}">
      <div class="semaforo">
        <span class="chip ${cls}">${T.esc(meta.mensaje || "")}</span>
        <span class="chip ok">Fuente: ${T.esc(meta.fuente || "?")}</span>
        <span class="chip ${nodosCls}">${nodosChip}</span>
        ${profChip}
        ${tierraChip}
      </div>
      ${adv ? `<ul class="hint-list">${adv}</ul>` : ""}
    </div>`;
  }

  function hintNodosEsperados(malla) {
    if (!malla?.mxc) return "Calcula la malla en el paso anterior.";
    const mxc = malla.mxc;
    const myc = malla.myc;
    const n = (mxc + 1) * (myc + 1);
    return `Malla ${mxc}×${myc} celdas → el .bot debe tener ${n} valores (${myc + 1}×${mxc + 1} nodos).`;
  }

  async function aplicarValidacionBot(domIdx, ruta, hintId, previewId, metaKey) {
    const dom = T.state.ctx.dominios[domIdx];
    if (!dom?.malla) { T.notify("Calcula la malla primero."); return false; }
    const val = await T.py("validar_bot_malla", ruta, JSON.stringify(dom.malla));
    dom.bot = ruta;
    dom.bati_meta = val?.meta || null;
    const hint = document.getElementById(hintId);
    if (hint) hint.textContent = ruta;
    const metaBox = document.getElementById(`meta-wrap-${metaKey}`);
    if (metaBox && val?.meta) metaBox.innerHTML = renderMetaBati(val.meta, metaKey);
    const pbox = document.getElementById(previewId);
    if (!val?.ok) {
      if (pbox) { pbox.classList.add("hidden"); pbox.innerHTML = ""; }
      T.notify(val?.error || val?.meta?.mensaje || "La batimetría no encaja con la malla.");
      return false;
    }
    const prev = await T.py("preview_batimetria", ruta, JSON.stringify(dom.malla));
    if (prev?.ok && pbox) {
      pbox.classList.remove("hidden");
      pbox.innerHTML = `<img src="${prev.img}" alt="Batimetría" class="preview-img-sm"/>`;
    } else if (pbox) {
      pbox.classList.add("hidden");
      pbox.innerHTML = "";
    }
    return true;
  }

  async function validarDominioBati(domIdx, etiqueta) {
    const dom = T.state.ctx.dominios[domIdx];
    if (!dom?.bot) {
      T.notify(`Genera o elige la batimetría del dominio ${etiqueta}.`);
      return false;
    }
    if (!dom.malla) {
      T.notify(`Calcula la malla del dominio ${etiqueta}.`);
      return false;
    }
    const val = await T.py("validar_bot_malla", dom.bot, JSON.stringify(dom.malla));
    dom.bati_meta = val?.meta || dom.bati_meta;
    if (!val?.ok || val?.meta?.estado === "err") {
      T.notify(val?.error || val?.meta?.mensaje || `Batimetría del dominio ${etiqueta} no apta.`);
      return false;
    }
    return true;
  }

  function era5RangoBorde() {
    return {
      inicio: T.state.prefs.era5_inicio || "2022-01-01",
      fin: T.state.prefs.era5_fin || "2024-12-31",
    };
  }

  function applyBordeDerivado(res) {
    if (!res?.ok) {
      T.notify(res?.error || "No se pudo derivar el borde.");
      return false;
    }
    const hs = document.getElementById("b-hs");
    const per = document.getElementById("b-per");
    const dir = document.getElementById("b-dir");
    if (hs) hs.value = res.hs ?? "";
    if (per) per.value = res.per ?? "";
    if (dir) dir.value = res.dir ?? "";
    T.state.ctx.dominios[0].serie_borde = res.ruta_serie || "";
    T.state.ctx.borde_derivado_auto = true;
    const st = document.getElementById("borde-era5-status");
    if (st) {
      st.textContent = "Borde derivado — " + (res.descripcion || "ERA5");
      st.classList.add("ok");
    }
    T.showLog();
    T.appendLog("Borde derivado — " + (res.descripcion || "") +
      (res.ruta_serie ? "\nSerie: " + res.ruta_serie : ""));
    return true;
  }

  async function derivarBordeEra5({ auto = false, descargar = false } = {}) {
    const ui = T.state.ctx.dominios?.[0]?.malla_ui;
    if (!ui?.lat || !ui?.lon) {
      if (!auto) T.notify("Calcula la malla del dominio grande primero.");
      return;
    }
    const { inicio, fin } = era5RangoBorde();
    let cond;
    if (auto) {
      cond = {
        modo: T.state.prefs.borde_modo || "reinante",
        tr: T.state.prefs.borde_tr || 100,
      };
    } else {
      cond = await T.askBordeCondicion();
      if (!cond) return;
      T.state.prefs.borde_modo = cond.modo;
      T.state.prefs.borde_tr = cond.tr;
      T.guardarPrefs();
    }

    const cache = await T.py("estado_cache_era5_borde", ui.lat, ui.lon, inicio, fin);
    if (auto && !cache?.en_cache) {
      const st = document.getElementById("borde-era5-status");
      if (st) {
        st.textContent = "Sin ERA5 en caché. Pulsa «Derivar de ERA5» (descarga si hace falta).";
        st.classList.remove("ok");
      }
      return;
    }

    const needDownload = descargar || (!cache?.en_cache && !auto);
    if (needDownload && !cache?.en_cache) {
      T.showLog();
      T.setStatus("Descargando ERA5 para el borde…", "proc");
      const start = await T.py("derivar_borde_era5", ui.lat, ui.lon, inicio, fin,
        cond.modo, cond.tr, true);
      if (!start?.ok) {
        T.setStatus(start?.error || "Error.", "err");
        T.notify(start?.error);
        return;
      }
      const done = await T.waitTask("borde_era5");
      T.setStatus(done.ok ? "Listo." : "Error.", done.ok ? "" : "err");
      if (done.ok) applyBordeDerivado(done.result);
      else T.notify(done.error);
      return;
    }

    const res = await T.py("derivar_borde_era5", ui.lat, ui.lon, inicio, fin,
      cond.modo, cond.tr, false);
    applyBordeDerivado(res);
  }

  function bordeEra5Hint() {
    const ui = T.state.ctx.dominios?.[0]?.malla_ui;
    if (!ui?.lat) return "Calcula la malla en el paso anterior para derivar el borde desde ERA5.";
    const { inicio, fin } = era5RangoBorde();
    return `Punto ERA5: (${ui.lat}, ${ui.lon}) · ${inicio} → ${fin}`;
  }

  function bordeDiagram() {
    return `<div class="borde-diagram" aria-hidden="true">
      <div class="borde-grid">
        <div class="borde-side borde-n">N — borde norte</div>
        <div class="borde-side borde-w">W</div>
        <div class="borde-domain">Dominio<br/><small>Dir náutica: de dónde viene el oleaje (° desde N)</small></div>
        <div class="borde-side borde-e">E</div>
        <div class="borde-side borde-s">S — borde sur</div>
      </div>
    </div>`;
  }

  function checklistHtml(items) {
    return `<ul class="checklist">${items.map((it) =>
      `<li class="${it.ok ? "ok" : "pending"}"><span class="check-icon">${it.ok ? "✓" : "○"}</span>
        <strong>${T.esc(it.label)}</strong> <span class="hint">${T.esc(it.detalle || "")}</span></li>`
    ).join("")}</ul>`;
  }

  async function refreshChecklist() {
    const box = document.getElementById("swan-checklist");
    if (!box) return;
    const res = await T.py("checklist_correr_swan", JSON.stringify(T.state.ctx));
    if (res?.items) box.innerHTML = checklistHtml(res.items);
  }

  async function calcMalla(prefix, domIdx) {
    const lat = document.getElementById(`${prefix}-lat`).value;
    const lon = document.getElementById(`${prefix}-lon`).value;
    const ancho = document.getElementById(`${prefix}-ancho`).value;
    const alto = document.getElementById(`${prefix}-alto`).value;
    const celda = document.getElementById(`${prefix}-celda`).value;
    const res = await T.py("calcular_malla", lat, lon, ancho, alto, celda);
    if (!res?.ok) { T.notify(res?.error || "Error al calcular malla."); return false; }
    if (!T.state.ctx.dominios[domIdx]) T.state.ctx.dominios[domIdx] = {};
    T.state.ctx.dominios[domIdx].malla = res.malla;
    T.state.ctx.dominios[domIdx].zona_utm = res.malla.zona_utm;
    T.state.ctx.dominios[domIdx].malla_ui = { lat, lon, ancho, alto, celda, resumen: res.resumen };
    delete T.state.ctx.dominios[domIdx].bot;
    delete T.state.ctx.dominios[domIdx].bati_meta;
    document.getElementById(`${prefix}-hint`).textContent = res.resumen;
    document.getElementById(`${prefix}-hint`).classList.add("ok");
    const avBox = document.getElementById(`${prefix}-avisos`);
    if (avBox && res.avisos_resolucion?.length) {
      avBox.innerHTML = res.avisos_resolucion.map((a) => `<p class="hint warn">${T.esc(a)}</p>`).join("");
    } else if (avBox) avBox.innerHTML = "";
    const prev = await T.py("preview_malla", JSON.stringify(res.malla), lat, lon);
    if (prev?.ok && prev.img) {
      const box = document.getElementById(`${prefix}-preview`);
      if (box) {
        box.classList.remove("hidden");
        box.innerHTML = `<img src="${prev.img}" alt="Vista malla" class="preview-img-sm"/>`;
      }
    }
    if (domIdx === 1 && T.state.ctx.dominios[0]?.malla) await previewNidoAnidado();
    return true;
  }

  async function previewNidoAnidado() {
    const g = T.state.ctx.dominios[0]?.malla;
    const n = T.state.ctx.dominios[1]?.malla;
    const box = document.getElementById("nido-overlay-preview");
    if (!box || !g || !n) return;
    const prev = await T.py("preview_malla_anidada", JSON.stringify(g), JSON.stringify(n));
    if (prev?.ok && prev.img) {
      box.classList.remove("hidden");
      box.innerHTML = `<img src="${prev.img}" alt="Anidamiento" class="preview-img-sm"/>`;
    }
    const val = await T.py("validar_nido", JSON.stringify(g), JSON.stringify(n));
    const msg = document.getElementById("nido-val-msg");
    if (msg && val) {
      const parts = [...(val.errores || []), ...(val.avisos || [])];
      msg.innerHTML = parts.length
        ? parts.map((p) => `<p class="hint ${val.errores?.length ? "err" : "warn"}">${T.esc(p)}</p>`).join("")
        : `<p class="hint ok">Nido contenido en el dominio grande.</p>`;
    }
  }

  async function generarBot(domIdx, nombre, hintId, previewId, metaKey, rasterRuta = null) {
    if (!T.state.ctx.carpeta_caso) { T.notify("Define la carpeta del caso en el paso Malla."); return; }
    const dom = T.state.ctx.dominios[domIdx];
    if (!dom?.malla) { T.notify("Calcula la malla primero."); return; }
    T.showLog();
    T.setStatus("Generando .bot…", "proc");
    const start = await T.py("generar_batimetria", JSON.stringify(dom.malla), dom.zona_utm,
      T.state.ctx.carpeta_caso, nombre, rasterRuta);
    if (!start?.ok) { T.notify(start?.error || "No se pudo iniciar."); return; }
    const done = await T.waitTask("batimetria");
    if (done.ok) {
      dom.bot = done.result.ruta;
      dom.bati_meta = done.result.meta;
      T.appendLog(done.result.log);
      const hint = document.getElementById(hintId);
      if (hint) hint.textContent = done.result.ruta;
      const metaBox = document.getElementById(`meta-wrap-${metaKey}`);
      if (metaBox) metaBox.innerHTML = renderMetaBati(done.result.meta, metaKey);
      T.setStatus("Listo.");
      const prev = await T.py("preview_batimetria", dom.bot, JSON.stringify(dom.malla));
      const pbox = document.getElementById(previewId);
      if (prev?.ok && pbox) {
        pbox.classList.remove("hidden");
        pbox.innerHTML = `<img src="${prev.img}" alt="Batimetría" class="preview-img-sm"/>`;
      }
    } else {
      T.appendLog(done.error);
      T.setStatus("Error.", "err");
    }
  }

  T.wizardModelar = {
    renderStep(id) {
      document.getElementById("step-body").innerHTML = this.stepHtml(id);
      this.bind(id);
    },

    stepHtml(id) {
      const dom = T.state.ctx.dominios?.[0] || {};
      const ctx = T.state.ctx;
      if (id === "malla") return `<div class="form-card">
        <p class="explain">El <strong>dominio grande</strong> es tu ventana de modelación en UTM (derivada del centro lat/lon).</p>
        <label class="field">Plantilla rápida
          <select id="plantilla-malla"><option value="">— Elegir —</option></select>
        </label>
        ${mallaFields("malla", dom.malla_ui || {})}
        <hr class="soft-divider"/>
        <label class="field">Carpeta del caso SWAN
          <div class="field-row">
            <input type="text" id="carpeta-caso" readonly placeholder="Elige dónde guardar .bot, .swn y salidas"
              value="${T.esc(ctx.carpeta_caso || "")}" style="flex:1"/>
            <button type="button" class="btn secondary" id="pick-carpeta">Carpeta…</button>
          </div>
        </label>
        <p class="hint">Aquí se guardan batimetría, archivos SWAN y resultados de la corrida.</p>
      </div>`;

      if (id === "nido") return `<div class="form-card">
        <p class="explain">Opcional: un <strong>nido</strong> es un dominio más fino dentro del grande (misma zona UTM).</p>
        <label class="radio"><input type="checkbox" id="nido-on" ${ctx.nido_activo ? "checked" : ""}/> Usar dominio anidado</label>
        <div id="nido-box" class="${ctx.nido_activo ? "" : "hidden"}">
          ${mallaFields("nido", ctx.dominios?.[1]?.malla_ui || { lat:"-36.97", lon:"-73.15", ancho:"9", alto:"10", celda:"200" })}
          <div id="nido-val-msg"></div>
          <div id="nido-overlay-preview" class="preview-inline hidden"></div>
        </div>
      </div>`;

      if (id === "bati") {
        const metaG = renderMetaBati(dom.bati_meta, "grande");
        const metaN = renderMetaBati(ctx.dominios?.[1]?.bati_meta, "nido");
        const hintG = hintNodosEsperados(dom.malla);
        const hintN = ctx.nido_activo ? hintNodosEsperados(ctx.dominios?.[1]?.malla) : "";
        return `<div class="form-card">
          <p class="explain">SWAN no lee un «mapa»: necesita <code>.bot</code> = profundidad en cada nodo de la malla.
            <strong>Generar desde ETOPO</strong> usa un mapa global (~${ETOPO_KM} km); sirve para dominios gruesos.
            Para bahías finas usa <strong>raster .nc</strong> (SHOA/GEBCO) o un <strong>.bot</strong> ya hecho.</p>
          <div class="tab-bar">
            <button type="button" class="tab-btn active" data-tab="bati-grande">Dominio grande</button>
            <button type="button" class="tab-btn ${ctx.nido_activo ? "" : "disabled"}" data-tab="bati-nido" ${ctx.nido_activo ? "" : "disabled"}>Nido</button>
          </div>
          <div id="bati-grande" class="tab-panel">
            <p class="hint ok" id="bati-esperado">${T.esc(hintG)}</p>
            <button type="button" class="btn primary" id="bati-etopo">Generar .bot desde ETOPO (~2 km)</button>
            <button type="button" class="btn secondary" id="bati-raster">Desde raster .nc local…</button>
            <button type="button" class="btn secondary" id="bati-pick">Usar .bot propio…</button>
            <p class="hint" id="bati-hint">${T.esc(dom.bot || "")}</p>
            <div id="meta-wrap-grande">${metaG}</div>
            <div id="bati-preview" class="preview-inline hidden"></div>
          </div>
          <div id="bati-nido" class="tab-panel hidden">
            ${ctx.nido_activo ? "" : "<p class=\"hint warn\">Activa el nido en el paso anterior.</p>"}
            ${hintN ? `<p class="hint ok" id="nido-esperado">${T.esc(hintN)}</p>` : ""}
            <button type="button" class="btn primary" id="nido-etopo" ${ctx.nido_activo ? "" : "disabled"}>Generar .bot nido (ETOPO)</button>
            <button type="button" class="btn secondary" id="nido-raster" ${ctx.nido_activo ? "" : "disabled"}>Raster .nc…</button>
            <button type="button" class="btn secondary" id="nido-pick" ${ctx.nido_activo ? "" : "disabled"}>.bot propio…</button>
            <p class="hint" id="nido-bot-hint">${T.esc(ctx.dominios?.[1]?.bot || "")}</p>
            <div id="meta-wrap-nido">${metaN}</div>
            <div id="nido-bati-preview" class="preview-inline hidden"></div>
          </div>
        </div>`;
      }

      if (id === "borde") return `<div class="form-card">
        ${bordeDiagram()}
        <p class="hint" id="borde-era5-hint">${T.esc(bordeEra5Hint())}</p>
        <p class="hint" id="borde-era5-status">${dom.borde_derivado_auto ? "Borde ya derivado de ERA5/serie." : "Al entrar se rellena solo si hay ERA5 en caché (oleaje reinante)."}</p>
        <div class="field-row">
          <label class="field">Hs [m]<input id="b-hs" value="${dom.borde_ui?.hs ?? "3.0"}"/></label>
          <label class="field">Tp [s]<input id="b-per" value="${dom.borde_ui?.per ?? "12.0"}"/></label>
          <label class="field">Dir [°] náutica<input id="b-dir" value="${dom.borde_ui?.dir ?? "290"}"/></label>
          <label class="field">Disp [°]<input id="b-dd" value="${dom.borde_ui?.dd ?? "20"}"/></label>
        </div>
        <div class="check-row">Marca los lados donde aplicas la condición:
          ${["N","S","E","W"].map(s => `<label><input type="checkbox" class="b-lado" value="${s}" ${(dom.borde_ui?.lados || ["N","W"]).includes(s) ? "checked" : ""}/> ${s}</label>`).join("")}
        </div>
        <div class="field-row" style="margin-top:12px">
          <button type="button" class="btn primary" id="b-derivar-era5">Derivar de ERA5 (centro malla)</button>
          <button type="button" class="btn secondary" id="b-derivar-arch">Desde archivo…</button>
        </div>
      </div>`;

      if (id === "correr") return `<div class="form-card">
        <div id="swan-checklist"><p class="hint">Comprobando requisitos…</p></div>
        <label class="field">Nombre del caso<input id="caso-nom" value="${T.esc(ctx.nombre_caso || "MiCaso")}"/></label>
        <div class="field-row">
          <button type="button" class="btn primary" id="swan-run">Generar .swn y correr</button>
          <button type="button" class="btn secondary hidden" id="swan-cancel">Cancelar corrida</button>
          <button type="button" class="btn secondary" id="swan-logs">Abrir carpeta / logs</button>
        </div>
        <p class="hint ${ctx.swanCorrido ? (ctx.swanOk ? "ok" : "err") : ""}" id="swan-hint">${ctx.swanCorrido ? (ctx.swanOk ? "SWAN terminó bien." : "SWAN terminó con errores — revisa .prt/.erf en la carpeta.") : ""}</p>
      </div>`;

      if (id === "mapas") return `<div class="form-card">
        <p>Genera el tablero de mapas de la corrida.</p>
        <button type="button" class="btn primary" id="gen-mapas">Generar mapas</button>
      </div>`;
      return "";
    },

    bind(id) {
      if (id === "malla") {
        T.py("listar_plantillas_malla").then((res) => {
          const sel = document.getElementById("plantilla-malla");
          if (!sel || !res?.plantillas) return;
          res.plantillas.forEach((p) => {
            const o = document.createElement("option");
            o.value = p.id;
            o.textContent = p.nombre;
            sel.appendChild(o);
          });
        });
        document.getElementById("plantilla-malla")?.addEventListener("change", async (e) => {
          const id = e.target.value;
          if (!id) return;
          const res = await T.py("listar_plantillas_malla");
          const p = res?.plantillas?.find((x) => x.id === id);
          if (!p) return;
          ["lat", "lon", "ancho", "alto", "celda"].forEach((k) => {
            const el = document.getElementById(`malla-${k}`);
            if (el) el.value = p[k];
          });
          if (p.nido) T.state.ctx._plantilla_nido = p.nido;
        });
        document.getElementById("malla-calc").onclick = () => calcMalla("malla", 0);
        document.getElementById("pick-carpeta").onclick = async () => {
          const d = await T.py("elegir_carpeta", "swan");
          if (d) {
            document.getElementById("carpeta-caso").value = d;
            T.state.ctx.carpeta_caso = d;
          }
        };
      }

      if (id === "nido") {
        document.getElementById("nido-on").onchange = (e) => {
          T.state.ctx.nido_activo = e.target.checked;
          document.getElementById("nido-box").classList.toggle("hidden", !e.target.checked);
          if (e.target.checked && T.state.ctx._plantilla_nido) {
            const p = T.state.ctx._plantilla_nido;
            ["lat", "lon", "ancho", "alto", "celda"].forEach((k) => {
              const el = document.getElementById(`nido-${k}`);
              if (el) el.value = p[k];
            });
          }
        };
        document.getElementById("nido-calc")?.addEventListener("click", () => calcMalla("nido", 1));
        if (T.state.ctx.dominios?.[1]?.malla) previewNidoAnidado();
      }

      if (id === "bati") {
        document.querySelectorAll(".tab-btn").forEach((btn) => {
          btn.onclick = () => {
            if (btn.disabled) return;
            document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById("bati-grande").classList.toggle("hidden", btn.dataset.tab !== "bati-grande");
            document.getElementById("bati-nido").classList.toggle("hidden", btn.dataset.tab !== "bati-nido");
          };
        });
        document.getElementById("bati-etopo").onclick = () =>
          generarBot(0, "bati.bot", "bati-hint", "bati-preview", "grande");
        document.getElementById("bati-raster").onclick = async () => {
          const r = await T.py("elegir_archivo", "raster");
          if (r) generarBot(0, "bati.bot", "bati-hint", "bati-preview", "grande", r);
        };
        document.getElementById("bati-pick").onclick = async () => {
          const r = await T.py("elegir_archivo", "bot");
          if (r) await aplicarValidacionBot(0, r, "bati-hint", "bati-preview", "grande");
        };
        document.getElementById("nido-etopo")?.addEventListener("click", () =>
          generarBot(1, "bati_nido.bot", "nido-bot-hint", "nido-bati-preview", "nido"));
        document.getElementById("nido-raster")?.addEventListener("click", async () => {
          const r = await T.py("elegir_archivo", "raster");
          if (r) generarBot(1, "bati_nido.bot", "nido-bot-hint", "nido-bati-preview", "nido", r);
        });
        document.getElementById("nido-pick")?.addEventListener("click", async () => {
          const r = await T.py("elegir_archivo", "bot");
          if (r) {
            if (!T.state.ctx.dominios[1]) T.state.ctx.dominios[1] = {};
            await aplicarValidacionBot(1, r, "nido-bot-hint", "nido-bati-preview", "nido");
          }
        });
      }

      if (id === "borde") {
        if (!T.state.ctx.borde_derivado_auto) {
          derivarBordeEra5({ auto: true });
        }
        document.getElementById("b-derivar-era5").onclick = () =>
          derivarBordeEra5({ auto: false, descargar: true });
        document.getElementById("b-derivar-arch").onclick = async () => {
          const r = await T.py("elegir_archivo", "serie");
          if (!r) return;
          const cond = await T.askBordeCondicion();
          if (!cond) return;
          const res = await T.py("derivar_borde", r, cond.modo, cond.tr);
          applyBordeDerivado(res);
        };
      }

      if (id === "correr") {
        refreshChecklist();
        document.getElementById("swan-run").onclick = () => this.runSwan();
        document.getElementById("swan-cancel")?.addEventListener("click", async () => {
          await T.py("cancelar_swan");
          T.appendLog("Cancelando corrida SWAN…");
        });
        document.getElementById("swan-logs").onclick = () => {
          if (T.state.ctx.carpeta_caso) T.py("abrir_logs_swan", T.state.ctx.carpeta_caso);
        };
      }

      if (id === "mapas") {
        document.getElementById("gen-mapas").onclick = async () => {
          T.showLog();
          T.setStatus("Generando mapas…", "proc");
          const start = await T.py("generar_mapas_swan", T.state.ctx.carpeta_resultado || T.state.ctx.carpeta_caso);
          if (!start?.ok) return;
          const done = await T.waitTask("mapas_swan");
          if (done.ok) {
            T.state.productoGenerado = true;
            T.appendLog("Resultado: " + done.result.ruta);
            T.setStatus("Listo.");
            T.showPreview("preview-box", done.result.preview, done.result.ruta);
            T.py("abrir_archivo", done.result.ruta);
          } else { T.appendLog(done.error); T.setStatus("Error.", "err"); }
        };
      }
    },

    collectStep() {
      const id = T.WIZARDS.modelar.pasos[T.state.step].id;
      const dom = T.state.ctx.dominios[0];
      if (id === "malla") {
        T.state.ctx.carpeta_caso = document.getElementById("carpeta-caso")?.value || T.state.ctx.carpeta_caso;
      }
      if (id === "nido") {
        T.state.ctx.nido_activo = document.getElementById("nido-on")?.checked;
        if (!T.state.ctx.nido_activo && T.state.ctx.dominios.length > 1) {
          T.state.ctx.dominios = [T.state.ctx.dominios[0]];
        }
      }
      if (id === "borde") {
        const lados = [...document.querySelectorAll(".b-lado:checked")].map((c) => c.value);
        const hs = parseFloat(document.getElementById("b-hs").value);
        const per = parseFloat(document.getElementById("b-per").value);
        const dir = parseFloat(document.getElementById("b-dir").value);
        const dd = parseFloat(document.getElementById("b-dd").value);
        dom.bordes = lados.map((s) => ({ lado: s, hs, per, dir, dd }));
        dom.borde_ui = { hs, per, dir, dd, lados };
      }
      if (id === "correr") {
        T.state.ctx.nombre_caso = document.getElementById("caso-nom")?.value || "MiCaso";
        T.state.ctx.carpeta_resultado = T.state.ctx.carpeta_caso;
      }
    },

    async validate() {
      T.clearFieldErrors();
      const id = T.WIZARDS.modelar.pasos[T.state.step].id;
      if (id === "malla") {
        if (!T.state.ctx.dominios[0]?.malla) { T.notify("Calcula la malla del dominio grande."); return false; }
        const carp = document.getElementById("carpeta-caso")?.value || T.state.ctx.carpeta_caso;
        if (!carp) { T.notify("Elige la carpeta del caso SWAN."); return false; }
        T.state.ctx.carpeta_caso = carp;
        return true;
      }
      if (id === "nido") {
        this.collectStep();
        if (T.state.ctx.nido_activo) {
          const n = T.state.ctx.dominios[1];
          if (!n?.malla) { T.notify("Calcula la malla del nido o desactívalo."); return false; }
          const val = await T.py("validar_nido", JSON.stringify(T.state.ctx.dominios[0].malla), JSON.stringify(n.malla));
          if (val?.errores?.length) { T.notify(val.errores.join("\n")); return false; }
        }
        return true;
      }
      if (id === "bati") {
        if (!(await validarDominioBati(0, "grande"))) return false;
        if (T.state.ctx.nido_activo && !(await validarDominioBati(1, "nido"))) return false;
        return true;
      }
      if (id === "borde") {
        this.collectStep();
        if (!T.state.ctx.dominios[0].bordes?.length) { T.notify("Elige al menos un lado de borde."); return false; }
        const u = T.state.ctx.dominios[0].borde_ui || {};
        if (!Number.isFinite(u.hs) || u.hs <= 0) { T.notify("Hs del borde debe ser > 0."); return false; }
        if (!Number.isFinite(u.per) || u.per <= 0) { T.notify("Periodo del borde debe ser > 0."); return false; }
        if (!Number.isFinite(u.dir)) { T.notify("Dirección del borde inválida."); return false; }
        return true;
      }
      if (id === "correr") {
        if (!T.state.swanCorrido) { T.notify("Corre SWAN primero."); return false; }
        if (!T.state.swanOk) { T.notify("SWAN falló; revisa el log y los archivos .prt/.erf."); return false; }
        return true;
      }
      if (id === "mapas") {
        if (!T.state.productoGenerado) { T.notify("Genera los mapas."); return false; }
        return true;
      }
      return true;
    },

    async runSwan() {
      this.collectStep();
      const val = await T.py("validar_correr_swan", JSON.stringify(T.state.ctx));
      if (val?.errores?.length) { T.notify(val.errores.join("\n\n")); return; }
      if (val?.avisos?.length) {
        const ok = await T.askConfirm(val.avisos.join("\n\n") + "\n\n¿Continuar?");
        if (!ok) return;
      }
      T.showLog();
      T.setStatus("Corriendo SWAN…", "proc");
      document.getElementById("swan-cancel")?.classList.remove("hidden");
      const nom = document.getElementById("caso-nom")?.value || "MiCaso";
      const start = await T.py("escribir_y_correr_swan", JSON.stringify(T.state.ctx), nom);
      if (!start?.ok) {
        document.getElementById("swan-cancel")?.classList.add("hidden");
        T.notify(start?.error);
        return;
      }
      const done = await T.waitTask("swan");
      document.getElementById("swan-cancel")?.classList.add("hidden");
      T.state.swanCorrido = true;
      if (done.ok) {
        T.state.swanOk = done.result.ok;
        T.appendLog(done.result.log);
        const hint = done.result.cancelado
          ? "Corrida cancelada."
          : (T.state.swanOk ? "SWAN terminó bien." : "SWAN terminó con errores — revisa .prt/.erf.");
        document.getElementById("swan-hint").textContent = hint;
        T.setStatus(done.result.cancelado ? "Cancelado." : (T.state.swanOk ? "Listo." : "Error."),
          done.result.cancelado ? "err" : (T.state.swanOk ? "listo" : "err"));
        if (!T.state.swanOk && T.state.ctx.carpeta_caso) {
          T.notify("Revisa .prt/.erf en la carpeta del caso.", "warn");
        }
      } else {
        T.state.swanOk = false;
        T.appendLog(done.error);
        T.setStatus("Error.", "err");
      }
      refreshChecklist();
    },

    onNext() {},
  };
})();
