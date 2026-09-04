"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BIOTIME · CLIENTE API                                                       ║
║                                                                             ║
║  Se conecta directamente a BioTime (ZKTeco) por su API REST y descarga:     ║
║      · Empleado.xlsx       (todos — no requiere rango de fecha)             ║
║      · Turnos.xlsx         (catálogo de turnos)                             ║
║      · Horarios.xlsx       (turnos asignados dentro del rango)             ║
║      · Transacciones.xlsx  (marcaciones dentro del rango)                  ║
║                                                                             ║
║  Con esto ya NO tienes que exportar los archivos a mano desde BioTime.      ║
║                                                                             ║
║  Uso normal (lo llama generar.py):                                          ║
║      from biotime_api import exportar_a_informacion                         ║
║      exportar_a_informacion("2026-02", "2026-05", carpeta)                  ║
║                                                                             ║
║  Uso directo desde terminal:                                                ║
║      python biotime_api.py --desde 2026-02 --hasta 2026-05                  ║
║                                                                             ║
║  Diagnóstico (para confirmar los endpoints de TU servidor):                 ║
║      python biotime_api.py --descubrir                                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import sys
import time
import calendar
from datetime import datetime, date
from pathlib import Path

# Fix Unicode output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import pandas as pd

try:
    import requests
except ImportError:
    print("\n  ✗  Falta la librería 'requests'.")
    print("     Instálala con:  pip install requests")
    print("     (o:  pip install -r requirements.txt)\n")
    sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
#  CONFIGURACIÓN  ·  cargada desde config.py (.env)
# ════════════════════════════════════════════════════════════════════════════
from config import (
    BASE_URL,
    USUARIO,
    CLAVE,
    TIMEOUT,
    PAGE_SIZE,
    VERIFY_SSL,
    EP_TOKEN,
    EP_EMPLEADOS,
    EP_DEPARTAMENTOS,
    EP_TRANSACC,
    EP_TIMEINTERVALS,
    EP_SHIFT_DETAILS,
    EP_TURNOS_CANDIDATOS,
    EP_HORARIOS_CANDIDATOS,
    validar_configuracion,
)


# ════════════════════════════════════════════════════════════════════════════
#  UTILIDADES DE CONSOLA
# ════════════════════════════════════════════════════════════════════════════

def sep(t):  print(f"\n{'═'*65}\n  {t}\n{'═'*65}")
def ok(m):   print(f"  ✓  {m}")
def info(m): print(f"  ·  {m}")
def warn(m): print(f"  ⚠  {m}")
def err(m):  print(f"  ✗  {m}")


def _rango_de_meses(desde, hasta):
    """('2026-02','2026-05') → (date(2026,2,1), date(2026,5,31))."""
    a1, m1 = (int(x) for x in desde.split("-")[:2])
    a2, m2 = (int(x) for x in hasta.split("-")[:2])
    d_ini = date(a1, m1, 1)
    d_fin = date(a2, m2, calendar.monthrange(a2, m2)[1])
    if d_fin < d_ini:
        raise ValueError(f"El período final ({hasta}) es anterior al inicial ({desde}).")
    return d_ini, d_fin


# ════════════════════════════════════════════════════════════════════════════
#  CLIENTE
# ════════════════════════════════════════════════════════════════════════════

