"""
Estilos compartidos del Tablero de Oleaje (inspiración visual macOS).

Centraliza paleta, ttk, stepper, sidebar, tarjetas e iconos de inicio.
"""

from pathlib import Path
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

RUTA_BASE = Path(__file__).resolve().parent
RUTA_ICONOS = RUTA_BASE / "assets" / "icons"
_VERSION_ICONOS = 2

# Ancho por debajo del cual tarjetas se apilan y el sidebar se oculta.
ANCHURA_APILADA = 720
ANCHO_SIDEBAR = 188

PALETA = {
    "primario": "#007aff",
    "primario_oscuro": "#0066d6",
    "acento": "#5ac8fa",
    "fondo": "#f5f5f7",
    "sidebar": "#ececec",
    "fondo_tarjeta": "#ffffff",
    "texto": "#1d1d1f",
    "texto_secundario": "#6e6e73",
    "borde": "#d1d1d6",
    "borde_suave": "#e5e5ea",
    "listo": "#007aff",
    "procesando": "#ff9500",
    "error": "#ff3b30",
    "analizar": "#007aff",
    "modelar": "#30b0c7",
    "ver": "#af52de",
    "analizar_fondo": "#e8f2ff",
    "modelar_fondo": "#e8f7fa",
    "ver_fondo": "#f3e8fa",
    "nav_activo": "#d6e8ff",
}

FUENTE_UI = ("Segoe UI",)
FUENTE_TITULO = ("Segoe UI", 22, "bold")
FUENTE_SUBTITULO = ("Segoe UI", 13)
FUENTE_TARJETA = ("Segoe UI", 12, "bold")
FUENTE_NAV = ("Segoe UI", 11)
FUENTE_NAV_SECCION = ("Segoe UI", 9, "bold")
FUENTE_BOTON = ("Segoe UI", 10)
FUENTE_STEPPER = ("Segoe UI", 9)


def aplicar_tema(root):
    """Configura ttk «clam» con paleta tipo macOS."""
    root.configure(bg=PALETA["fondo"])
    estilo = ttk.Style(root)
    try:
        estilo.theme_use("clam")
    except tk.TclError:
        pass

    fondo = PALETA["fondo"]
    estilo.configure(".", background=fondo, foreground=PALETA["texto"])
    estilo.configure("TFrame", background=fondo)
    estilo.configure("Sidebar.TFrame", background=PALETA["sidebar"])
    estilo.configure("TLabel", background=fondo, foreground=PALETA["texto"],
                     font=FUENTE_UI)
    estilo.configure("Card.TFrame", background=PALETA["fondo_tarjeta"])
    estilo.configure("Muted.TLabel", background=fondo,
                     foreground=PALETA["texto_secundario"])
    estilo.configure("SidebarMuted.TLabel", background=PALETA["sidebar"],
                     foreground=PALETA["texto_secundario"],
                     font=FUENTE_NAV_SECCION)
    estilo.configure("SidebarNav.TLabel", background=PALETA["sidebar"],
                     foreground=PALETA["texto"], font=FUENTE_NAV)
    estilo.configure("SidebarNavActivo.TLabel", background=PALETA["nav_activo"],
                     foreground=PALETA["primario"], font=("Segoe UI", 11, "bold"))
    estilo.configure("CardMuted.TLabel",
                     background=PALETA["fondo_tarjeta"],
                     foreground=PALETA["texto_secundario"])
    estilo.configure("CardTitle.TLabel",
                     background=PALETA["fondo_tarjeta"],
                     foreground=PALETA["texto"],
                     font=FUENTE_TARJETA)
    estilo.configure("Titulo.TLabel", font=FUENTE_TITULO, foreground=PALETA["texto"])
    estilo.configure("Subtitulo.TLabel", font=FUENTE_SUBTITULO,
                     foreground=PALETA["texto_secundario"])
    estilo.configure("WizardTitulo.TLabel", font=("Segoe UI", 17, "bold"),
                     foreground=PALETA["texto"])

    estilo.configure("EstadoListo.TLabel",
                     foreground=PALETA["listo"], background=fondo,
                     font=("Segoe UI", 10))
    estilo.configure("EstadoProcesando.TLabel",
                     foreground=PALETA["procesando"], background=fondo,
                     font=("Segoe UI", 10))
    estilo.configure("EstadoError.TLabel",
                     foreground=PALETA["error"], background=fondo,
                     font=("Segoe UI", 10))

    estilo.configure("TButton", padding=(12, 6), font=FUENTE_BOTON)
    estilo.configure("Primary.TButton",
                     background=PALETA["primario"],
                     foreground="#ffffff",
                     font=FUENTE_BOTON,
                     padding=(16, 8))
    estilo.map("Primary.TButton",
               background=[("active", PALETA["primario_oscuro"]),
                           ("pressed", "#0055b3")],
               foreground=[("disabled", "#aeaeb2"), ("!disabled", "#ffffff")])

    estilo.configure("Secondary.TButton",
                     background=PALETA["fondo_tarjeta"],
                     foreground=PALETA["texto"],
                     padding=(12, 6))
    estilo.map("Secondary.TButton",
               background=[("active", PALETA["borde_suave"])])

    estilo.configure("TEntry", padding=6, fieldbackground="#fafafa")
    estilo.configure("TProgressbar", troughcolor=PALETA["borde_suave"],
                     background=PALETA["primario"])
    estilo.configure("TNotebook", background=fondo)
    estilo.configure("TNotebook.Tab", padding=(12, 6), font=FUENTE_BOTON)


