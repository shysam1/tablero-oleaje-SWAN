"""
Protege la corrida SWAN del Power Throttling (EcoQoS) de Windows.

SWAN corre monohilo: su velocidad depende de la frecuencia del único núcleo que
usa. Con el plan de energía "Equilibrado", Windows 11 baja esa frecuencia cuando
la ventana de la app se minimiza (la clasifica como "en segundo plano"), y la
corrida se vuelve ~1.5-2x más lenta. Aquí se exime a swan.exe de ese throttling
(correr siempre a máxima frecuencia) y se le sube la prioridad un escalón, de modo
que minimizar la ventana deja de afectar el tiempo de cálculo.

Fuera de Windows todo queda en no-ops, para no romper imports en otros sistemas.
"""

import sys
import time

_ES_WINDOWS = sys.platform == "win32"

if _ES_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _PROCESS_SET_INFORMATION = 0x0200
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000

    _ProcessPowerThrottling = 4
    _POWER_THROTTLING_CURRENT_VERSION = 1
    _POWER_THROTTLING_EXECUTION_SPEED = 0x1

    _TH32CS_SNAPPROCESS = 0x00000002
    _INVALID_HANDLE = wintypes.HANDLE(-1).value

    class _PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        ]

    class _PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _pids_por_nombre(nombre, padre=None):
    """PIDs de procesos cuyo ejecutable coincide con `nombre`; opcional filtro por padre."""
    pids = []
    snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == _INVALID_HANDLE:
        return pids
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        objetivo = nombre.lower().encode()
        ok = _k32.Process32First(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == objetivo:
                if padre is None or entry.th32ParentProcessID == padre:
                    pids.append(entry.th32ProcessID)
            ok = _k32.Process32Next(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return pids


def _mapa_padres():
    """Dict pid → ppid de todos los procesos visibles."""
    padres = {}
    snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == _INVALID_HANDLE:
        return padres
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        ok = _k32.Process32First(snap, ctypes.byref(entry))
        while ok:
            padres[entry.th32ProcessID] = entry.th32ParentProcessID
            ok = _k32.Process32Next(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return padres


def _es_descendiente(pid, ancestro, padres):
    """True si `pid` es el proceso `ancestro` o un hijo suyo."""
    visto = set()
    while pid and pid not in visto:
        if pid == ancestro:
            return True
        visto.add(pid)
        pid = padres.get(pid)
    return False


def proteger_pid(pid):
    """
    Exime al proceso `pid` del Power Throttling (máxima frecuencia siempre) y le
    sube la prioridad a ABOVE_NORMAL. Devuelve True si se aplicó.
    """
    if not _ES_WINDOWS:
        return False
    h = _k32.OpenProcess(
        _PROCESS_SET_INFORMATION | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    try:
        # ControlMask activa la palanca de velocidad; StateMask=0 => "no throttlear".
        st = _PROCESS_POWER_THROTTLING_STATE(
            _POWER_THROTTLING_CURRENT_VERSION,
            _POWER_THROTTLING_EXECUTION_SPEED,
            0)
        _k32.SetProcessInformation(
            h, _ProcessPowerThrottling, ctypes.byref(st), ctypes.sizeof(st))
        _k32.SetPriorityClass(h, _ABOVE_NORMAL_PRIORITY_CLASS)
        return True
    finally:
        _k32.CloseHandle(h)


def proteger_swan(timeout=30.0, intervalo=0.3, log=None, launcher_pid=None):
    """
    Espera a que aparezca swan.exe (lo lanza swanrun) y lo protege del throttling.

    Si se pasa `launcher_pid` (PID del cmd/swanrun que lanzamos), solo se protege
    un swan.exe descendiente de ese proceso. Devuelve el PID protegido o None.
    """
    if not _ES_WINDOWS:
        return None
    plazo = time.monotonic() + timeout
    while time.monotonic() < plazo:
        padres = _mapa_padres() if launcher_pid else {}
        candidatos = _pids_por_nombre("swan.exe")
        for pid in candidatos:
            if launcher_pid and not _es_descendiente(pid, launcher_pid, padres):
                continue
            if proteger_pid(pid):
                if log:
                    log(f"[velocidad] swan.exe protegido del throttling "
                        f"(PID {pid}, prioridad alta, frecuencia máxima).")
                return pid
        time.sleep(intervalo)
    return None