class BioTimeClient:
    """Cliente mínimo para la API REST de BioTime (ZKTeco)."""

    def __init__(self, base_url=BASE_URL, usuario=USUARIO, clave=CLAVE,
                 timeout=TIMEOUT, verify_ssl=VERIFY_SSL):
        self.base    = base_url.rstrip("/")
        self.usuario = usuario
        self.clave   = clave
        self.timeout = timeout
        self.verify  = verify_ssl
        self.token   = None
        self.sesion  = requests.Session()
        if not verify_ssl:
            try:
                import urllib3
                urllib3.disable_warnings()
            except Exception:
                pass

    # -- autenticación -------------------------------------------------------
    def login(self):
        url = self.base + EP_TOKEN
        try:
            r = self.sesion.post(
                url,
                json={"username": self.usuario, "password": self.clave},
                headers={"Content-Type": "application/json"},
                timeout=self.timeout, verify=self.verify,
            )
        except requests.exceptions.ConnectionError:
            err(f"No pude conectar a {self.base}")
            err("Verifica que estés en la red de la empresa y que la IP/puerto sean correctos.")
            raise SystemExit(1)

        if r.status_code != 200:
            err(f"Login rechazado (HTTP {r.status_code}). Revisa usuario/clave.")
            err(f"Respuesta: {r.text[:300]}")
            raise SystemExit(1)

        data = r.json()
        self.token = data.get("token") or data.get("access") or data.get("jwt")
        if not self.token:
            err(f"El servidor respondió sin token: {data}")
            raise SystemExit(1)

        self.sesion.headers.update({
            "Authorization": f"JWT {self.token}",
            "Content-Type": "application/json",
        })
        ok(f"Autenticado en {self.base} como '{self.usuario}'")
        return self

    # -- GET paginado --------------------------------------------------------
    def _get_pagina(self, endpoint, params):
        url = self.base + endpoint if endpoint.startswith("/") else endpoint
        r = self.sesion.get(url, params=params, timeout=self.timeout, verify=self.verify)
        r.raise_for_status()
        return r.json()

    def get_todo(self, endpoint, params=None, etiqueta=""):
        """Descarga TODAS las páginas de un endpoint y devuelve una lista de dicts."""
        params = dict(params or {})
        params.setdefault("page_size", PAGE_SIZE)
        params["page"] = 1

        filas = []
        total = None
        while True:
            try:
                data = self._get_pagina(endpoint, params)
            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response is not None else "?"
                raise RuntimeError(f"{endpoint} respondió HTTP {code}") from e

            # BioTime usa 'data' en unas versiones y 'results' en otras
            lote = data.get("data")
            if lote is None:
                lote = data.get("results", [])
            if total is None:
                total = data.get("count")

            filas.extend(lote)
            if etiqueta and total:
                print(f"\r  ·  {etiqueta}: {len(filas):,}/{total:,}", end="", flush=True)

            siguiente = data.get("next")
            if not siguiente or not lote:
                break
            params["page"] += 1
            time.sleep(0.03)   # respiro para no saturar el servidor

        if etiqueta:
            print(f"\r  ✓  {etiqueta}: {len(filas):,} registros descargados" + " " * 15)
        return filas

    def probar(self, endpoint):
        """Diagnóstico: devuelve (ok, status, muestra) sin lanzar excepción."""
        try:
            r = self.sesion.get(self.base + endpoint, params={"page_size": 1},
                                timeout=self.timeout, verify=self.verify)
            if r.status_code == 200:
                j = r.json()
                lote = j.get("data") or j.get("results") or []
                muestra = lote[0] if lote else {}
                return True, 200, muestra
            return False, r.status_code, {}
        except Exception as e:
            return False, str(e), {}

    def listar_rutas(self, modulo_root):
        """
        La API de BioTime está hecha con Django REST Framework, cuyo 'api root'
        devuelve el listado de rutas registradas del módulo como {nombre: url}.
        GET /att/api/  →  {"transactions": ".../att/api/transactions/", ...}
        Devuelve ese diccionario, o None si el módulo no expone raíz.
        """
        for suf in ("", "?format=json"):
            try:
                url = self.base + modulo_root + suf
                r = self.sesion.get(url, timeout=self.timeout, verify=self.verify)
                if r.status_code == 200:
                    j = r.json()
                    if isinstance(j, dict):
                        # descarta la envoltura estándar count/next/data
                        rutas = {k: v for k, v in j.items()
                                 if isinstance(v, str) and "://" in v}
                        if rutas:
                            return rutas
            except Exception:
                pass
        return None

    def primer_endpoint_valido(self, candidatos):
        for ep in candidatos:
            valido, status, _ = self.probar(ep)
            if valido:
                return ep
        return None