def configurar_estado(widget, estado):
    """Aplica estilo de estado a un ttk.Label."""
    mapa = {
        "listo": "EstadoListo.TLabel",
        "procesando": "EstadoProcesando.TLabel",
        "error": "EstadoError.TLabel",
    }
    widget.configure(style=mapa.get(estado, "TLabel"))


class PanelTarjeta(tk.Frame):
    """Panel blanco con borde suave (formularios del wizard)."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=PALETA["borde"], highlightthickness=0, **kw)
        self.cuerpo = tk.Frame(self, bg=PALETA["fondo_tarjeta"], padx=18, pady=16)
        self.cuerpo.pack(fill="both", expand=True, padx=1, pady=1)


class Stepper(tk.Canvas):
    """Barra de pasos con círculos y líneas (estilo instalador Mac)."""

    _RADIO = 11
    _ALTO = 56

    def __init__(self, master, titulos, **kw):
        super().__init__(master, height=self._ALTO, highlightthickness=0,
                         bg=PALETA["fondo"], **kw)
        self._titulos = list(titulos)
        self._indice = 0
        self.bind("<Configure>", self._redibujar)

    def actualizar(self, indice):
        self._indice = indice
        self._redibujar()

    def _abreviar(self, texto, max_len=11):
        t = texto.replace("\n", " ").strip()
        return t if len(t) <= max_len else t[: max_len - 1] + "…"

    def _redibujar(self, _event=None):
        self.delete("all")
        n = len(self._titulos)
        w = self.winfo_width()
        if n == 0 or w < 20:
            return

        paso = max(72, w // n)
        x0 = paso / 2
        y_circ = 16
        fuente = tkfont.Font(family="Segoe UI", size=9)
        fuente_b = tkfont.Font(family="Segoe UI", size=9, weight="bold")

        for i in range(n):
            cx = x0 + i * paso
            if i < self._indice:
                self.create_oval(cx - self._RADIO, y_circ - self._RADIO,
                                 cx + self._RADIO, y_circ + self._RADIO,
                                 fill=PALETA["primario"], outline=PALETA["primario"])
                self.create_text(cx, y_circ, text="✓", fill="#ffffff",
                                 font=("Segoe UI", 9, "bold"))
            elif i == self._indice:
                self.create_oval(cx - self._RADIO - 2, y_circ - self._RADIO - 2,
                                 cx + self._RADIO + 2, y_circ + self._RADIO + 2,
                                 outline=PALETA["primario"], width=2)
                self.create_oval(cx - self._RADIO, y_circ - self._RADIO,
                                 cx + self._RADIO, y_circ + self._RADIO,
                                 fill=PALETA["primario"], outline=PALETA["primario"])
                self.create_text(cx, y_circ, text=str(i + 1), fill="#ffffff",
                                 font=("Segoe UI", 9, "bold"))
            else:
                self.create_oval(cx - self._RADIO, y_circ - self._RADIO,
                                 cx + self._RADIO, y_circ + self._RADIO,
                                 fill=PALETA["borde_suave"], outline=PALETA["borde_suave"])
                self.create_text(cx, y_circ, text=str(i + 1),
                                 fill=PALETA["texto_secundario"],
                                 font=("Segoe UI", 9))

            etiqueta = self._abreviar(self._titulos[i])
            f = fuente_b if i == self._indice else fuente
            color = PALETA["texto"] if i == self._indice else PALETA["texto_secundario"]
            self.create_text(cx, y_circ + 22, text=etiqueta, fill=color, font=f)

            if i < n - 1:
                x1 = cx + self._RADIO + 4
                x2 = cx + paso - self._RADIO - 4
                color_ln = PALETA["primario"] if i < self._indice else PALETA["borde_suave"]
                self.create_line(x1, y_circ, x2, y_circ, fill=color_ln, width=2)


class TarjetaCamino(tk.Frame):
    """Tarjeta de inicio: franja superior de color, icono en pastilla y enlace."""

    def __init__(self, master, titulo, desc, destino, icono, color_acento,
                 fondo_icono, ir_a):
        super().__init__(master, bg=PALETA["borde"], highlightthickness=0, cursor="hand2")
        self._destino = destino
        self._ir_a = ir_a
        self._wraplength = 220
        self._hover = False

        cuerpo = tk.Frame(self, bg=PALETA["fondo_tarjeta"])
        cuerpo.pack(fill="both", expand=True, padx=1, pady=1)

        franja = tk.Frame(cuerpo, bg=color_acento, height=3)
        franja.pack(fill="x")
        franja.pack_propagate(False)

        interior = tk.Frame(cuerpo, bg=PALETA["fondo_tarjeta"], padx=16, pady=14)
        interior.pack(fill="both", expand=True)

        fila_t = tk.Frame(interior, bg=PALETA["fondo_tarjeta"])
        fila_t.pack(anchor="w", fill="x")

        pastilla = tk.Frame(fila_t, bg=fondo_icono, padx=6, pady=6)
        pastilla.pack(side="left", padx=(0, 10))
        tk.Label(pastilla, image=icono, bg=fondo_icono).pack()

        self._lbl_titulo = tk.Label(
            fila_t, text=titulo, font=FUENTE_TARJETA, justify="left",
            bg=PALETA["fondo_tarjeta"], fg=PALETA["texto"])
        self._lbl_titulo.pack(side="left", anchor="nw")

        self._lbl_desc = tk.Label(
            interior, text=desc, justify="left", wraplength=self._wraplength,
            bg=PALETA["fondo_tarjeta"], fg=PALETA["texto_secundario"],
            font=("Segoe UI", 10))
        self._lbl_desc.pack(anchor="w", pady=(10, 12))

        self._lbl_link = tk.Label(
            interior, text="Empezar →", font=("Segoe UI", 10),
            fg=PALETA["primario"], bg=PALETA["fondo_tarjeta"], cursor="hand2")
        self._lbl_link.pack(anchor="w")

        widgets = (self, cuerpo, interior, fila_t, pastilla,
                   self._lbl_titulo, self._lbl_desc, self._lbl_link)
        for w in widgets:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)
        self._lbl_link.bind("<Enter>", lambda e: self._lbl_link.configure(
            fg=PALETA["primario_oscuro"]))
        self._lbl_link.bind("<Leave>", lambda e: self._lbl_link.configure(
            fg=PALETA["primario"]))

    def _on_enter(self, _event=None):
        self._hover = True
        self.configure(bg=PALETA["primario"])

    def _on_leave(self, _event=None):
        self._hover = False
        self.configure(bg=PALETA["borde"])

    def _on_click(self, _event=None):
        self._ir_a(self._destino)

    def ajustar_ancho(self, ancho_contenedor, apilado):
        if apilado:
            self._wraplength = max(280, ancho_contenedor - 100)
        else:
            self._wraplength = max(150, (ancho_contenedor - 56) // 3 - 70)
        self._lbl_desc.configure(wraplength=self._wraplength)


def _marcador_iconos():
    return RUTA_ICONOS / ".version"


def _generar_iconos_en_disco():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    RUTA_ICONOS.mkdir(parents=True, exist_ok=True)

    def _guardar(fig, nombre):
        fig.savefig(RUTA_ICONOS / nombre, dpi=96, bbox_inches="tight",
                    pad_inches=0.05, transparent=True)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(0.55, 0.55))
    ax.set_facecolor("none")
    fig.patch.set_alpha(0)
    x = np.linspace(0, 4, 40)
    ax.plot(x, 0.35 + 0.25 * np.sin(x) + 0.08 * x,
            color=PALETA["analizar"], lw=2.5)
    ax.axis("off")
    _guardar(fig, "analizar.png")

    fig, ax = plt.subplots(figsize=(0.55, 0.55))
    ax.set_facecolor("none")
    fig.patch.set_alpha(0)
    x = np.linspace(0, 2 * np.pi, 80)
    for i, amp in enumerate((0.22, 0.14, 0.09)):
        ax.plot(x, amp * np.sin(x * (1.2 + i * 0.35) + i),
                color=PALETA["modelar"], lw=2.2 - i * 0.3)
    ax.axis("off")
    _guardar(fig, "modelar.png")

    fig, ax = plt.subplots(figsize=(0.55, 0.55))
    ax.set_facecolor("none")
    fig.patch.set_alpha(0)
    for i in range(4):
        ax.axhline(i * 0.33, color=PALETA["ver"], lw=1.2, alpha=0.35)
        ax.axvline(i * 0.33, color=PALETA["ver"], lw=1.2, alpha=0.35)
    ax.add_patch(plt.Rectangle((0.08, 0.12), 0.55, 0.45,
                               fill=True, facecolor=PALETA["ver"], alpha=0.25,
                               edgecolor=PALETA["ver"], lw=2))
    ax.axis("off")
    _guardar(fig, "ver.png")

    _marcador_iconos().write_text(str(_VERSION_ICONOS), encoding="utf-8")


def asegurar_iconos_en_disco():
    marcador = _marcador_iconos()
    if marcador.exists() and marcador.read_text(encoding="utf-8") == str(_VERSION_ICONOS):
        if all((RUTA_ICONOS / f"{n}.png").exists()
               for n in ("analizar", "modelar", "ver")):
            return
    _generar_iconos_en_disco()


def cargar_iconos(root):
    asegurar_iconos_en_disco()
    iconos = {}
    for nombre in ("analizar", "modelar", "ver"):
        iconos[nombre] = tk.PhotoImage(
            file=str(RUTA_ICONOS / f"{nombre}.png"), master=root)
    return iconos
