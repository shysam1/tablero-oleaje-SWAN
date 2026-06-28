/* Feedback inline (reemplaza alert) */
window.Tablero = window.Tablero || {};

(() => {
  const T = window.Tablero;

  T.notify = (msg, kind = "err") => {
    const el = document.getElementById("inline-error");
    if (el) {
      el.textContent = msg;
      el.className = "inline-error" + (kind === "ok" ? " ok" : kind === "warn" ? " warn" : "");
      el.classList.remove("hidden");
      return;
    }
    T.setStatus(msg, kind === "ok" ? "listo" : "err");
  };

  T.clearNotify = () => {
    const el = document.getElementById("inline-error");
    if (el) { el.textContent = ""; el.classList.add("hidden"); }
  };

  T.fieldError = (id, msg) => {
    const f = document.getElementById(id)?.closest(".field") || document.getElementById(id)?.parentElement;
    if (f) {
      f.classList.add("field-error");
      let hint = f.querySelector(".field-err-msg");
      if (!hint) {
        hint = document.createElement("span");
        hint.className = "field-err-msg";
        f.appendChild(hint);
      }
      hint.textContent = msg;
    }
    T.notify(msg);
  };

  T.clearFieldErrors = () => {
    document.querySelectorAll(".field-error").forEach((f) => f.classList.remove("field-error"));
    document.querySelectorAll(".field-err-msg").forEach((e) => e.remove());
    T.clearNotify();
  };
})();