# ════════════════════════════════════════════════════════════════════════════
#  TRANSFORMACIONES  ·  JSON de BioTime → DataFrame para escribir a Excel
#  Cada Excel usa los mismos nombres de columna que generar.py espera leer.
# ════════════════════════════════════════════════════════════════════════════

def _val(reg, *claves, default=""):
    """Devuelve el primer campo no vacío de una lista de posibles nombres."""
    for k in claves:
        if k in reg and reg[k] not in (None, ""):
            return reg[k]
    return default


def _flat(reg, campo, *subclaves, default=""):
    """
    Resuelve un campo que BioTime puede devolver como valor plano o como
    objeto anidado (foreign key). Ej: reg['shift'] puede ser 'TURNO 1' o
    {'id':3,'alias':'TURNO 1'}. Devuelve el primer subcampo útil.
    """
    v = reg.get(campo)
    if v in (None, ""):
        return default
    if isinstance(v, dict):
        for sk in subclaves:
            if v.get(sk) not in (None, ""):
                return v[sk]
        return default
    if isinstance(v, (list, tuple)):
        return default
    return v


def _nombre_anidado(reg, campo, subcampo, plano):
    """Extrae dept_name / position_name venga anidado o plano."""
    v = reg.get(campo)
    if isinstance(v, dict):
        return v.get(subcampo) or reg.get(plano) or ""
    return reg.get(plano) or (v if isinstance(v, str) else "") or ""


def empleados_a_df(registros):
    filas = []
    for e in registros:
        filas.append({
            "ID Empleado": str(_val(e, "emp_code", "employee_code", "id")).strip(),
            "Nombre":      _val(e, "first_name", "nickname"),
            "Apellidos":   _val(e, "last_name"),
            "Departamento": _nombre_anidado(e, "department", "dept_name", "dept_name"),
            "Cargo":        _nombre_anidado(e, "position", "position_name", "position_name"),
            "Compañía":    _val(e, "company_name", "company"),
            "Fecha Ingreso": _val(e, "hire_date", "create_time", "enroll_date"),
        })
    df = pd.DataFrame(filas)
    df = df[df["ID Empleado"].str.strip() != ""].drop_duplicates("ID Empleado")
    return df


def turnos_a_df(registros):
    """
    Catálogo de turnos. Sirve tanto para 'attshifts' (turnos) como para
    'timeintervals' (horarios base con horas de entrada/salida).
    """
    filas = []
    for t in registros:
        entrada = _val(t, "in_time", "start_time", "check_in", "on_time")
        salida  = _val(t, "out_time", "end_time", "check_out", "off_time")
        # BioTime suele traer la duración en minutos (work_time_duration)
        horas   = _val(t, "work_time_duration", "duration", "work_hours",
                       "hours", "work_day", default=None)
        try:
            if horas not in (None, "") and float(horas) > 24:
                horas = round(float(horas) / 60.0, 2)
        except (TypeError, ValueError):
            pass
        # calcular salida si solo hay entrada + duración
        if (not salida) and entrada and horas not in (None, ""):
            try:
                hh, mm = (int(x) for x in str(entrada).split(":")[:2])
                total  = hh * 60 + mm + int(float(horas) * 60)
                salida = f"{(total // 60) % 24:02d}:{total % 60:02d}"
            except Exception:
                pass
        filas.append({
            "Código":     str(_val(t, "shift_code", "alias", "code", "id")).strip(),
            "Descripción": _val(t, "alias", "name", "shift_name", "description"),
            "Entrada":    entrada,
            "Salida":     salida,
            "Horas Día":  horas if horas is not None else "",
        })
    df = pd.DataFrame(filas)
    if len(df):
        df = df[df["Código"].str.strip() != ""].drop_duplicates("Código")
    return df


