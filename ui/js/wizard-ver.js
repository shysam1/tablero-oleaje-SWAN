/* Wizard — Ver corrida SWAN */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;

  function aplicarInfoCarpetaSwan(info) {
    if (!info) return;
    T.state.ctx.casos_txt = info.casos?.length
      ? "Casos: " + info.casos.join(", ")
      : "Sin .swn detectados.";
    T.state.ctx.nonst = info.nonst;
    T.state.ctx.tipo_resumen = info.resumen || "";
    if (info.utm_x != null && info.utm_y != null) {
      T.state.ctx.utm_x = String(info.utm_x);
      T.state.ctx.utm_y = String(info.utm_y);
      T.state.ctx.utm_origen = info.origen;
      T.state.ctx.utm_mensaje = info.mensaje || "";
    }
  }

  T.wizardVer = {
    renderStep(id) {
      document.getElementById("step-body").innerHTML = this.stepHtml(id);
      this.bind(id);
    },

    stepHtml(id) {
      if (id === "carpeta") return `<div class="form-card">
        <label class="field">Carpeta SWAN
          <div class="field-row">
            <input id="ver-carpeta" readonly value="${T.esc(T.state.ctx.carpeta || "")}"/>
            <button type="button" class="btn secondary" id="ver-pick">Carpeta…</button>
          </div>
        </label>
        <p class="hint" id="ver-casos">${T.esc(T.state.ctx.casos_txt || "")}</p>
      </div>`;
      if (id === "tipo") return `<div class="form-card">
        <pre class="log-pre">${T.esc(T.state.ctx.tipo_resumen || "")}</pre>
        <p class="hint ${T.state.ctx.utm_mensaje ? "ok" : ""}">${T.esc(T.state.ctx.utm_mensaje || "Offset UTM del nodo (0,0) del dominio grande.")}</p>
        <div class="field-row" style="margin-top:12px">
          <label class="field">UTM X<input id="utm-x" value="${T.esc(T.state.ctx.utm_x ?? T.state.prefs.utm_x ?? "")}"/></label>
          <label class="field">UTM Y<input id="utm-y" value="${T.esc(T.state.ctx.utm_y ?? T.state.prefs.utm_y ?? "")}"/></label>
        </div>
      </div>`;
      if (id === "generar") {
        const prod = T.state.ctx.nonst ? "video multipanel" : "tablero de mapas";
        return `<div class="form-card">
          <p>Genera el ${prod}. La vista previa aparece abajo (PNG; videos se abren al terminar).</p>
          <button type="button" class="btn primary" id="ver-gen">Generar ${prod}</button>
        </div>`;
      }
      return "";
    },

    bind(id) {
      if (id === "carpeta") {
        document.getElementById("ver-pick").onclick = async () => {
          const d = await T.py("elegir_carpeta", "swan");
          if (d) {
            document.getElementById("ver-carpeta").value = d;
            T.state.ctx.carpeta = d;
            const info = await T.py("info_carpeta_swan", d);
            aplicarInfoCarpetaSwan(info);
            document.getElementById("ver-casos").textContent = T.state.ctx.casos_txt;
          }
        };
      }
      if (id === "generar") {
        document.getElementById("ver-gen").onclick = async () => {
          T.showLog();
          T.setStatus("Generando…", "proc");
          const start = await T.py("generar_producto_ver", JSON.stringify(T.state.ctx));
          if (!start?.ok) return;
          const done = await T.waitTask("ver_producto");
          if (done.ok) {
            T.state.productoGenerado = true;
            T.appendLog("Resultado: " + done.result.ruta);
            T.setStatus("Listo.");
            if (done.result.preview) {
              T.showPreview("preview-box", done.result.preview, done.result.ruta);
            }
            T.py("abrir_archivo", done.result.ruta);
          } else { T.appendLog(done.error); T.setStatus("Error.", "err"); }
        };
      }
    },

    collectStep() {
      if (T.state.step === 0) {
        T.state.ctx.carpeta = document.getElementById("ver-carpeta")?.value || T.state.ctx.carpeta;
      }
      if (T.state.step === 1) {
        T.state.ctx.utm_x = document.getElementById("utm-x")?.value;
        T.state.ctx.utm_y = document.getElementById("utm-y")?.value;
        T.state.prefs.utm_x = T.state.ctx.utm_x;
        T.state.prefs.utm_y = T.state.ctx.utm_y;
        T.guardarPrefs();
        const ux = parseFloat(T.state.ctx.utm_x);
        const uy = parseFloat(T.state.ctx.utm_y);
        T.state.ctx.utm_large = (Number.isFinite(ux) && Number.isFinite(uy)) ? [ux, uy] : null;
      }
    },

    async validate() {
      T.clearFieldErrors();
      const id = T.WIZARDS.ver.pasos[T.state.step].id;
      if (id === "carpeta") {
        const d = document.getElementById("ver-carpeta")?.value || T.state.ctx.carpeta;
        if (!d) { T.notify("Elige una carpeta."); return false; }
        T.state.ctx.carpeta = d;
        return true;
      }
      if (id === "tipo") return true;
      if (id === "generar") {
        if (!T.state.productoGenerado) { T.notify("Genera el producto primero."); return false; }
        return true;
      }
      return true;
    },

    async onNext() {
      if (T.state.step === 0) {
        const info = await T.py("info_carpeta_swan", T.state.ctx.carpeta);
        aplicarInfoCarpetaSwan(info);
      }
    },
  };
})();
