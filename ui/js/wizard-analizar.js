/* Wizard — Analizar oleaje */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;

  function statusErrorEra5(mensaje) {
    if (/credencial|cdsapirc|CDS/i.test(mensaje || "")) {
      return "Error: Faltan credenciales ERA5";
    }
    const txt = (mensaje || "Error al descargar").trim();
    return txt.startsWith("Error:") ? txt : `Error: ${txt}`;
  }

  function collectEra5Fields() {
    T.state.ctx.modo = document.querySelector('input[name="modo"]:checked')?.value || "archivo";
    T.state.ctx.era5 = {
      lat: document.getElementById("era5-lat")?.value,
      lon: document.getElementById("era5-lon")?.value,
      inicio: document.getElementById("era5-ini")?.value,
      fin: document.getElementById("era5-fin")?.value,
      viento: document.getElementById("era5-viento")?.checked,
      espectro: document.getElementById("era5-espectro")?.checked,
    };
    T.state.prefs.era5_lat = T.state.ctx.era5.lat;
    T.state.prefs.era5_lon = T.state.ctx.era5.lon;
    T.state.prefs.era5_inicio = T.state.ctx.era5.inicio;
    T.state.prefs.era5_fin = T.state.ctx.era5.fin;
    T.guardarPrefs();
  }

  function renderSemafaro(res) {
    if (!res?.validacion) return "";
    const vars = (res.variables || []).join(", ") || "—";
    const prodOk = (res.productos || []).filter((p) => p.disponible).length;
    const prodNo = (res.productos || []).filter((p) => !p.disponible).length;
    const valWarn = (res.validacion || []).filter((v) => v.estado === "warn").length;
    let html = `<div class="semaforo">
      <span class="chip ok">Variables: ${T.esc(vars)}</span>
      <span class="chip ok">${res.n_pasos || 0} pasos</span>
      <span class="chip ${prodOk ? "ok" : "err"}">${prodOk} productos OK</span>`;
    if (prodNo) html += `<span class="chip warn">${prodNo} omitidos</span>`;
    if (valWarn) html += `<span class="chip warn">${valWarn} avisos validación</span>`;
    html += "</div>";
    html += '<ul class="semaforo-list">';
    for (const v of res.validacion || []) {
      html += `<li class="sem-${v.estado}"><strong>${T.esc(v.nombre)}</strong> — ${T.esc(v.detalle || (v.estado === "ok" ? "OK" : ""))}</li>`;
    }
    for (const p of res.productos || []) {
      const cls = p.disponible ? "ok" : "na";
      html += `<li class="sem-${cls}"><strong>${T.esc(p.nombre)}</strong> — ${p.disponible ? "disponible" : T.esc(p.motivo)}</li>`;
    }
    html += "</ul>";
    if (res.comparacion && !res.comparacion.error) {
      const c = res.comparacion;
      html += `<div class="comparacion-box"><strong>Comparación vs referencia</strong> (${c.n} pasos comunes):
        bias ${c.bias?.toFixed(3)} m · RMSE ${c.rmse?.toFixed(3)} m · r=${c.corr?.toFixed(3) ?? "—"}</div>`;
    } else if (res.comparacion?.error) {
      html += `<p class="hint err">${T.esc(res.comparacion.error)}</p>`;
    }
    html += `<details class="reporte-detalle"><summary>Reporte completo</summary><pre class="log-pre">${T.esc(res.reporte || "")}</pre></details>`;
    return html;
  }

  async function runRevision() {
    const ref = T.state.ctx.ruta_referencia || "";
    const res = ref
      ? await T.py("revision_con_referencia", T.state.ctx.ruta_datos, ref)
      : await T.py("revision_datos", T.state.ctx.ruta_datos);
    T.state.ctx.revision = res;
    T.state.ctx.reporte = res?.reporte || "";
    T.state.ctx.revision_ok = res?.ok;
    T.state.ctx.revision_motivo = res?.motivo || "";
  }

  T.wizardAnalizar = {
    renderStep(id) {
      const body = document.getElementById("step-body");
      if (!body) return;
      if (id === "origen") body.innerHTML = this.stepOrigen();
      if (id === "revision") body.innerHTML = this.stepRevision();
      if (id === "tablero") body.innerHTML = this.stepTablero();
      this.bind(id);
    },

    stepOrigen() {
      const c = T.state.ctx;
      const e = c.era5 || {};
      return `<div class="form-card">
        <label class="radio"><input type="radio" name="modo" value="archivo" ${c.modo !== "era5" ? "checked" : ""}/> Tengo un archivo (.mat / .csv / .nc)</label>
        <div class="field-row" style="margin-left:20px;margin-bottom:12px">
          <input type="text" id="ruta-arch" readonly placeholder="Ningún archivo" value="${T.esc(c.ruta_datos || "")}" style="flex:1"/>
          <button type="button" class="btn secondary" id="pick-arch">Archivo…</button>
        </div>
        <label class="radio"><input type="radio" name="modo" value="era5" ${c.modo === "era5" ? "checked" : ""}/> Descargar de ERA5</label>
        <div id="era5-fields" class="${c.modo === "era5" ? "" : "hidden"}" style="margin-left:20px">
          <div class="field-row">
            <label class="field">Latitud<input id="era5-lat" value="${T.esc(e.lat ?? T.state.prefs.era5_lat ?? "-37.0")}"/></label>
            <label class="field">Longitud<input id="era5-lon" value="${T.esc(e.lon ?? T.state.prefs.era5_lon ?? "-73.5")}"/></label>
          </div>
          <div class="field-row">
            <label class="field">Inicio<input id="era5-ini" value="${T.esc(e.inicio ?? T.state.prefs.era5_inicio ?? "2024-07-28")}"/></label>
            <label class="field">Fin<input id="era5-fin" value="${T.esc(e.fin ?? T.state.prefs.era5_fin ?? "2024-07-29")}"/></label>
          </div>
          <label class="radio"><input type="checkbox" id="era5-viento" ${e.viento !== false ? "checked" : ""}/> Incluir viento (sea/swell)</label>
          <label class="radio"><input type="checkbox" id="era5-espectro" ${e.espectro ? "checked" : ""}/> Incluir espectro 2D (partición espectral)</label>
          <button type="button" class="btn primary" id="era5-dl" style="margin-top:10px">Descargar ERA5</button>
          <p class="hint ${c.era5_descargado ? "ok" : ""}" id="era5-hint">${c.era5_descargado ? "Serie descargada." : ""}</p>
        </div>
        <hr class="soft-divider"/>
        <label class="field">Serie de referencia (opcional, p. ej. boya observada)
          <div class="field-row">
            <input type="text" id="ruta-ref" readonly placeholder="Ninguna" value="${T.esc(c.ruta_referencia || "")}" style="flex:1"/>
            <button type="button" class="btn secondary" id="pick-ref">Archivo…</button>
          </div>
        </label>
      </div>`;
    },

    stepRevision() {
      const r = T.state.ctx.revision;
      return `<div class="form-card">${r ? renderSemafaro(r) : "<p>Cargando…</p>"}</div>`;
    },

    stepTablero() {
      return `<div class="form-card">
        <p>Genera el tablero de curvas. La vista previa aparece abajo; también puedes abrir el PNG.</p>
        <button type="button" class="btn primary" id="gen-tablero">Generar tablero</button>
      </div>`;
    },

    bind(id) {
      if (id === "origen") {
        document.querySelectorAll('input[name="modo"]').forEach((r) =>
          r.onchange = () => {
            document.getElementById("era5-fields").classList.toggle("hidden", r.value !== "era5" || !r.checked);
            if (r.checked) T.state.ctx.modo = r.value;
          });
        document.getElementById("pick-arch").onclick = async () => {
          const r = await T.py("elegir_archivo", "oleaje");
          if (r) { document.getElementById("ruta-arch").value = r; T.state.ctx.ruta_datos = r; }
        };
        document.getElementById("pick-ref").onclick = async () => {
          const r = await T.py("elegir_archivo", "serie");
          if (r) { document.getElementById("ruta-ref").value = r; T.state.ctx.ruta_referencia = r; }
        };
        for (const fid of ["era5-lat", "era5-lon", "era5-ini", "era5-fin"]) {
          document.getElementById(fid)?.addEventListener("input", () => {
            T.state.ctx.era5_descargado = false;
            T.state.tableroGenerado = false;
          });
        }
        document.getElementById("era5-dl").onclick = async () => {
          collectEra5Fields();
          const e = T.state.ctx.era5;
          T.showLog();
          T.setStatus("Descargando ERA5…", "proc");
          T.state.ctx.era5_descargado = false;
          const start = await T.py("descargar_era5", e.lat, e.lon, e.inicio, e.fin, e.viento, e.espectro);
          if (!start?.ok) { T.setStatus(statusErrorEra5(start?.error), "err"); return; }
          const dias = T.diasEntre(e.inicio, e.fin);
          const idleMs = Math.min(3600000, Math.max(1800000, dias * 90000));
          const done = await T.waitTask("era5", idleMs, {
            renewOnActivity: true,
            timeoutMessage: "Tiempo de espera agotado en la interfaz. Si el log sigue avanzando, la descarga continúa; pulsa Descargar otra vez para reanudar.",
          });
          if (done.ok) {
            T.state.ctx.ruta_datos = done.result.ruta;
            T.state.ctx.era5_descargado = true;
            T.state.ctx.era5_clave = `${e.lat}|${e.lon}|${e.inicio}|${e.fin}|${e.espectro}`;
            T.appendLog(done.result.log || "");
            document.getElementById("era5-hint").textContent = "Descarga lista: " + done.result.ruta;
            document.getElementById("era5-hint").classList.add("ok");
            T.setStatus("Listo.");
          } else {
            T.appendLog(done.error);
            T.setStatus(statusErrorEra5(done.error), "err");
          }
        };
      }
      if (id === "tablero") {
        document.getElementById("gen-tablero").onclick = async () => {
          T.showLog();
          T.setStatus("Generando tablero…", "proc");
          const start = await T.py("generar_tablero_oleaje", T.state.ctx.ruta_datos);
          if (!start?.ok) { T.notify(start?.error || "No se pudo iniciar."); return; }
          const done = await T.waitTask("tablero_oleaje");
          if (done.ok) {
            T.state.tableroGenerado = true;
            T.appendLog("Resultado: " + done.result.ruta);
            T.setStatus("Listo.");
            T.showPreview("preview-box", done.result.preview, done.result.ruta);
            T.py("abrir_archivo", done.result.ruta);
          } else {
            T.appendLog(done.error);
            T.setStatus("Error.", "err");
          }
        };
      }
    },

    collectStep() {
      if (T.state.step === 0) {
        if (T.state.ctx.modo === "era5") collectEra5Fields();
        T.state.ctx.ruta_referencia = document.getElementById("ruta-ref")?.value || T.state.ctx.ruta_referencia;
      }
    },

    async validate() {
      T.clearFieldErrors();
      if (T.state.step === 0) {
        const modo = document.querySelector('input[name="modo"]:checked')?.value || T.state.ctx.modo || "archivo";
        T.state.ctx.modo = modo;
        if (modo === "archivo") {
          const r = document.getElementById("ruta-arch")?.value || T.state.ctx.ruta_datos;
          if (!r) { T.notify("Selecciona un archivo."); return false; }
          if (!(await T.py("ruta_existe", r))) { T.notify("El archivo no existe en disco."); return false; }
          T.state.ctx.ruta_datos = r;
        } else {
          if (!T.state.ctx.era5_descargado) { T.notify("Descarga la serie ERA5 primero."); return false; }
          collectEra5Fields();
          const e = T.state.ctx.era5 || {};
          const clave = `${e.lat}|${e.lon}|${e.inicio}|${e.fin}|${e.espectro}`;
          if (T.state.ctx.era5_clave && T.state.ctx.era5_clave !== clave) {
            T.notify("Cambiaste coordenadas, fechas u opciones; vuelve a descargar ERA5.");
            return false;
          }
        }
        T.state.ctx.ruta_referencia = document.getElementById("ruta-ref")?.value || "";
        return true;
      }
      if (T.state.step === 1) {
        if (!T.state.ctx.revision_ok) { T.notify(T.state.ctx.revision_motivo || "Revisión no superada."); return false; }
        return true;
      }
      if (T.state.step === 2) {
        if (!T.state.tableroGenerado) { T.notify("Genera el tablero y espera a que termine."); return false; }
        return true;
      }
      return true;
    },

    async onNext() {
      if (T.state.step === 0 && T.WIZARDS.analizar.pasos[T.state.step + 1]?.id === "revision") {
        await runRevision();
      }
    },
  };
})();