def horarios_a_df(registros, mapa_emp, mapa_turnos=None):
    """
    Asignaciones de turno por empleado en formato RANGO
    (una fila por asignación: ID, turno, fecha inicial, fecha final).
    generar.py detecta este formato automáticamente y expande día por día.

    Robusto a los FK anidados que devuelve BioTime: 'employee' y 'shift'
    pueden venir como id, como emp_code, o como objeto {id, emp_code, alias}.
    """
    mapa_turnos = mapa_turnos or {}
    filas = []
    for h in registros:
        # --- empleado ---
        emp_code = _flat(h, "employee", "emp_code", "id")
        emp_code = str(_val(h, "emp_code", "employee_code", default=emp_code)).strip()
        # si vino el id interno, tradúcelo a emp_code con el mapa
        if emp_code in mapa_emp:
            emp_code = mapa_emp[emp_code]
        if not emp_code or emp_code in ("None", ""):
            continue

        # --- turno ---
        raw_shift = h.get("shift")
        shift_id_str = str(raw_shift).strip() if raw_shift is not None else ""
        if shift_id_str in mapa_turnos:
            t_cod  = mapa_turnos[shift_id_str].get("codigo", shift_id_str)
            t_desc = mapa_turnos[shift_id_str].get("descripcion", "")
        elif isinstance(raw_shift, dict):
            t_cod  = str(_val(raw_shift, "shift_code", "code", "id", default=shift_id_str)).strip()
            t_desc = _val(raw_shift, "alias", "name", "shift_name", default="")
        else:
            t_desc = _val(h, "shift_name", "shift_alias",
                          default=_flat(h, "shift", "alias", "shift_name", "name"))
            t_cod  = str(_flat(h, "shift", "id", "shift_code",
                               default=_val(h, "shift_code", "shift_id"))).strip()

        # --- fechas ---
        f_ini = _val(h, "start_date", "start_time", "date", "schedule_date")
        f_fin = _val(h, "end_date", "end_time", default=f_ini)  # por día → ini=fin

        filas.append({
            "ID Empleado":       emp_code,
            "Código Turno":      t_cod,
            "Descripción Turno": t_desc,
            "Fecha Inicial":     str(f_ini)[:10],
            "Fecha Final":       str(f_fin)[:10],
        })
    df = pd.DataFrame(filas)
    if len(df):
        df = df[df["Fecha Inicial"].str.strip() != ""]
    return df


def transacciones_a_df(registros):
    filas = []
    for t in registros:
        punch = str(_val(t, "punch_time", "att_time", "checktime"))
        fecha, hora = "", ""
        if punch:
            partes = punch.replace("T", " ").split(" ")
            fecha = partes[0]
            hora  = partes[1][:8] if len(partes) > 1 else ""
        filas.append({
            "ID Empleado":    str(_val(t, "emp_code", "employee_code")).strip(),
            "Fecha":          fecha,
            "Hora":           hora,
            "Tipo Marcación": _val(t, "punch_state_display", "punch_state", "state"),
            "Verificación":   _val(t, "verify_type_display", "verify_type", "verify_mode"),
            "Dispositivo":    _val(t, "terminal_alias", "terminal_sn", "device_alias", "sn"),
        })
    df = pd.DataFrame(filas)
    if len(df):
        df = df[df["ID Empleado"].str.strip() != ""]
    return df


# ════════════════════════════════════════════════════════════════════════════
#  FLUJO PRINCIPAL  ·  descarga y escribe los 4 Excel
# ════════════════════════════════════════════════════════════════════════════

