/* Bootstrap — navegación, atajos, arranque */
window.addEventListener("pywebviewready", () => {
  console.log("API lista");
  Tablero.cargarPrefs().then(() => Tablero.views.renderInicio());
});

document.addEventListener("DOMContentLoaded", () => {
  if (window.pywebview?.api) {
    Tablero.cargarPrefs().then(() => Tablero.views.renderInicio());
  }
});

document.querySelectorAll(".nav-item").forEach((n) => {
  n.onclick = () => {
    if (n.dataset.nav === "inicio") Tablero.views.renderInicio();
    if (n.dataset.nav === "avanzado") Tablero.views.renderAvanzado();
    if (n.dataset.nav === "credenciales") Tablero.views.renderCredenciales();
    if (n.dataset.nav === "cache") Tablero.views.renderCache();
    if (n.dataset.nav === "acerca") Tablero.views.renderAcerca();
  };
});

window.addEventListener("resize", () => Tablero.onResize());
Tablero.onResize();

document.addEventListener("keydown", (ev) => {
  if (ev.target.matches("input, textarea, select")) return;
  const T = Tablero;
  if (ev.key === "Enter" && T.state.vista === "wizard" && !T.state.busy) {
    ev.preventDefault();
    T.wizard.next();
  }
  if (ev.key === "Escape" && T.state.vista === "wizard" && T.state.step > 0) {
    ev.preventDefault();
    T.wizard.collectStep();
    T.state.step--;
    T.renderWizard();
  }
  if (ev.ctrlKey && ev.key.toLowerCase() === "l") {
    ev.preventDefault();
    T.clearLog();
  }
});
