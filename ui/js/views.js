/* Vistas: inicio, avanzado, credenciales, caché, acerca */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;

  function htmlProcesarSwanPanel() {
    return `<div class="form-card" id="swan-web-panel">
          <p class="hint">Elige la carpeta del caso (contiene el <code>.swn</code>, batimetría y archivos de entrada).</p>
          <div class="field-row">
            <input type="text" id="swan-carpeta" readonly placeholder="Carpeta con .swn" style="flex:1"/>
            <button type="button" class="btn secondary" id="swan-pick">Carpeta…</button>
          </div>
          <div class="field-row" style="margin-top:8px">
            <button type="button" class="btn primary" id="swan-correr">Correr caso existente</button>
            <button type="button" class="btn secondary" id="swan-cancel-adv">Cancelar</button>
            <button type="button" class="btn secondary" id="swan-wizard">Armar caso nuevo (asistente)…</button>
          </div>
        </div>`;
  }

  function shellProcesarSwan(extra = "") {
    return `${extra}
        ${htmlProcesarSwanPanel()}
        <div class="inline-error hidden" id="inline-error"></div>
        <div class="progress-wrap"><div class="progress-bar"></div></div>
        <div class="status-bar">Listo.</div>
        <div id="preview-box" class="hidden"></div>
        <div class="log-panel"><pre class="log-pre"></pre></div>`;
  }

  function bindProcesarSwan() {
    document.getElementById("swan-pick").onclick = async () => {
      const r = await T.py("elegir_carpeta", "swan");
      if (r) document.getElementById("swan-carpeta").value = r;
    };
    document.getElementById("swan-correr").onclick = async () => {
      const carpeta = document.getElementById("swan-carpeta").value;
      if (!carpeta) { T.notify("Elige la carpeta del caso."); return; }
      T.showLog();
      T.setStatus("Corriendo SWAN…", "proc");
      const start = await T.py("correr_swan_existente", carpeta);
      if (!start?.ok) { T.notify(start?.error); return; }
      const done = await T.waitTask("swan_existente");
      if (done.ok) {
        T.appendLog(done.result.log);
        T.setStatus("Listo.");
      } else {
        T.appendLog(done.error || done.result?.log);
        T.setStatus("Error.", "err");
      }
    };
    document.getElementById("swan-cancel-adv").onclick = () => T.py("cancelar_swan");
    document.getElementById("swan-wizard").onclick = () => T.startWizard("modelar");
  }

  T.wizard = {
    collectStep() {
      if (T.state.wizard === "analizar") T.wizardAnalizar.collectStep();
      if (T.state.wizard === "modelar") T.wizardModelar.collectStep();
      if (T.state.wizard === "ver") T.wizardVer.collectStep();
    },
    async validate() {
      if (T.state.wizard === "analizar") return T.wizardAnalizar.validate();
      if (T.state.wizard === "modelar") return T.wizardModelar.validate();
      if (T.state.wizard === "ver") return T.wizardVer.validate();
      return true;
    },
    async onNext() {
      if (T.state.wizard === "analizar") await T.wizardAnalizar.onNext();
      if (T.state.wizard === "modelar") await T.wizardModelar.onNext();
      if (T.state.wizard === "ver") await T.wizardVer.onNext();
    },
    async next() {
      const ok = await this.validate();
      if (!ok) return;
      this.collectStep();
      await this.onNext();
      const w = T.WIZARDS[T.state.wizard];
      if (T.state.step >= w.pasos.length - 1) {
        T.py("limpiar_sesion_wizard");
        T.views.renderInicio();
        return;
      }
      T.state.step++;
      T.persistirSesion();
      T.renderWizard();
    },
  };

  T.views = {
    async renderInicio() {
      T.state.vista = "inicio";
      T.state.wizard = null;
      T.updateNav();
      const cds = (await T.py("estado_cds_credenciales")) || {};
      const rec = (await T.py("listar_recientes"))?.items || [];
      const ses = (await T.py("cargar_sesion_wizard"))?.sesion;
      const cdsBadge = cds.configurado
        ? `<span class="chip ok">CDS: ${T.esc(cds.key_enmascarada || cds.uid || "OK")}</span>`
        : `<span class="chip warn">CDS: sin configurar</span>`;

      let recHtml = "";
      if (rec.length) {
        recHtml = `<section class="home-section"><h3 class="section-title">Recientes</h3><div class="recientes-grid">${
          rec.slice(0, 6).map((it) => `
            <article class="rec-item" data-ruta="${T.esc(it.ruta)}">
              ${it.thumb ? `<img src="${it.thumb}" alt="" class="rec-thumb"/>` : `<div class="rec-thumb placeholder">${T.esc(it.tipo?.slice(0, 4) || "?")}</div>`}
              <span class="rec-name">${T.esc(it.nombre)}</span>
            </article>`).join("")
        }</div></section>`;
      }

      let sesHtml = "";
      if (ses?.wizard) {
        sesHtml = `<div class="resume-banner">
          <span>Sesión en curso: ${T.esc(T.WIZARDS[ses.wizard]?.titulo || ses.wizard)} (paso ${(ses.step || 0) + 1})</span>
          <button type="button" class="btn secondary btn-sm" id="resume-wizard">Continuar</button>
          <button type="button" class="btn link btn-sm" id="discard-wizard">Descartar</button>
        </div>`;
      }

      const p = T.state.prefs;
      const repeatEra5 = p.era5_lat ? `<button type="button" class="btn secondary btn-sm" id="repeat-era5">Repetir último ERA5 (${T.esc(p.era5_lat)}, ${T.esc(p.era5_lon)})</button>` : "";

      T.main().innerHTML = `
        <h2 class="hero-title">¿Qué quieres hacer?</h2>
        <p class="hero-sub">Elige un flujo guiado o abre las herramientas sueltas. ${cdsBadge}</p>
        ${sesHtml}
        ${repeatEra5 ? `<p class="home-actions">${repeatEra5}</p>` : ""}
        <div class="cards">
          <article class="card analizar" data-wizard="analizar">
            <div class="card-head"><div class="card-icon">${T.ICONS.analizar}</div><h3>Analizar oleaje<br>en un punto</h3></div>
            <p>Datos propios o ERA5 → curvas, partición sea/swell y régimen extremo.</p>
            <span class="card-link">Empezar →</span>
          </article>
          <article class="card modelar" data-wizard="modelar">
            <div class="card-head"><div class="card-icon">${T.ICONS.modelar}</div><h3>Modelar propagación<br>con SWAN</h3></div>
            <p>Malla → batimetría → borde → correr → mapas.</p>
            <span class="card-link">Empezar →</span>
          </article>
          <article class="card procesar" data-vista="procesar">
            <div class="card-head"><div class="card-icon">${T.ICONS.procesar}</div><h3>Procesar SWAN<br>(caso existente)</h3></div>
            <p>Ya tienes <code>.swn</code> y batimetría → ejecuta SWAN sin el asistente.</p>
            <span class="card-link">Abrir →</span>
          </article>
          <article class="card ver" data-wizard="ver">
            <div class="card-head"><div class="card-icon">${T.ICONS.ver}</div><h3>Ver una corrida<br>SWAN ya hecha</h3></div>
            <p>Mapas estacionarios o video multipanel no estacionario.</p>
            <span class="card-link">Empezar →</span>
          </article>
        </div>
        ${recHtml}
        <footer class="footer">
          <span>Creado por Javier Tarrazón</span>
          <button type="button" class="btn link" id="go-avanzado">Herramientas sueltas →</button>
        </footer>`;

      T.main().querySelectorAll(".card").forEach((c) =>
        c.addEventListener("click", () => {
          if (c.dataset.vista === "procesar") T.views.renderProcesarSwan();
          else T.startWizard(c.dataset.wizard);
        }));
      document.getElementById("go-avanzado").onclick = () => T.views.renderAvanzado();
      document.getElementById("resume-wizard")?.addEventListener("click", () => {
        T.startWizard(ses.wizard, ses.ctx || {}, ses.step || 0);
      });
      document.getElementById("discard-wizard")?.addEventListener("click", async () => {
        await T.py("limpiar_sesion_wizard");
        T.views.renderInicio();
      });
      document.getElementById("repeat-era5")?.addEventListener("click", () => {
        T.startWizard("analizar", { modo: "era5", era5: { lat: p.era5_lat, lon: p.era5_lon, inicio: p.era5_inicio, fin: p.era5_fin, viento: true, espectro: false } });
      });
      T.main().querySelectorAll(".rec-item").forEach((el) => {
        el.onclick = () => {
          T.py("abrir_archivo", el.dataset.ruta);
        };
      });
    },

    renderProcesarSwan() {
      T.state.vista = "procesar";
      T.state.wizard = null;
      T.updateNav();
      T.main().innerHTML = shellProcesarSwan(`
        <button type="button" class="btn link" id="go-inicio" style="margin-bottom:8px">← Inicio</button>
        <h2 class="hero-title" style="font-size:22px">Procesar SWAN</h2>
        <p class="hero-sub">Corre un caso que ya tienes armado en una carpeta (.swn, .bot y condiciones de borde).</p>`);
      T.state.log = "";
      bindProcesarSwan();
      document.getElementById("go-inicio").onclick = () => T.views.renderInicio();
    },

    renderAvanzado() {
      T.state.vista = "avanzado";
      T.state.wizard = null;
      T.updateNav();
      const p = T.state.prefs;
      T.main().innerHTML = `
        <h2 class="hero-title" style="font-size:22px">Modo avanzado</h2>
        <p class="hero-sub">Serie → curvas · SWAN estacionaria → mapas · no estacionaria → video multipanel.</p>
        <div class="form-card">
          <div class="field-row">
            <input type="text" id="adv-ruta" placeholder="Archivo o carpeta SWAN" style="flex:1"/>
            <button type="button" class="btn secondary" id="adv-arch">Archivo…</button>
            <button type="button" class="btn secondary" id="adv-dir">Carpeta…</button>
          </div>
          <div class="field-row" style="margin-top:12px">
            <button type="button" class="btn primary" id="adv-crear">Crear</button>
          </div>
          <div class="field-row" style="margin-top:12px">
            <label class="field">UTM X<input id="adv-ux" value="${T.esc(p.utm_x || "620494")}"/></label>
            <label class="field">UTM Y<input id="adv-uy" value="${T.esc(p.utm_y || "5876451")}"/></label>
          </div>
        </div>
        <h3 class="section-title" style="margin-top:20px">Procesar SWAN</h3>
        <p class="hint">Mismo panel que en la página principal — corre un caso existente o abre el asistente.</p>
        ${htmlProcesarSwanPanel()}
        <div class="inline-error hidden" id="inline-error"></div>
        <div class="progress-wrap"><div class="progress-bar"></div></div>
        <div class="status-bar">Listo.</div>
        <div id="preview-box" class="hidden"></div>
        <div class="log-panel"><pre class="log-pre"></pre></div>`;
      T.state.log = "";
      document.getElementById("adv-arch").onclick = async () => {
        const r = await T.py("elegir_archivo", "oleaje");
        if (r) document.getElementById("adv-ruta").value = r;
      };
      document.getElementById("adv-dir").onclick = async () => {
        const r = await T.py("elegir_carpeta", "swan");
        if (r) document.getElementById("adv-ruta").value = r;
      };
      document.getElementById("adv-crear").onclick = async () => {
        const ruta = document.getElementById("adv-ruta").value;
        if (!ruta) { T.notify("Selecciona entrada."); return; }
        T.showLog();
        T.setStatus("Procesando…", "proc");
        T.state.prefs.utm_x = document.getElementById("adv-ux").value;
        T.state.prefs.utm_y = document.getElementById("adv-uy").value;
        T.guardarPrefs();
        const start = await T.py("despachar_avanzado", ruta,
          document.getElementById("adv-ux").value,
          document.getElementById("adv-uy").value);
        if (!start?.ok) { T.notify(start?.error); return; }
        const done = await T.waitTask("avanzado");
        if (done.ok) {
          T.appendLog("Resultado: " + done.result.ruta);
          T.setStatus("Listo.");
          T.showPreview("preview-box", done.result.preview, done.result.ruta);
        } else {
          T.appendLog(done.error);
          T.setStatus("Error.", "err");
        }
      };
      bindProcesarSwan();
    },

    async renderCredenciales() {
      T.state.vista = "credenciales";
      T.state.wizard = null;
      T.updateNav();
      const st = (await T.py("estado_cds_credenciales")) || { configurado: false };
      const badgeCls = st.configurado ? "ok" : "pending";
      const badgeTxt = st.configurado
        ? `Configurado (${T.esc(st.key_enmascarada || st.uid)})`
        : "Sin configurar";
      T.main().innerHTML = `
        <h2 class="hero-title" style="font-size:22px">Credenciales ERA5 (Copernicus CDS)</h2>
        <p class="hero-sub">Cada persona usa su propia cuenta gratis. La clave se guarda solo en este equipo.</p>
        <div class="form-card">
          <div class="cds-status ${badgeCls}" id="cds-status">${badgeTxt}</div>
          <p class="hint">Archivo: <code id="cds-ruta">${T.esc(st.ruta || "")}</code></p>
          <ol class="instr-list">
            <li>Crea una cuenta en <a href="#" id="cds-open-web">cds.climate.copernicus.eu</a>.</li>
            <li>Acepta los términos del dataset <em>ERA5 single levels</em>.</li>
            <li>Copia tu Personal Access Token (o el formato antiguo <code>UID:API-KEY</code>) y pégala abajo.</li>
          </ol>
          <label class="field">URL del API
            <input type="text" id="cds-url" value="${T.esc(st.url || "https://cds.climate.copernicus.eu/api")}"/>
          </label>
          <label class="field">Clave API
            <input type="password" id="cds-key" autocomplete="off"
              placeholder="${st.configurado ? "Vacío = conservar clave actual" : "Personal Access Token o UID:API-KEY"}"/>
          </label>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
            <button type="button" class="btn primary" id="cds-guardar">Guardar</button>
            <button type="button" class="btn secondary" id="cds-probar">Probar conexión</button>
          </div>
          <p class="hint" id="cds-msg"></p>
        </div>`;
      document.getElementById("cds-open-web").onclick = (ev) => {
        ev.preventDefault();
        T.py("abrir_url_externa", "https://cds.climate.copernicus.eu");
      };
      const setCdsMsg = (text, kind = "") => {
        const el = document.getElementById("cds-msg");
        if (!el) return;
        el.textContent = text;
        el.className = "hint" + (kind ? ` ${kind}` : "");
      };
      document.getElementById("cds-guardar").onclick = async () => {
        const res = await T.py("guardar_cds_credenciales",
          document.getElementById("cds-url").value,
          document.getElementById("cds-key").value);
        if (res?.ok) {
          document.getElementById("cds-key").value = "";
          setCdsMsg(res.mensaje || "Guardado.", "ok");
        } else setCdsMsg(res?.error || "Error.", "err");
      };
      document.getElementById("cds-probar").onclick = async () => {
        setCdsMsg("Probando…");
        const res = await T.py("probar_cds_credenciales",
          document.getElementById("cds-url").value,
          document.getElementById("cds-key").value);
        setCdsMsg(res?.ok ? (res.mensaje || "OK") : (res?.error || "Error"), res?.ok ? "ok" : "err");
      };
    },

    async renderCache() {
      T.state.vista = "cache";
      T.state.wizard = null;
      T.updateNav();
      const items = (await T.py("listar_cache_era5"))?.items || [];
      const rows = items.length ? items.map((it) => `
        <tr>
          <td>${T.esc(it.nombre)}</td>
          <td>${it.tiene_serie ? "✓" : "—"}</td>
          <td>${it.tiene_espectro ? "✓" : "—"}</td>
          <td>${it.mb} MB</td>
          <td><button type="button" class="btn link btn-sm" data-del="${T.esc(it.carpeta)}">Borrar</button></td>
        </tr>`).join("") : `<tr><td colspan="5">No hay descargas ERA5 guardadas.</td></tr>`;

      T.main().innerHTML = `
        <h2 class="hero-title" style="font-size:22px">Caché ERA5</h2>
        <p class="hero-sub">Descargas guardadas en salidas/. Borrar libera espacio; los tramos en chunks/ se eliminan con la carpeta.</p>
        <div class="form-card table-wrap">
          <table class="data-table">
            <thead><tr><th>Carpeta</th><th>Serie</th><th>Espectro</th><th>Tamaño</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
      T.main().querySelectorAll("[data-del]").forEach((btn) => {
        btn.onclick = async () => {
          if (!await T.askConfirm("¿Borrar esta descarga ERA5?")) return;
          const res = await T.py("eliminar_cache_era5", btn.dataset.del);
          if (res?.ok) T.views.renderCache();
          else T.notify(res?.error || "No se pudo borrar.");
        };
      });
    },

    async renderAcerca() {
      T.state.vista = "acerca";
      T.state.wizard = null;
      T.updateNav();
      const info = (await T.py("info_aplicacion")) || {};
      T.main().innerHTML = `
        <h2 class="hero-title" style="font-size:22px">Acerca de</h2>
        <div class="form-card about-box">
          <p><strong>Tablero de Oleaje</strong></p>
          <p>Versión: ${T.esc(info.version || "—")}</p>
          <p>Python: ${T.esc(info.python || "—")}</p>
          <p>Salidas: <code>${T.esc(info.salidas || "")}</code></p>
          <p>Repositorio: <code>${T.esc(info.repo || "")}</code></p>
          <p class="hint">Documentación: README.md y HANDOFF.md en la carpeta del proyecto.</p>
          <button type="button" class="btn secondary" id="abrir-salidas">Abrir carpeta salidas</button>
        </div>`;
      document.getElementById("abrir-salidas").onclick = () => {
        if (info.salidas) T.py("abrir_en_explorador", info.salidas);
      };
    },
  };
})();