def exportar_a_informacion(desde, hasta, carpeta,
                           base_url=BASE_URL, usuario=None, clave=None):
    """
    Descarga desde BioTime y escribe los 4 .xlsx en `carpeta`.

    desde, hasta : "YYYY-MM"  (ej. "2026-02", "2026-05")
    carpeta      : ruta (str o Path) donde se guardan los .xlsx
    """
    import os
    usuario = usuario or USUARIO or os.environ.get("BIOTIME_USER") or ""
    clave   = clave   or CLAVE   or os.environ.get("BIOTIME_PASS") or ""

    if not usuario:
        usuario = input("  Usuario BioTime: ").strip()
    if not clave:
        import getpass
        clave = getpass.getpass("  Clave BioTime:   ")

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)

    d_ini, d_fin = _rango_de_meses(desde, hasta)
    ini_str = f"{d_ini} 00:00:00"
    fin_str = f"{d_fin} 23:59:59"

    sep(f"DESCARGANDO DE BIOTIME  ·  {desde} → {hasta}")

    cli = BioTimeClient(base_url=base_url, usuario=usuario, clave=clave).login()

    # ── 1. Empleados (sin rango) ────────────────────────────────────────────
    info("Empleados (todos)...")
    emp_raw = cli.get_todo(EP_EMPLEADOS, etiqueta="Empleados")
    df_emp  = empleados_a_df(emp_raw)
    df_emp.to_excel(carpeta / "Empleado.xlsx", index=False)
    ok(f"Empleado.xlsx  ·  {len(df_emp):,} empleados")

    # id interno → emp_code (por si horarios referencian el id interno)
    mapa_emp = {}
    for e in emp_raw:
        mapa_emp[str(e.get("id"))] = str(_val(e, "emp_code", "employee_code", "id"))

    # ── 2. Turnos (catálogo) ────────────────────────────────────────────────
    mapa_turnos = {}
    ep_turnos = cli.primer_endpoint_valido(EP_TURNOS_CANDIDATOS)
    if ep_turnos:
        info(f"Turnos (catálogo) desde {ep_turnos}...")
        try:
            tur_raw = cli.get_todo(ep_turnos, etiqueta="Turnos")

            # Enriquecer turnos con horarios base (entrada/salida/horas) si existen shift_details y timeintervals
            try:
                val_ti, _, _ = cli.probar(EP_TIMEINTERVALS)
                val_sd, _, _ = cli.probar(EP_SHIFT_DETAILS)
                if val_ti and val_sd:
                    intervals = {ti["id"]: ti for ti in cli.get_todo(EP_TIMEINTERVALS)}
                    details   = cli.get_todo(EP_SHIFT_DETAILS)
                    shift_hours = {}
                    for sd in details:
                        sid = sd.get("shift")
                        if sid not in shift_hours:
                            ti = intervals.get(sd.get("time_interval"), {})
                            shift_hours[sid] = {
                                "in_time": ti.get("in_time") or sd.get("in_time"),
                                "out_time": ti.get("out_time") or sd.get("out_time"),
                                "duration": ti.get("duration") or ti.get("work_time_duration"),
                            }
                    for s in tur_raw:
                        hrs = shift_hours.get(s.get("id"), {})
                        if not s.get("in_time") and hrs.get("in_time"):
                            s["in_time"] = hrs["in_time"]
                        if not s.get("out_time") and hrs.get("out_time"):
                            s["out_time"] = hrs["out_time"]
                        dur = hrs.get("duration")
                        if not s.get("work_time_duration") and dur:
                            s["work_time_duration"] = dur
            except Exception as e_enr:
                info(f"Aviso al enriquecer horarios de turnos: {e_enr}")

            for t in tur_raw:
                s_id = str(t.get("id"))
                s_code = str(_val(t, "shift_code", "alias", "code", "id")).strip()
                s_desc = _val(t, "alias", "name", "shift_name", "description")
                mapa_turnos[s_id] = {"codigo": s_code, "descripcion": s_desc}

            df_tur  = turnos_a_df(tur_raw)
            df_tur.to_excel(carpeta / "Turnos.xlsx", index=False)
            ok(f"Turnos.xlsx  ·  {len(df_tur):,} turnos")
        except Exception as e:
            warn(f"No pude descargar el catálogo de turnos: {e}")
            warn("Se continúa sin catálogo (el dashboard igual se genera).")
    else:
        warn("No encontré el endpoint de turnos en este servidor.")
        warn("Corre  python biotime_api.py --descubrir  para ubicarlo.")

    # ── 3. Horarios (asignaciones turno→empleado) ──────────────────────────
    #  No se filtra por fecha: una asignación pudo empezar antes del período
    #  y seguir vigente. generar.py recorta al rango al expandir día por día.
    ep_hor = cli.primer_endpoint_valido(EP_HORARIOS_CANDIDATOS)
    if ep_hor:
        info(f"Horarios asignados desde {ep_hor}...")
        try:
            hor_raw = cli.get_todo(ep_hor, etiqueta="Horarios")
            df_hor = horarios_a_df(hor_raw, mapa_emp, mapa_turnos)
            df_hor.to_excel(carpeta / "Horarios.xlsx", index=False)
            ok(f"Horarios.xlsx  ·  {len(df_hor):,} asignaciones")
        except Exception as e:
            warn(f"No pude descargar horarios: {e}")
            warn("La cobertura de turnos quedará en 0% (lo demás se calcula igual).")
            _excel_vacio_horarios(carpeta)
    else:
        warn("No encontré el endpoint de horarios en este servidor.")
        warn("Corre  python biotime_api.py --descubrir  para ubicarlo.")
        _excel_vacio_horarios(carpeta)

    # ── 4. Transacciones (rango) ────────────────────────────────────────────
    info(f"Transacciones (marcaciones)  ({d_ini} → {d_fin})...")
    trx_raw = cli.get_todo(
        EP_TRANSACC,
        params={"start_time": ini_str, "end_time": fin_str},
        etiqueta="Transacciones")
    df_trx = transacciones_a_df(trx_raw)
    df_trx.to_excel(carpeta / "Transacciones.xlsx", index=False)
    ok(f"Transacciones.xlsx  ·  {len(df_trx):,} marcaciones")

    print()
    ok("Descarga completa. Archivos listos en: " + str(carpeta))
    return carpeta


