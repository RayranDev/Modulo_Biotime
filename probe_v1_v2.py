"""
PROBE V1/V2 · Solo lectura. No escribe nada en BioTime.
Responde las preguntas 42-48 del levantamiento.

Uso:   python probe_v1_v2.py 2026-08-01 2026-08-07 <emp_code_rotativo>
Salida: probe_resultado.txt  (revisar y compartir; NO contiene credenciales)
"""
import sys, json, io
from datetime import datetime
import config as C
from biotime_api import BioTimeClient

out = io.StringIO()
def w(*a):
    s = " ".join(str(x) for x in a)
    print(s); out.write(s + "\n")

desde = sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"
hasta = sys.argv[2] if len(sys.argv) > 2 else "2026-08-07"
emp   = sys.argv[3] if len(sys.argv) > 3 else None

cli = BioTimeClient().login()

def head(t): w("\n" + "="*70 + f"\n  {t}\n" + "="*70)

# ---------- V1 : esquema crudo de transactions ----------
head("V1 · TRANSACTIONS · registro crudo completo")
r = cli._get_pagina(C.EP_TRANSACC, {"page_size": 1})
data = r.json() if hasattr(r, "json") else r
rows = data.get("data") or data.get("results") or []
if rows:
    w(json.dumps(rows[0], indent=2, ensure_ascii=False, default=str))
    k = list(rows[0].keys())
    w("\nCAMPOS:", k)
    w("\n>> id unico?      ", [x for x in k if x in ("id","pk","uuid","trans_id")] or "NO SE VE")
    w(">> hora subida?   ", [x for x in k if "upload" in x.lower() or "create" in x.lower()
                             or "sync" in x.lower() or "insert" in x.lower()] or "NO SE VE")
    w(">> hora marcacion?", [x for x in k if "punch" in x.lower() or "att_time" in x.lower()
                             or "check" in x.lower()])
else:
    w("sin datos:", json.dumps(data, ensure_ascii=False)[:600])

# ---------- V1b : filtros aceptados ----------
head("V1b · FILTROS aceptados por transactions")
for params in (
    {"start_time": f"{desde} 00:00:00", "end_time": f"{hasta} 23:59:59", "page_size": 1},
    {"punch_time__gte": f"{desde} 00:00:00", "page_size": 1},
    {"emp_code": emp or "", "page_size": 1},
    {"terminal_sn": "", "page_size": 1},
):
    try:
        rr = cli._get_pagina(C.EP_TRANSACC, {k: v for k, v in params.items() if v != ""})
        d = rr.json() if hasattr(rr, "json") else rr
        n = d.get("count", "?")
        w(f"  OK   {list(params)[:-1]} -> count={n}")
    except Exception as e:
        w(f"  FALLA {list(params)[:-1]} -> {type(e).__name__}: {str(e)[:120]}")

# ---------- V2 : cadena de programacion ----------
head("V2 · CADENA attschedules -> attshifts -> shift_details -> timeintervals")
for name, ep in (("attschedules", C.EP_ATTSCHEDULES),
                 ("attshifts",    C.EP_ATTSHIFTS),
                 ("shift_details",C.EP_SHIFT_DETAILS),
                 ("timeintervals",C.EP_TIMEINTERVALS),
                 ("tempschedules",C.EP_TEMPSCHEDULES),
                 ("breaktime",    C.EP_BREAKTIME),
                 ("leave",        C.EP_LEAVE)):
    try:
        rr = cli._get_pagina(ep, {"page_size": 1})
        d = rr.json() if hasattr(rr, "json") else rr
        rws = d.get("data") or d.get("results") or []
        w(f"\n--- {name}  (count={d.get('count','?')}) ---")
        if rws:
            w(json.dumps(rws[0], indent=2, ensure_ascii=False, default=str)[:1400])
    except Exception as e:
        w(f"\n--- {name} --- FALLA: {type(e).__name__}: {str(e)[:160]}")

# ---------- V3 : escritura permitida? (OPTIONS, no escribe) ----------
head("V3 · METODOS permitidos en /personnel/api/employees/  (OPTIONS, no escribe nada)")
try:
    import requests
    resp = requests.options(C.BASE_URL + C.EP_EMPLEADOS,
                            headers=cli.headers if hasattr(cli, "headers") else {},
                            verify=C.VERIFY_SSL, timeout=C.TIMEOUT)
    w("Allow:", resp.headers.get("Allow", "(no header)"))
    w(json.dumps(resp.json(), indent=2, ensure_ascii=False)[:700])
except Exception as e:
    w("FALLA:", type(e).__name__, str(e)[:200])

# ---------- V4 : historico y volumen ----------
head("V4 · HISTORICO y VOLUMEN")
for label, params in (("total historico", {"page_size": 1}),
                      ("rango pedido", {"start_time": f"{desde} 00:00:00",
                                        "end_time": f"{hasta} 23:59:59", "page_size": 1})):
    try:
        rr = cli._get_pagina(C.EP_TRANSACC, params)
        d = rr.json() if hasattr(rr, "json") else rr
        w(f"  {label}: count={d.get('count','?')}")
    except Exception as e:
        w(f"  {label}: FALLA {str(e)[:120]}")

with open("probe_resultado.txt", "w", encoding="utf-8") as f:
    f.write(out.getvalue())
w("\n\nGuardado en probe_resultado.txt")