def _excel_vacio_horarios(carpeta):
    """Crea un Horarios.xlsx con la estructura correcta pero sin filas."""
    pd.DataFrame(columns=["ID Empleado", "Código Turno", "Descripción Turno",
                          "Fecha Inicial", "Fecha Final"]
                 ).to_excel(Path(carpeta) / "Horarios.xlsx", index=False)


# ════════════════════════════════════════════════════════════════════════════
#  DIAGNÓSTICO  ·  python biotime_api.py --descubrir
# ════════════════════════════════════════════════════════════════════════════

def descubrir(base_url=BASE_URL, usuario=None, clave=None):
    import os, json
    usuario = usuario or USUARIO or os.environ.get("BIOTIME_USER") or input("  Usuario BioTime: ").strip()
    if not (clave or CLAVE or os.environ.get("BIOTIME_PASS")):
        import getpass
        clave = getpass.getpass("  Clave BioTime:   ")
    clave = clave or CLAVE or os.environ.get("BIOTIME_PASS")

    sep("DIAGNÓSTICO DE ENDPOINTS")
    cli = BioTimeClient(base_url=base_url, usuario=usuario, clave=clave).login()

    candidatos = {
        "Empleados":     [EP_EMPLEADOS],
        "Departamentos": [EP_DEPARTAMENTOS],
        "Transacciones": [EP_TRANSACC],
        "Turnos":        EP_TURNOS_CANDIDATOS,
        "Horarios":      EP_HORARIOS_CANDIDATOS,
    }

    for grupo, eps in candidatos.items():
        print(f"\n  {grupo}")
        for ep in eps:
            valido, status, muestra = cli.probar(ep)
            if valido:
                campos = ", ".join(list(muestra.keys())[:12]) if muestra else "(sin registros de muestra)"
                ok(f"{ep}  →  HTTP 200")
                info(f"    campos: {campos}")
            else:
                err(f"{ep}  →  {status}")

    # ── Enumerar TODAS las rutas registradas por módulo ─────────────────────
    sep("RUTAS DISPONIBLES POR MÓDULO  (según el propio servidor)")
    print("  Esto muestra los nombres REALES de cada endpoint en tu BioTime.\n")
    for modulo in ("/att/api/", "/personnel/api/", "/iclock/api/",
                   "/base/api/", "/api/"):
        rutas = cli.listar_rutas(modulo)
        if rutas:
            print(f"  {modulo}")
            for nombre, url in sorted(rutas.items()):
                # imprime la ruta relativa, que es lo que va en CONFIGURACIÓN
                rel = url.split(cli.base, 1)[-1] if cli.base in url else url
                print(f"      {nombre:<22} {rel}")
            print()
        else:
            info(f"{modulo}  → sin índice navegable (normal en algunos módulos)")

    print("\n  Busca arriba, en el módulo /att/api/, las rutas de turnos y")
    print("  horarios (p.ej. 'shift', 'schedule', 'empSchedule', 'timeCard').")
    print("  Pásame esa lista y fijo los endpoints exactos.\n")


def muestra_att(base_url=BASE_URL, usuario=None, clave=None):
    """
    Descarga UN registro de cada endpoint de asistencia y lo imprime completo,
    para confirmar los nombres exactos de los campos (turno, empleado, fechas).
    """
    import os, json, getpass
    usuario = usuario or USUARIO or os.environ.get("BIOTIME_USER") or input("  Usuario BioTime: ").strip()
    clave   = clave or CLAVE or os.environ.get("BIOTIME_PASS") or getpass.getpass("  Clave BioTime:   ")

    sep("MUESTRA DE REGISTROS  ·  módulo asistencia")
    cli = BioTimeClient(base_url=base_url, usuario=usuario, clave=clave).login()

    endpoints = [
        "/att/api/attshifts/",
        "/att/api/timeintervals/",
        "/att/api/shift_details/",
        "/att/api/attschedules/",
        "/att/api/tempschedules/",
    ]
    for ep in endpoints:
        print(f"\n  ── {ep} " + "─" * (55 - len(ep)))
        try:
            r = cli.sesion.get(cli.base + ep, params={"page_size": 1},
                               timeout=cli.timeout, verify=cli.verify)
            if r.status_code != 200:
                err(f"HTTP {r.status_code}")
                continue
            j = r.json()
            total = j.get("count")
            lote  = j.get("data") or j.get("results") or []
            print(f"     total de registros: {total}")
            if lote:
                print(json.dumps(lote[0], indent=2, ensure_ascii=False, default=str))
            else:
                print("     (sin registros)")
        except Exception as e:
            err(str(e))

    print("\n  Pásame este volcado y ajusto el mapeo de campos exacto.\n")


# ════════════════════════════════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════════════════════════════════

def _parse_args(argv):
    args = {"desde": None, "hasta": None, "descubrir": False,
            "muestra": False, "carpeta": "informacion"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--desde", "-d"):     args["desde"]  = argv[i + 1]; i += 2
        elif a in ("--hasta", "-h"):   args["hasta"]  = argv[i + 1]; i += 2
        elif a == "--carpeta":         args["carpeta"] = argv[i + 1]; i += 2
        elif a == "--descubrir":       args["descubrir"] = True; i += 1
        elif a == "--muestra":         args["muestra"] = True; i += 1
        else: i += 1
    return args


def main():
    if not validar_configuracion():
        sys.exit(1)

    a = _parse_args(sys.argv[1:])

    if a["descubrir"]:
        descubrir()
        return

    if a["muestra"]:
        muestra_att()
        return

    desde = a["desde"] or input("  Período DESDE (YYYY-MM): ").strip()
    hasta = a["hasta"] or input("  Período HASTA (YYYY-MM): ").strip() or desde

    exportar_a_informacion(desde, hasta, a["carpeta"])


if __name__ == "__main__":
    main()
