"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SERVIDOR WEB DE ASISTENCIA Y EXPLORACIÓN · BIOTIME API                      ║
║  - Consulta de Endpoints & Exportación a Excel                               ║
║  - Malla de Asistencia Matricial (Turno vs. Marcaciones con Reglas de Color) ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import io
import sys
import base64
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image

import pandas as pd
import requests
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from biotime_api import BioTimeClient, _val, _flat
from config import (
    BASE_URL,
    USUARIO,
    CLAVE,
    TIMEOUT,
    PAGE_SIZE,
    VERIFY_SSL,
    EP_TOKEN,
    EP_EMPLEADOS,
    EP_EMPLEADO_ADD,
    EP_EMPLEADO_EDIT,
    EP_DEPARTAMENTOS,
    EP_CARGOS,
    EP_AREAS,
    EP_EMPRESAS,
    EP_COMPANIAS,
    EP_CENTROS_COSTOS,
    EP_TRANSACC,
    EP_TIMEINTERVALS,
    EP_SHIFT_DETAILS,
    EP_ATTSHIFTS,
    EP_ATTSCHEDULES,
    EP_TEMPSCHEDULES,
    EP_LEAVE,
    EP_BREAKTIME,
    EP_TERMINALS,
    EP_TURNOS_CANDIDATOS,
    EP_HORARIOS_CANDIDATOS,
    EP_CALCULATION,
    EP_SETTLEMENT_CALC,
    EP_DAILY_HOURS,
    EP_FIRST_LAST_REPORT,
    EP_DAILY_ATT_REPORT,
    EP_LATE_REPORT,
    EP_ABSENT_REPORT,
    EP_PAYROLL_CONCEPTS,
    validar_configuracion,
)

# Inicialización de FastAPI
app = FastAPI(title="BioTime Manager & Explorer", version="2.0.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Cache de cliente y catalogos
_client_instance: Optional[BioTimeClient] = None
_cache_turnos: Optional[Dict[str, Any]] = None
_cache_deptos: Optional[List[Dict[str, Any]]] = None
_cache_emps_raw: Optional[List[Dict[str, Any]]] = None
_cache_schedules_raw: Optional[List[Dict[str, Any]]] = None
_cache_positions: Optional[List[Dict[str, Any]]] = None
_cache_areas: Optional[List[Dict[str, Any]]] = None
_cache_companies: Optional[List[Dict[str, Any]]] = None
_cache_subcompanies: Optional[List[Dict[str, Any]]] = None
_cache_costcenters: Optional[List[Dict[str, Any]]] = None


def get_client() -> BioTimeClient:
    """Obtiene o reutiliza la sesión autenticada con BioTime."""
    global _client_instance
    if not validar_configuracion():
        raise HTTPException(
            status_code=500,
            detail="Falta configurar variables en el archivo .env (BIOTIME_BASE_URL, BIOTIME_USER, BIOTIME_PASS)"
        )
    if _client_instance is None or not _client_instance.token:
        try:
            cli = BioTimeClient(
                base_url=BASE_URL,
                usuario=USUARIO,
                clave=CLAVE,
                timeout=TIMEOUT,
                verify_ssl=VERIFY_SSL,
            )
            cli.login()
            _client_instance = cli
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"No se pudo conectar a BioTime: {str(e)}")
    return _client_instance


def _flatten_record(record: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Aplana diccionarios anidados para que encajen limpiamente en columnas de tabla."""
    flat: Dict[str, Any] = {}
    for k, v in record.items():
        col_name = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten_record(v, col_name))
        elif isinstance(v, list):
            flat[col_name] = ", ".join(str(x) for x in v) if v else ""
        else:
            flat[col_name] = "" if v is None else v
    return flat


def _get_turnos_enriquecidos(cli: BioTimeClient) -> Dict[str, Dict[str, Any]]:
    """Descarga y construye el catálogo de turnos con horas de entrada/salida calculadas por día de la semana."""
    global _cache_turnos
    if _cache_turnos is not None:
        return _cache_turnos

    turnos_map: Dict[str, Dict[str, Any]] = {}
    ep_turnos = cli.primer_endpoint_valido(EP_TURNOS_CANDIDATOS) or "/att/api/attshifts/"
    try:
        raw_shifts = cli.get_todo(ep_turnos)
        intervals = {ti["id"]: ti for ti in cli.get_todo(EP_TIMEINTERVALS or "/att/api/timeintervals/")}
        details = cli.get_todo(EP_SHIFT_DETAILS or "/att/api/shift_details/")

        for s in raw_shifts:
            sid_int = s.get("id")
            sid = str(sid_int)
            s_sds = [sd for sd in details if sd.get("shift") == sid_int]
            s_code = str(_val(s, "shift_code", "alias", "code", "id")).strip()
            s_name = str(_val(s, "alias", "name", "shift_name", "description")).strip()

            ti_list = []
            for sd in s_sds:
                ti = intervals.get(sd.get("time_interval"))
                if ti and ti not in ti_list:
                    ti_list.append(ti)

            # Mapeo específico por día de semana (0=Lunes, 1=Martes, ..., 6=Domingo)
            week_map: Dict[int, Dict[str, Any]] = {}
            if sid_int == 45:  # T_ADM1: Lun-Jue 07:30-17:00, Vie 07:30-16:30
                for w in range(5):
                    if w == 4:
                        week_map[w] = {"in_time": "07:30:00", "out_time": "16:30:00", "cross_day": 0, "duration": 9.0}
                    else:
                        week_map[w] = {"in_time": "07:30:00", "out_time": "17:00:00", "cross_day": 0, "duration": 9.5}
            elif sid_int == 46:  # T_NORMAL1: Lun-Jue 06:00-14:00, Vie 06:00-13:00, Sab 06:00-12:00
                for w in range(6):
                    if w == 4:
                        week_map[w] = {"in_time": "06:00:00", "out_time": "13:00:00", "cross_day": 0, "duration": 7.0}
                    elif w == 5:
                        week_map[w] = {"in_time": "06:00:00", "out_time": "12:00:00", "cross_day": 0, "duration": 6.0}
                    else:
                        week_map[w] = {"in_time": "06:00:00", "out_time": "14:00:00", "cross_day": 0, "duration": 8.0}
            elif sid_int == 47:  # T_NORMAL2: Lun-Jue 14:00-22:00, Vie 13:00-21:30
                for w in range(5):
                    if w == 4:
                        week_map[w] = {"in_time": "13:00:00", "out_time": "21:30:00", "cross_day": 0, "duration": 8.5}
                    else:
                        week_map[w] = {"in_time": "14:00:00", "out_time": "22:00:00", "cross_day": 0, "duration": 8.0}
            elif sid_int == 48:  # T_NORMAL3: Lun-Jue 22:00-06:00, Vie 21:30-06:00
                for w in range(5):
                    if w == 4:
                        week_map[w] = {"in_time": "21:30:00", "out_time": "06:00:00", "cross_day": 1, "duration": 8.5}
                    else:
                        week_map[w] = {"in_time": "22:00:00", "out_time": "06:00:00", "cross_day": 1, "duration": 8.0}
            elif ti_list:
                ti = ti_list[0]
                in_t = str(ti.get("in_time") or "08:00:00")[:8]
                out_t = str(ti.get("out_time") or "17:00:00")[:8]
                cross = 1 if (ti.get("cross_day") == 1 or out_t < in_t) else 0
                dur = float(ti.get("duration") or 480) / 60.0
                for w in range(7):
                    week_map[w] = {"in_time": in_t, "out_time": out_t, "cross_day": cross, "duration": dur}
            else:
                for w in range(7):
                    week_map[w] = {"in_time": "08:00:00", "out_time": "17:00:00", "cross_day": 0, "duration": 8.0}

            rep_in = week_map.get(0, {}).get("in_time", "08:00:00")
            rep_out = week_map.get(0, {}).get("out_time", "17:00:00")
            rep_cross = week_map.get(0, {}).get("cross_day", 0)

            turnos_map[sid] = {
                "id": sid,
                "code": s_code,
                "name": s_name,
                "in_time": rep_in[:8],
                "out_time": rep_out[:8],
                "cross_day": rep_cross,
                "duration": week_map.get(0, {}).get("duration", 8.0),
                "week_map": week_map,
            }
        _cache_turnos = turnos_map
    except Exception as e:
        print(f"Error cargando catálogo de turnos: {e}")
        _cache_turnos = {}
    return _cache_turnos


# ─────────────────────────────────────────────────────────────────────────────
#  ENDPOINTS DE LA API REST
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    """Estado de conexión e información de servidor."""
    return {
        "configured": validar_configuracion(),
        "base_url": BASE_URL,
        "usuario": USUARIO,
    }


@app.get("/api/endpoints")
def list_endpoints():
    """Catálogo clasificado de endpoints para exploración."""
    catalogo = [
        {"categoria": "Personal", "nombre": "Empleados", "endpoint": EP_EMPLEADOS},
        {"categoria": "Personal", "nombre": "Departamentos", "endpoint": EP_DEPARTAMENTOS},
        {"categoria": "Personal", "nombre": "Cargos / Posiciones", "endpoint": EP_CARGOS},
        {"categoria": "Personal", "nombre": "Áreas", "endpoint": EP_AREAS},
        {"categoria": "Personal", "nombre": "Empresas", "endpoint": EP_EMPRESAS},
        {"categoria": "Personal", "nombre": "Compañías / Ramas", "endpoint": EP_COMPANIAS},
        {"categoria": "Personal", "nombre": "Centros de Costos", "endpoint": EP_CENTROS_COSTOS},
        {"categoria": "Asistencia", "nombre": "Transacciones (Marcaciones)", "endpoint": EP_TRANSACC},
        {"categoria": "Asistencia", "nombre": "Turnos (attshifts)", "endpoint": EP_ATTSHIFTS},
        {"categoria": "Asistencia", "nombre": "Horarios Base (timeintervals)", "endpoint": EP_TIMEINTERVALS},
        {"categoria": "Asistencia", "nombre": "Detalle de Turnos (shift_details)", "endpoint": EP_SHIFT_DETAILS},
        {"categoria": "Asistencia", "nombre": "Horarios Asignados (attschedules)", "endpoint": EP_ATTSCHEDULES},
        {"categoria": "Asistencia", "nombre": "Horarios Temporales (tempschedules)", "endpoint": EP_TEMPSCHEDULES},
        {"categoria": "Dispositivos", "nombre": "Terminales / Relojes", "endpoint": EP_TERMINALS},
        {"categoria": "Dispositivos", "nombre": "Estado de Dispositivos", "endpoint": EP_DEVICE_STATUS},
    ]
    return {"endpoints": catalogo}


@app.get("/api/departments")
def list_departments():
    """Obtiene la lista de departamentos para filtros dinámicos."""
    global _cache_deptos
    cli = get_client()
    if _cache_deptos is None:
        try:
            raw = cli.get_todo(EP_DEPARTAMENTOS)
            deptos = []
            for d in raw:
                deptos.append({
                    "id": str(d.get("id")),
                    "code": str(_val(d, "dept_code", "code", "id")).strip(),
                    "name": str(_val(d, "dept_name", "name", default="Sin Nombre")).strip(),
                })
            _cache_deptos = sorted(deptos, key=lambda x: x["name"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error cargando departamentos: {e}")
    return {"departments": _cache_deptos}


@app.get("/api/employees")
def list_employees(department_id: Optional[str] = Query(None)):
    """Obtiene empleados con filtro opcional por departamento."""
    global _cache_emps_raw
    cli = get_client()
    try:
        if _cache_emps_raw is None:
            _cache_emps_raw = cli.get_todo(EP_EMPLEADOS)
        raw = _cache_emps_raw
        empleados = []
        for e in raw:
            dept_obj = e.get("department") or {}
            dept_id = str(dept_obj.get("id") if isinstance(dept_obj, dict) else dept_obj or "")
            dept_name = dept_obj.get("dept_name") if isinstance(dept_obj, dict) else str(dept_obj)
            
            pos_obj = e.get("position") or {}
            pos_name = pos_obj.get("position_name") if isinstance(pos_obj, dict) else str(pos_obj)

            emp_code = str(_val(e, "emp_code", "employee_code", "id")).strip()
            nombre = str(_val(e, "first_name", "nickname", default="")).strip()
            apellido = str(_val(e, "last_name", default="")).strip()
            nombre_completo = f"{nombre} {apellido}".strip() or f"Empleado {emp_code}"

            if department_id and department_id not in ("", "all") and dept_id != department_id:
                continue

            empleados.append({
                "id": str(e.get("id")),
                "emp_code": emp_code,
                "name": nombre_completo,
                "department_id": dept_id,
                "department_name": dept_name or "Sin Departamento",
                "position_name": pos_name or "Sin Cargo",
            })

        empleados = sorted(empleados, key=lambda x: x["name"])
        return {"employees": empleados}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error cargando empleados: {e}")


@app.get("/api/positions")
def list_positions():
    """Obtiene catálogo de cargos/posiciones existentes."""
    global _cache_positions
    cli = get_client()
    if _cache_positions is None:
        try:
            raw = cli.get_todo(EP_CARGOS)
            cargos = []
            for p in raw:
                cargos.append({
                    "id": p.get("id"),
                    "code": str(_val(p, "position_code", "code", "id", default="")).strip(),
                    "name": str(_val(p, "position_name", "name", default="Sin Cargo")).strip(),
                })
            _cache_positions = sorted(cargos, key=lambda x: x["name"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error cargando cargos: {e}")
    return {"positions": _cache_positions}


@app.get("/api/areas")
def list_areas():
    """Obtiene catálogo de áreas de marcación existentes."""
    global _cache_areas
    cli = get_client()
    if _cache_areas is None:
        try:
            raw = cli.get_todo(EP_AREAS)
            areas = []
            for a in raw:
                areas.append({
                    "id": a.get("id"),
                    "code": str(_val(a, "area_code", "code", "id", default="")).strip(),
                    "name": str(_val(a, "area_name", "name", default="Sin Nombre")).strip(),
                })
            _cache_areas = sorted(areas, key=lambda x: x["name"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error cargando áreas: {e}")
    return {"areas": _cache_areas}


@app.get("/api/companies")
def list_companies():
    """Obtiene empresas registradas."""
    global _cache_companies
    cli = get_client()
    if _cache_companies is None:
        try:
            res = cli.sesion.get(cli.base + EP_EMPRESAS, params={"page_size": 100}, timeout=cli.timeout, verify=cli.verify)
            cos = []
            if res.status_code == 200:
                data = res.json()
                raw = data.get("data") or data.get("results") or []
                for c in raw:
                    cos.append({
                        "id": c.get("id"),
                        "code": str(_val(c, "co_code", "code", default="")).strip(),
                        "name": str(_val(c, "co_name", "name", default="Empresa")).strip(),
                    })
            _cache_companies = cos or [{"id": 1, "code": "01", "name": "PLASTITEC"}]
        except Exception:
            _cache_companies = [{"id": 1, "code": "01", "name": "PLASTITEC"}]
    return {"companies": _cache_companies}


@app.get("/api/subcompanies")
def list_subcompanies():
    """Obtiene catálogo de compañías/branches dependientes de la empresa (PLASTITECSA, GRANSERVICIOS)."""
    global _cache_subcompanies
    if _cache_subcompanies is not None:
        return {"subcompanies": _cache_subcompanies}
    cli = get_client()
    try:
        r = cli.sesion.get(cli.base + EP_COMPANIAS, timeout=cli.timeout)
        if r.status_code == 200:
            tree = r.json()
            branches = []
            for node in tree:
                nid = str(node.get("id", ""))
                pid = str(node.get("pId", ""))
                if pid == "5" or nid.startswith("branch-"):
                    raw_id = nid.replace("branch-", "")
                    branches.append({
                        "id": int(raw_id) if raw_id.isdigit() else raw_id,
                        "name": str(node.get("name", "")).strip(),
                    })
            if branches:
                _cache_subcompanies = branches
                return {"subcompanies": _cache_subcompanies}
    except Exception:
        pass
    _cache_subcompanies = [
        {"id": 1, "name": "PLASTITECSA"},
        {"id": 2, "name": "GRANSERVICIOS"},
    ]
    return {"subcompanies": _cache_subcompanies}


@app.get("/api/costcenters")
def list_costcenters():
    """Obtiene catálogo de centros de costos existentes."""
    global _cache_costcenters
    cli = get_client()
    if _cache_costcenters is None:
        try:
            raw = cli.get_todo(EP_CENTROS_COSTOS)
            ccs = []
            for c in raw:
                ccs.append({
                    "id": c.get("id"),
                    "code": str(_val(c, "cost_code", "code", default="")).strip(),
                    "name": str(_val(c, "cost_name", "name", default="Sin Nombre")).strip(),
                })
            _cache_costcenters = sorted(ccs, key=lambda x: x["name"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error cargando centros de costos: {e}")
    return {"costcenters": _cache_costcenters}


class CreateEmployeeRequest(BaseModel):
    emp_code: str
    first_name: str
    last_name: str
    department_id: int
    area_ids: List[int]
    position_id: Optional[int] = None
    company_id: Optional[int] = 1
    branch_id: Optional[int] = None
    cost_center_id: Optional[int] = None
    emp_type: Optional[int] = 1
    verify_mode: Optional[int] = 15
    hire_date: Optional[str] = None
    gender: Optional[str] = "M"
    national: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    photo_b64: Optional[str] = None


@app.post("/api/employees")
def create_employee(req: CreateEmployeeRequest):
    """Crea un empleado en BioTime usando catálogos existentes y enrola foto facial si se adjunta."""
    global _cache_emps_raw
    cli = get_client()

    emp_code = req.emp_code.strip()
    first_name = req.first_name.strip()
    last_name = req.last_name.strip()
    if not emp_code or not first_name or not last_name:
        raise HTTPException(status_code=400, detail="Código de empleado, nombres y apellidos son requeridos.")

    if not req.area_ids:
        raise HTTPException(status_code=400, detail="Debe asignar al menos un área de marcación.")

    # Procesar foto/biometría si viene en el payload
    files = {}
    has_photo = False
    if req.photo_b64:
        try:
            b64_str = req.photo_b64.strip()
            if "," in b64_str:
                b64_str = b64_str.split(",", 1)[1]
            raw_bytes = base64.b64decode(b64_str)
            img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            # Redimensionar si supera 1200px para acelerar transferencia y cumplir estándares BioTime
            if max(img.size) > 1200:
                img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            out_buf = io.BytesIO()
            img.save(out_buf, format="JPEG", quality=92)
            jpeg_bytes = out_buf.getvalue()
            files = {
                "bio_photo": ("biophoto.jpg", jpeg_bytes, "image/jpeg"),
                "photo": ("avatar.jpg", jpeg_bytes, "image/jpeg"),
            }
            has_photo = True
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error al decodificar la imagen del empleado: {e}")

    payload: Dict[str, Any] = {
        "emp_code": emp_code,
        "first_name": first_name,
        "last_name": last_name,
        "department": req.department_id,
        "area": req.area_ids,
        "gender": req.gender or "M",
        "company": req.company_id or 1,
        "verify_mode": req.verify_mode if req.verify_mode is not None else 15,
        "emp_type": req.emp_type if req.emp_type is not None else 1,
    }

    if req.branch_id:
        payload["branch"] = req.branch_id
    if req.position_id:
        payload["position"] = req.position_id
    if req.cost_center_id:
        payload["cost_centers"] = req.cost_center_id
    if req.hire_date:
        payload["hire_date"] = req.hire_date
    else:
        payload["hire_date"] = date.today().strftime("%Y-%m-%d")
    if req.national:
        payload["national"] = req.national.strip()
    if req.mobile:
        payload["mobile"] = req.mobile.strip()
    if req.email:
        payload["email"] = req.email.strip()

    # 1. Intentar creación vía formulario web de BioTime (EP_EMPLEADO_ADD)
    # Este endpoint interno procesa y asocia directamente la Compañía (branch), las áreas y la Bio-Foto.
    try:
        s = requests.Session()
        r_login_page = s.get(cli.base + "/login/", timeout=cli.timeout, verify=cli.verify)
        for c in s.cookies:
            c.secure = False
        csrf_login = s.cookies.get("csrftoken")

        login_data = {
            "username": cli.usuario,
            "password": cli.clave,
            "login_type": "pwd",
            "csrfmiddlewaretoken": csrf_login,
        }
        login_headers = {
            "X-CSRFToken": csrf_login,
            "Referer": cli.base + "/login/",
            "X-Requested-With": "XMLHttpRequest",
        }
        s.post(cli.base + "/login/", data=login_data, headers=login_headers, timeout=cli.timeout, verify=cli.verify)
        for c in s.cookies:
            c.secure = False

        r_page = s.get(cli.base + EP_EMPLEADO_ADD, timeout=cli.timeout, verify=cli.verify)
        for c in s.cookies:
            c.secure = False
        csrf_form = s.cookies.get("csrftoken")

        form_items = [
            ("csrfmiddlewaretoken", csrf_form),
            ("emp_code", emp_code),
            ("first_name", first_name),
            ("last_name", last_name),
            ("company", str(req.company_id or 1)),
            ("branch", str(req.branch_id or 1)),
            ("department", str(req.department_id)),
            ("position", str(req.position_id or 1)),
            ("cost_centers", str(req.cost_center_id or 1)),
            ("emp_type", str(req.emp_type or 1)),
            ("verify_mode", str(req.verify_mode if req.verify_mode is not None else 15)),
            ("gender", req.gender or "M"),
            ("hire_date", req.hire_date or date.today().strftime("%Y-%m-%d")),
            ("enable_att", "True"),
            ("payment_mode", "1"),
            ("payment_type", "1"),
            ("emp_status", "1"),
            ("app_role", "1"),
            ("app_status", "0"),
        ]

        if req.national:
            form_items.append(("national", req.national.strip()))
        if req.mobile:
            form_items.append(("mobile", req.mobile.strip()))
        if req.email:
            form_items.append(("email", req.email.strip()))

        for aid in req.area_ids:
            form_items.append(("area", str(aid)))

        headers = {
            "X-CSRFToken": csrf_form,
            "Referer": cli.base + EP_EMPLEADO_ADD,
            "X-Requested-With": "XMLHttpRequest",
        }

        resp = s.post(
            cli.base + EP_EMPLEADO_ADD,
            data=form_items,
            files=files if files else None,
            headers=headers,
            timeout=cli.timeout,
            verify=cli.verify,
        )

        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("code") == 0:
                _cache_emps_raw = None
                extra_msg = " con biometría facial enrolada (VL Face)" if has_photo else ""
                return {
                    "success": True,
                    "message": f"Empleado {first_name} {last_name} ({emp_code}) creado con éxito en BioTime{extra_msg}.",
                    "data": res_json,
                }
            else:
                err_msg = res_json.get("msg") or str(res_json)
                raise HTTPException(status_code=400, detail=f"BioTime rechazó el alta: {err_msg}")
        elif "Guardar foto" in resp.text or "verifique la foto" in resp.text.lower():
            raise HTTPException(
                status_code=400,
                detail="BioTime rechazó la foto: No se detectó un rostro humano frontal válido o la imagen no cumple los requisitos. Tome o suba una foto frontal nítida."
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Aviso: Alta vía form web no disponible ({e}). Usando fallback REST API...")

    # Fallback: Creación estándar por REST API
    url = cli.base + EP_EMPLEADOS
    try:
        resp = cli.sesion.post(url, json=payload, timeout=cli.timeout, verify=cli.verify)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error conectando con BioTime: {e}")

    if resp.status_code in (200, 201):
        _cache_emps_raw = None
        data = resp.json() if resp.text else {}
        return {
            "success": True,
            "message": f"Empleado {first_name} {last_name} ({emp_code}) creado con éxito en BioTime.",
            "data": data,
        }
    else:
        err_msg = resp.text
        try:
            err_json = resp.json()
            err_msg = err_json.get("msg") or err_json.get("detail") or str(err_json)
        except Exception:
            pass
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"BioTime rechazó la creación: {err_msg}"
        )


@app.get("/api/query")
def query_endpoint(
    endpoint: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    fetch_all: bool = Query(False),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    """Consulta cualquier endpoint de BioTime."""
    cli = get_client()
    params: Dict[str, Any] = {"page": page, "page_size": page_size}
    if start_time: params["start_time"] = start_time
    if end_time: params["end_time"] = end_time

    try:
        if fetch_all:
            raw_records = cli.get_todo(endpoint, params=params)
            total_count = len(raw_records)
        else:
            resp = cli._get_pagina(endpoint, params)
            raw_records = resp.get("data") or resp.get("results") or []
            total_count = resp.get("count", len(raw_records))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error consultando '{endpoint}': {str(e)}")

    flat_records = [_flatten_record(r) for r in raw_records]
    columnas: List[str] = []
    if flat_records:
        col_set = set()
        for r in flat_records:
            for k in r.keys():
                if k not in col_set:
                    col_set.add(k)
                    columnas.append(k)

    return {
        "endpoint": endpoint,
        "total_count": total_count,
        "returned_count": len(flat_records),
        "page": page,
        "page_size": page_size,
        "columns": columnas,
        "rows": flat_records,
        "raw": raw_records[:20],
    }


@app.get("/api/export-excel")
def export_excel(
    endpoint: str = Query(...),
    page_size: int = Query(500, ge=1, le=1000),
    fetch_all: bool = Query(True),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    """Exporta los datos planos de cualquier endpoint a Excel."""
    cli = get_client()
    params: Dict[str, Any] = {"page_size": page_size}
    if start_time: params["start_time"] = start_time
    if end_time: params["end_time"] = end_time

    try:
        if fetch_all:
            raw_records = cli.get_todo(endpoint, params=params)
        else:
            params["page"] = 1
            resp = cli._get_pagina(endpoint, params)
            raw_records = resp.get("data") or resp.get("results") or []
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al descargar datos para Excel: {str(e)}")

    flat_records = [_flatten_record(r) for r in raw_records]
    df = pd.DataFrame(flat_records)

    output = io.BytesIO()
    clean_name = endpoint.strip("/").replace("/", "_") or "biotime_export"
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=clean_name[:31])
    output.seek(0)

    filename = f"{clean_name}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ─────────────────────────────────────────────────────────────────────────────
#  MALLA DE ASISTENCIA (MATRIZ DIARIA INTELIGENTE)
# ─────────────────────────────────────────────────────────────────────────────

def _generar_rango_fechas(fecha_inicio: date, fecha_fin: date) -> List[Dict[str, Any]]:
    """Genera lista de fechas con metadata de día y nombre para la cabecera."""
    dias_semana_es = ["Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"]
    fechas = []
    curr = fecha_inicio
    while curr <= fecha_fin:
        fechas.append({
            "iso": curr.strftime("%Y-%m-%d"),
            "day": curr.day,
            "day_str": f"{curr.day:02d}",
            "weekday": dias_semana_es[curr.weekday()],
            "is_weekend": curr.weekday() in (5, 6),
        })
        curr += timedelta(days=1)
    return fechas


def _procesar_matriz_asistencia(
    cli: BioTimeClient,
    fecha_inicio: date,
    fecha_fin: date,
    department_id: Optional[str] = None,
    employee_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Motor de cálculo de asistencia por empleado y fecha."""
    global _cache_emps_raw, _cache_schedules_raw
    # 1. Obtener empleados
    if _cache_emps_raw is None:
        _cache_emps_raw = cli.get_todo(EP_EMPLEADOS)
    raw_emps = _cache_emps_raw
    empleados_dict: Dict[str, Dict[str, Any]] = {}
    emp_internal_to_code: Dict[str, str] = {}

    for e in raw_emps:
        internal_id = str(e.get("id"))
        emp_code = str(_val(e, "emp_code", "employee_code", "id")).strip()
        emp_internal_to_code[internal_id] = emp_code

        dept_obj = e.get("department") or {}
        dept_id = str(dept_obj.get("id") if isinstance(dept_obj, dict) else dept_obj or "")
        dept_name = dept_obj.get("dept_name") if isinstance(dept_obj, dict) else str(dept_obj)

        pos_obj = e.get("position") or {}
        pos_name = pos_obj.get("position_name") if isinstance(pos_obj, dict) else str(pos_obj)

        if department_id and department_id not in ("", "all") and dept_id != department_id:
            continue
        if employee_id and employee_id not in ("", "all") and emp_code != employee_id and internal_id != employee_id:
            continue

        nombre = str(_val(e, "first_name", "nickname", default="")).strip()
        apellido = str(_val(e, "last_name", default="")).strip()
        nombre_completo = f"{nombre} {apellido}".strip() or f"Empleado {emp_code}"

        empleados_dict[emp_code] = {
            "internal_id": internal_id,
            "emp_code": emp_code,
            "name": nombre_completo,
            "department": dept_name or "Sin Departamento",
            "position": pos_name or "Sin Cargo",
            "days": {},
        }

    if not empleados_dict:
        return {
            "dates": _generar_rango_fechas(fecha_inicio, fecha_fin),
            "employees": [],
            "summary": {"total_employees": 0, "complete": 0, "incomplete": 0, "early_leave": 0, "absent": 0, "no_shift": 0, "off": 0}
        }

    # 2. Catálogo de turnos
    turnos_catalogo = _get_turnos_enriquecidos(cli)

    # 3. Asignaciones de turno (attschedules)
    if _cache_schedules_raw is None:
        ep_hor = cli.primer_endpoint_valido(EP_HORARIOS_CANDIDATOS) or "/att/api/attschedules/"
        _cache_schedules_raw = cli.get_todo(ep_hor)
    raw_schedules = _cache_schedules_raw

    # Mapear horarios: emp_code -> lista de (start_date, end_date, turno_info)
    horarios_por_empleado: Dict[str, List[Dict[str, Any]]] = {code: [] for code in empleados_dict}
    for sch in raw_schedules:
        raw_emp = str(sch.get("employee") or "")
        emp_code = emp_internal_to_code.get(raw_emp, raw_emp)
        if emp_code in horarios_por_empleado:
            f_ini_str = str(sch.get("start_date") or "")[:10]
            f_fin_str = str(sch.get("end_date") or f_ini_str)[:10]
            shift_id = str(sch.get("shift") or "")
            turno_info = turnos_catalogo.get(shift_id, {
                "id": shift_id,
                "code": f"TURNO_{shift_id}",
                "name": f"Turno {shift_id}",
                "in_time": "08:00:00",
                "out_time": "17:00:00",
                "duration": 8.0,
            })
            try:
                d_ini = datetime.strptime(f_ini_str, "%Y-%m-%d").date()
                d_fin = datetime.strptime(f_fin_str, "%Y-%m-%d").date()
                horarios_por_empleado[emp_code].append({
                    "start": d_ini,
                    "end": d_fin,
                    "turno": turno_info,
                })
            except Exception:
                pass

    # 4. Transacciones (marcaciones en el rango con buffer de +/- 1 día para cruces de medianoche)
    ini_buffer = fecha_inicio - timedelta(days=1)
    fin_buffer = fecha_fin + timedelta(days=1)
    ini_str = f"{ini_buffer.strftime('%Y-%m-%d')} 00:00:00"
    fin_str = f"{fin_buffer.strftime('%Y-%m-%d')} 23:59:59"

    # Si se filtra por empleado específico, optimizar petición
    trx_params = {"start_time": ini_str, "end_time": fin_str}
    if employee_id and employee_id not in ("", "all"):
        trx_params["emp_code"] = employee_id

    raw_trans = cli.get_todo(
        EP_TRANSACC or "/iclock/api/transactions/",
        params=trx_params
    )

    # Agrupar marcaciones por emp_code como objetos datetime
    emp_punches_map: Dict[str, List[Dict[str, Any]]] = {code: [] for code in empleados_dict}
    for trx in raw_trans:
        code = str(_val(trx, "emp_code", "employee_code")).strip()
        if code in emp_punches_map:
            punch_raw = str(_val(trx, "punch_time", "att_time", default="")).replace("T", " ")[:19]
            if punch_raw:
                try:
                    dt_obj = datetime.strptime(punch_raw, "%Y-%m-%d %H:%M:%S")
                    emp_punches_map[code].append({
                        "dt": dt_obj,
                        "datetime": punch_raw,
                        "time": dt_obj.strftime("%H:%M:%S"),
                        "date": dt_obj.strftime("%Y-%m-%d"),
                        "state": str(_val(trx, "punch_state", "state", default="0")),
                        "device": str(_val(trx, "terminal_alias", "device_alias", default="Terminal")),
                    })
                except Exception:
                    pass

    # Ordenar marcaciones cronológicamente
    for code in emp_punches_map:
        emp_punches_map[code].sort(key=lambda x: x["dt"])

    # 5. Calcular estado por cada empleado y día
    dias_rango = _generar_rango_fechas(fecha_inicio, fecha_fin)
    summary_counts = {
        "total_employees": len(empleados_dict),
        "complete": 0,
        "incomplete": 0,
        "early_leave": 0,
        "late_leave": 0,
        "absent": 0,
        "no_shift": 0,
        "off": 0,
    }

    for emp_code, emp_data in empleados_dict.items():
        all_emp_punches = emp_punches_map.get(emp_code, [])

        # Turno principal o más reciente asignado al empleado
        active_shift_info = None
        if horarios_por_empleado.get(emp_code):
            latest_sch = max(horarios_por_empleado[emp_code], key=lambda x: x["end"])
            t_obj = latest_sch["turno"]
            active_shift_info = {
                "id": t_obj.get("id"),
                "code": t_obj.get("code"),
                "name": t_obj.get("name"),
                "hours": f"{t_obj.get('in_time', '08:00')[:5]} a {t_obj.get('out_time', '17:00')[:5]}",
                "cross_day": t_obj.get("cross_day", 0),
            }
        emp_data["assigned_shift"] = active_shift_info

        curr = fecha_inicio
        while curr <= fecha_fin:
            f_str = curr.strftime("%Y-%m-%d")
            w = curr.weekday() # 0=Lun, 1=Mar, 2=Mie, 3=Jue, 4=Vie, 5=Sab, 6=Dom

            # Buscar turno asignado para esta fecha
            turno_asignado = None
            for sch in horarios_por_empleado.get(emp_code, []):
                if sch["start"] <= curr <= sch["end"]:
                    turno_asignado = sch["turno"]
                    break

            in_time: Optional[str] = None
            out_time: Optional[str] = None
            status = "LIBRE"
            status_text = "Día Libre / Descanso"
            punches_del_dia: List[Dict[str, Any]] = []

            if turno_asignado:
                week_map = turno_asignado.get("week_map", {})
                t_day = week_map.get(w) or turno_asignado
                t_in_str = str(t_day.get("in_time", "08:00:00"))[:8]
                t_out_str = str(t_day.get("out_time", "17:00:00"))[:8]
                cross_day = t_day.get("cross_day", 0)

                try:
                    in_h, in_m, in_s = [int(x) for x in t_in_str.split(":")]
                    out_h, out_m, out_s = [int(x) for x in t_out_str.split(":")]
                    dt_in_sched = datetime(curr.year, curr.month, curr.day, in_h, in_m, in_s)
                    if cross_day:
                        dt_out_sched = datetime(curr.year, curr.month, curr.day, out_h, out_m, out_s) + timedelta(days=1)
                    else:
                        dt_out_sched = datetime(curr.year, curr.month, curr.day, out_h, out_m, out_s)
                except Exception:
                    dt_in_sched = datetime(curr.year, curr.month, curr.day, 8, 0, 0)
                    dt_out_sched = datetime(curr.year, curr.month, curr.day, 17, 0, 0)

                dur_hours = max((dt_out_sched - dt_in_sched).total_seconds() / 3600.0, 1.0)

                # Definir ventanas dinámicas de entrada y salida
                win_in_start = dt_in_sched - timedelta(hours=3.5)
                win_in_end = dt_in_sched + timedelta(hours=dur_hours * 0.5)
                win_out_start = dt_in_sched + timedelta(hours=dur_hours * 0.5)
                win_out_end = dt_out_sched + timedelta(hours=4.0)

                cand_in = [p for p in all_emp_punches if win_in_start <= p["dt"] <= win_in_end]
                cand_out = [p for p in all_emp_punches if win_out_start <= p["dt"] <= win_out_end]

                p_in = min(cand_in, key=lambda x: x["dt"]) if cand_in else None
                p_out = max(cand_out, key=lambda x: x["dt"]) if cand_out else None

                punches_del_dia = [p for p in all_emp_punches if win_in_start <= p["dt"] <= win_out_end]

                if not p_in and not p_out:
                    status = "AUSENTE"
                    status_text = "Ausente (Sin Marcaciones)"
                    summary_counts["absent"] += 1
                elif p_in and not p_out:
                    in_time = p_in["time"]
                    status = "INCOMPLETO"
                    status_text = "Incompleto (Falta salida)"
                    summary_counts["incomplete"] += 1
                elif not p_in and p_out:
                    out_time = p_out["time"]
                    status = "INCOMPLETO"
                    status_text = "Incompleto (Falta entrada)"
                    summary_counts["incomplete"] += 1
                else:
                    in_time = p_in["time"]
                    out_time = p_out["time"]

                    tardanza_min = (p_in["dt"] - dt_in_sched).total_seconds() / 60.0
                    salida_anticipada_min = (dt_out_sched - p_out["dt"]).total_seconds() / 60.0
                    salida_tardia_min = (p_out["dt"] - dt_out_sched).total_seconds() / 60.0

                    if salida_anticipada_min > 15:
                        status = "SALIDA_ANTICIPADA"
                        status_text = f"Salida anticipada (-{int(salida_anticipada_min)} min)"
                        summary_counts["early_leave"] += 1
                    elif tardanza_min > 15:
                        status = "SALIDA_ANTICIPADA"
                        status_text = f"Tardanza (+{int(tardanza_min)} min)"
                        summary_counts["early_leave"] += 1
                    elif salida_tardia_min > 30:
                        status = "SALIDA_TARDIA"
                        status_text = f"Salida tardía / HE (+{int(salida_tardia_min)} min)"
                        summary_counts["late_leave"] += 1
                    else:
                        status = "COMPLETO"
                        status_text = "Completo"
                        summary_counts["complete"] += 1

            else:
                # Sin turno asignado
                day_punches = [p for p in all_emp_punches if p["date"] == f_str]
                punches_del_dia = day_punches
                if day_punches:
                    in_time = day_punches[0]["time"]
                    out_time = day_punches[-1]["time"] if len(day_punches) > 1 else None
                    status = "SIN_TURNO"
                    status_text = f"Con marcaciones pero sin turno ({len(day_punches)} marcaciones)"
                    summary_counts["no_shift"] += 1
                else:
                    status = "LIBRE"
                    status_text = "Día Libre / Descanso"
                    summary_counts["off"] += 1

            emp_data["days"][f_str] = {
                "date": f_str,
                "day": curr.day,
                "status": status,
                "status_text": status_text,
                "in_time": in_time,
                "out_time": out_time,
                "shift_code": turno_asignado.get("code") if turno_asignado else "",
                "shift_name": turno_asignado.get("name") if turno_asignado else "",
                "shift_in": t_in_str if turno_asignado else "",
                "shift_out": t_out_str if turno_asignado else "",
                "cross_day": cross_day if turno_asignado else 0,
                "punches_count": len(punches_del_dia),
                "punches": punches_del_dia,
            }
            curr += timedelta(days=1)

    return {
        "dates": dias_rango,
        "employees": list(empleados_dict.values()),
        "summary": summary_counts,
    }


@app.get("/api/attendance-matrix")
def get_attendance_matrix(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    department_id: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
):
    """Obtiene la cuadrícula de asistencia procesada día a día."""
    cli = get_client()
    try:
        d_ini = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        d_fin = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()
        if d_fin < d_ini:
            raise HTTPException(status_code=400, detail="La fecha final no puede ser anterior a la inicial")
        if (d_fin - d_ini).days > 62:
            raise HTTPException(status_code=400, detail="El rango máximo permitido para la cuadrícula es de 62 días (2 meses)")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD")

    resultado = _procesar_matriz_asistencia(
        cli=cli,
        fecha_inicio=d_ini,
        fecha_fin=d_fin,
        department_id=department_id,
        employee_id=employee_id,
    )
    return resultado


@app.get("/api/attendance-matrix/export-excel")
def export_attendance_matrix_excel(
    start_date: str = Query(...),
    end_date: str = Query(...),
    department_id: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
):
    """Genera y descarga un archivo Excel tipo matriz con formato condicional de colores."""
    cli = get_client()
    d_ini = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
    d_fin = datetime.strptime(end_date.strip(), "%Y-%m-%d").date()

    data = _procesar_matriz_asistencia(cli, d_ini, d_fin, department_id, employee_id)
    fechas = data["dates"]
    empleados = data["employees"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Malla de Asistencia"

    # Paleta de estilos OpenPyXL
    font_title = Font(name="Calibri", size=14, bold=True, color="1E293B")
    font_subtitle = Font(name="Calibri", size=10, italic=True, color="64748B")
    font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    fill_header = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")

    font_emp = Font(name="Calibri", size=10, bold=True, color="0F172A")
    font_meta = Font(name="Calibri", size=9, color="475569")
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center")
    border_thin = Border(
        left=Side(style="thin", color="E2E8F0"),
        right=Side(style="thin", color="E2E8F0"),
        top=Side(style="thin", color="E2E8F0"),
        bottom=Side(style="thin", color="E2E8F0"),
    )

    # Fills por estado
    fills = {
        "COMPLETO": PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid"),         # Verde suave
        "INCOMPLETO": PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid"),       # Amarillo suave
        "SALIDA_ANTICIPADA": PatternFill(start_color="FFEDD5", end_color="FFEDD5", fill_type="solid"),# Naranja suave
        "SALIDA_TARDIA": PatternFill(start_color="CFFAFE", end_color="CFFAFE", fill_type="solid"),    # Cian suave
        "AUSENTE": PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid"),          # Rojo suave
        "SIN_TURNO": PatternFill(start_color="F3E8FF", end_color="F3E8FF", fill_type="solid"),        # Morado suave
        "LIBRE": PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid"),            # Gris suave
    }
    fonts = {
        "COMPLETO": Font(name="Calibri", size=8, bold=True, color="166534"),
        "INCOMPLETO": Font(name="Calibri", size=8, bold=True, color="854D0E"),
        "SALIDA_ANTICIPADA": Font(name="Calibri", size=8, bold=True, color="9A3412"),
        "SALIDA_TARDIA": Font(name="Calibri", size=8, bold=True, color="0E7490"),
        "AUSENTE": Font(name="Calibri", size=8, bold=True, color="991B1B"),
        "SIN_TURNO": Font(name="Calibri", size=8, bold=True, color="6B21A8"),
        "LIBRE": Font(name="Calibri", size=8, color="94A3B8"),
    }

    # Encabezado del reporte
    ws["A1"] = "BIOTIME · MALLA DE ASISTENCIA Y CONTROL DE TURNOS"
    ws["A1"].font = font_title
    ws["A2"] = f"Período: {start_date} al {end_date} | Total empleados: {len(empleados)}"
    ws["A2"].font = font_subtitle

    # Fila de cabecera de tabla (Fila 4)
    headers_fijas = ["ID Empleado", "Nombre y Apellidos", "Departamento", "Cargo", "Turno Programado"]
    for col_idx, h in enumerate(headers_fijas, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = border_thin

    start_date_col = len(headers_fijas) + 1
    for i, d in enumerate(fechas):
        col_num = start_date_col + i
        cell = ws.cell(row=4, column=col_num, value=f"{d['day_str']}\n{d['weekday']}")
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = border_thin

    # Llenar datos de empleados y días
    row_idx = 5
    for emp in empleados:
        ws.cell(row=row_idx, column=1, value=emp["emp_code"]).font = font_emp
        ws.cell(row=row_idx, column=2, value=emp["name"]).font = font_emp
        ws.cell(row=row_idx, column=3, value=emp["department"]).font = font_meta
        ws.cell(row=row_idx, column=4, value=emp["position"]).font = font_meta

        # Turno asignado
        t_info = emp.get("assigned_shift") or {}
        turno_str = f"{t_info.get('name', 'Sin Turno')}\n({t_info.get('hours', '--')})" if t_info else "Sin Turno"
        ws.cell(row=row_idx, column=5, value=turno_str).font = font_meta

        for c in range(1, start_date_col):
            cell = ws.cell(row=row_idx, column=c)
            cell.alignment = align_left if c != 5 else align_center
            cell.border = border_thin

        for i, d in enumerate(fechas):
            col_num = start_date_col + i
            day_data = emp["days"].get(d["iso"], {})
            st = day_data.get("status", "LIBRE")
            in_t = day_data.get("in_time") or "--"
            out_t = day_data.get("out_time") or "--"

            val_cell = ""
            if st == "COMPLETO":
                val_cell = f"E: {in_t[:5]}\nS: {out_t[:5]}"
            elif st == "INCOMPLETO":
                val_cell = f"E: {in_t[:5] if in_t != '--' else 'FALTA'}\nS: {out_t[:5] if out_t != '--' else 'FALTA'}"
            elif st == "SALIDA_ANTICIPADA":
                val_cell = f"E: {in_t[:5]}\nS: {out_t[:5]} (ANTIC)"
            elif st == "SALIDA_TARDIA":
                val_cell = f"E: {in_t[:5]}\nS: {out_t[:5]} (TARDÍA)"
            elif st == "AUSENTE":
                val_cell = "AUSENTE"
            elif st == "SIN_TURNO":
                val_cell = f"E: {in_t[:5]}\n(S/T)"
            else:
                val_cell = "LIBRE"

            cell = ws.cell(row=row_idx, column=col_num, value=val_cell)
            cell.font = fonts.get(st, font_meta)
            cell.fill = fills.get(st, fills["LIBRE"])
            cell.alignment = align_center
            cell.border = border_thin

        row_idx += 1

    # Ajustar anchos de columnas
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 26
    for i in range(len(fechas)):
        col_letter = get_column_letter(start_date_col + i)
        ws.column_dimensions[col_letter].width = 11

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Malla_Asistencia_{start_date}_a_{end_date}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO DE REPORTES DE ASISTENCIA & EXPORTACIÓN A EXCEL
# ══════════════════════════════════════════════════════════════════════════════

def _get_biotime_web_session() -> requests.Session:
    """Inicia sesión web en BioTime capturando cookies y token CSRF para endpoints internos."""
    s = requests.Session()
    s.verify = VERIFY_SSL
    r = s.get(BASE_URL + "/login/", timeout=TIMEOUT)
    for c in s.cookies: c.secure = False
    csrf = s.cookies.get("csrftoken")
    s.post(
        BASE_URL + "/login/",
        data={
            "username": USUARIO,
            "password": CLAVE,
            "login_type": "pwd",
            "csrfmiddlewaretoken": csrf,
        },
        headers={"X-CSRFToken": csrf, "Referer": BASE_URL + "/login/"},
        timeout=TIMEOUT,
    )
    for c in s.cookies: c.secure = False
    return s


def _compute_daily_hours(punch_in_str: str, punch_out_str: str, att_date: date) -> Dict[str, float]:
    """
    Calcula desglose de horas según legislación laboral colombiana y conceptos oficiales de BioTime:
    - Diurno: 06:00 a 21:00
    - Nocturno: 21:00 a 06:00 del día siguiente
    - Límite jornada ordinaria: 8 horas
    - Horas extras si total > 8h (HED +25%, HEN +75%)
    - Recargo nocturno (pc_5, 35%) para horas nocturnas ordinarias
    - Dominicales / Festivos (pc_7, 75%) y extras dominicales (pc_3 y pc_4)
    """
    try:
        dt_in = datetime.strptime(punch_in_str, "%Y-%m-%d %H:%M:%S")
        dt_out = datetime.strptime(punch_out_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return {
            "total_time": 0.0, "dayWT": 0.0, "ntWT": 0.0,
            "dayOT": 0.0, "ntOT": 0.0, "daySundayOT": 0.0, "ntSundayOT": 0.0,
            "pc_5": 0.0, "pc_7": 0.0, "pc_8": 0.0
        }
    
    if dt_out <= dt_in:
        return {
            "total_time": 0.0, "dayWT": 0.0, "ntWT": 0.0,
            "dayOT": 0.0, "ntOT": 0.0, "daySundayOT": 0.0, "ntSundayOT": 0.0,
            "pc_5": 0.0, "pc_7": 0.0, "pc_8": 0.0
        }

    cur = dt_in
    day_mins = 0
    night_mins = 0
    
    while cur < dt_out:
        h = cur.hour
        if 6 <= h < 21:
            day_mins += 1
        else:
            night_mins += 1
        cur += timedelta(minutes=1)

    total_hours = round((day_mins + night_mins) / 60.0, 2)
    day_hours = round(day_mins / 60.0, 2)
    night_hours = round(night_mins / 60.0, 2)

    is_sunday = (att_date.weekday() == 6)
    regular_limit = 8.0
    dayWT = 0.0
    ntWT = 0.0
    dayOT = 0.0
    ntOT = 0.0
    daySundayOT = 0.0
    ntSundayOT = 0.0
    pc_5 = 0.0
    pc_7 = 0.0
    pc_8 = 0.0

    if not is_sunday:
        if total_hours <= regular_limit:
            dayWT = day_hours
            ntWT = night_hours
            pc_5 = ntWT
        else:
            rem_reg = regular_limit
            dayWT = min(rem_reg, day_hours)
            rem_reg -= dayWT
            ntWT = min(rem_reg, night_hours)
            pc_5 = ntWT
            dayOT = round(max(0.0, day_hours - dayWT), 2)
            ntOT = round(max(0.0, night_hours - ntWT), 2)
    else:
        if total_hours <= regular_limit:
            dayWT = day_hours
            ntWT = night_hours
            pc_7 = dayWT
            pc_8 = ntWT
        else:
            rem_reg = regular_limit
            dayWT = min(rem_reg, day_hours)
            rem_reg -= dayWT
            ntWT = min(rem_reg, night_hours)
            pc_7 = dayWT
            pc_8 = ntWT
            daySundayOT = round(max(0.0, day_hours - dayWT), 2)
            ntSundayOT = round(max(0.0, night_hours - ntWT), 2)

    return {
        "total_time": total_hours,
        "dayWT": dayWT,
        "ntWT": ntWT,
        "dayOT": dayOT,
        "ntOT": ntOT,
        "daySundayOT": daySundayOT,
        "ntSundayOT": ntSundayOT,
        "pc_5": pc_5,
        "pc_7": pc_7,
        "pc_8": pc_8
    }


REPORT_CATALOG = [
    {
        "id": "daily_hours",
        "name": "Reporte de Horas, Recargos y Novedades",
        "description": "Detalle diario de horas ordinarias diurnas/nocturnas, horas extras (HED, HEN, HEDF, HENF), recargos nocturnos y novedades de nómina.",
        "icon": "💼",
        "badge": "Horas & Conceptos",
        "columns": [
            {"key": "att_date", "label": "Fecha"},
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "company_name", "label": "Empresa"},
            {"key": "weekday_str", "label": "Día"},
            {"key": "timetable", "label": "Programación"},
            {"key": "check_in", "label": "Hora Entrada"},
            {"key": "check_out", "label": "Hora Salida"},
            {"key": "total_time", "label": "Total Horas"},
            {"key": "dayWT", "label": "Ord. Diurna"},
            {"key": "ntWT", "label": "Ord. Nocturna"},
            {"key": "dayOT", "label": "Extra Diurna (HED)"},
            {"key": "ntOT", "label": "Extra Nocturna (HEN)"},
            {"key": "daySundayOT", "label": "Extra Dom. Diurna"},
            {"key": "ntSundayOT", "label": "Extra Dom. Nocturna"},
            {"key": "pc_5", "label": "Recargo Nocturno"},
            {"key": "pc_7", "label": "Recargo Festivo/Dom."},
            {"key": "pc_8", "label": "Recargo Noct. Festivo"},
            {"key": "novelty", "label": "Novedad / Ausencia"},
        ]
    },
    {
        "id": "transactions",
        "name": "Marcaciones y Transacciones Crudas",
        "description": "Historial de cada registro en terminales biométricas con fecha, hora, dispositivo y método.",
        "icon": "⏱️",
        "columns": [
            {"key": "punch_time", "label": "Fecha y Hora"},
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "company_name", "label": "Empresa"},
            {"key": "terminal_alias", "label": "Terminal / Biométrico"},
            {"key": "punch_state_str", "label": "Tipo de Evento"},
            {"key": "verify_type_str", "label": "Método de Verificación"},
        ]
    },
    {
        "id": "first_last",
        "name": "Primera Entrada y Última Salida (First In / Last Out)",
        "description": "Consolidado diario: primera marcación de ingreso, última salida y tiempo total de permanencia.",
        "icon": "🚪",
        "columns": [
            {"key": "att_date", "label": "Fecha"},
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "first_punch", "label": "Primera Entrada"},
            {"key": "last_punch", "label": "Última Salida"},
            {"key": "total_punches", "label": "Total Marcaciones"},
            {"key": "time_spent", "label": "Tiempo Total (HH:MM)"},
            {"key": "hours_decimal", "label": "Horas Decimales"},
            {"key": "first_terminal", "label": "Terminal Entrada"},
            {"key": "last_terminal", "label": "Terminal Salida"},
        ]
    },
    {
        "id": "late_arrivals",
        "name": "Control de Tardanzas y Puntualidad",
        "description": "Llegadas registradas después de la hora programada con minutos exactos de retraso.",
        "icon": "⚠️",
        "columns": [
            {"key": "att_date", "label": "Fecha"},
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "scheduled_in", "label": "Hora Esperada"},
            {"key": "first_punch", "label": "Hora Llegada"},
            {"key": "delay_minutes", "label": "Retraso (Min)"},
            {"key": "severity", "label": "Nivel Tardanza"},
        ]
    },
    {
        "id": "absences",
        "name": "Ausentismos e Inasistencias",
        "description": "Días laborables sin marcaciones registradas para empleados activos.",
        "icon": "❌",
        "columns": [
            {"key": "att_date", "label": "Fecha"},
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "position_name", "label": "Cargo"},
            {"key": "status", "label": "Estado de Ausencia"},
        ]
    },
    {
        "id": "summary",
        "name": "Resumen Consolidado de Asistencia",
        "description": "Métricas consolidadas por persona: días asistidos, tardanzas, ausencias y porcentaje de cumplimiento.",
        "icon": "📊",
        "columns": [
            {"key": "emp_code", "label": "Cód. Empleado"},
            {"key": "emp_name", "label": "Empleado"},
            {"key": "dept_name", "label": "Departamento"},
            {"key": "company_name", "label": "Empresa"},
            {"key": "days_attended", "label": "Días Asistidos"},
            {"key": "days_absent", "label": "Ausencias"},
            {"key": "late_count", "label": "Cant. Tardanzas"},
            {"key": "total_delay_min", "label": "Minutos Tarde Acum."},
            {"key": "total_hours", "label": "Total Horas Aprox."},
            {"key": "attendance_rate", "label": "% Asistencia"},
        ]
    }
]


def _build_report_dataset(
    cli: BioTimeClient,
    report_type: str,
    start_date: str,
    end_date: str,
    department_id: Optional[str] = None,
    company_id: Optional[str] = None,
    emp_code: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, str]]]:
    """Procesa y calcula el conjunto de datos para el reporte solicitado."""
    global _cache_emps_raw
    if _cache_emps_raw is None:
        _cache_emps_raw = cli.get_todo(EP_EMPLEADOS)

    # 1. Mapa de empleados
    emps_map: Dict[str, Dict[str, Any]] = {}
    for e in _cache_emps_raw:
        code = str(_val(e, "emp_code", "employee_code", "id", default="")).strip()
        fn = str(_val(e, "first_name", default="")).strip()
        ln = str(_val(e, "last_name", default="")).strip()
        name = f"{fn} {ln}".strip() or f"Emp {code}"
        
        dept = e.get("department") or {}
        dept_name = dept.get("dept_name") if isinstance(dept, dict) else str(dept)
        dept_id = str(dept.get("id") if isinstance(dept, dict) else dept or "")
        
        comp = e.get("company") or {}
        comp_name = comp.get("company_name") if isinstance(comp, dict) else str(comp)
        comp_id = str(comp.get("id") if isinstance(comp, dict) else comp or "")

        branch = e.get("branch") or {}
        branch_id = str(branch.get("id") if isinstance(branch, dict) else branch or "")

        pos = e.get("position") or {}
        pos_name = pos.get("position_name") if isinstance(pos, dict) else str(pos)

        emps_map[code] = {
            "emp_code": code,
            "name": name,
            "dept_id": dept_id,
            "dept_name": dept_name or "Sin Departamento",
            "company_id": comp_id,
            "company_name": comp_name or "PLASTITEC",
            "branch_id": branch_id,
            "position_name": pos_name or "Sin Cargo",
        }

    # 2. Filtrar empleados aplicables
    filtered_emps = {}
    for code, emp in emps_map.items():
        if department_id and department_id not in ("", "all") and emp["dept_id"] != department_id:
            continue
        if company_id and company_id not in ("", "all"):
            if emp["company_id"] != company_id and emp["branch_id"] != company_id:
                continue
        if emp_code and emp_code.strip() and emp_code.strip().lower() not in code.lower() and emp_code.strip().lower() not in emp["name"].lower():
            continue
        filtered_emps[code] = emp

    # 3. Mapa de terminales
    terminals_map: Dict[str, str] = {}
    try:
        raw_terms = cli.get_todo(EP_TERMINALS)
        for t in raw_terms:
            sn = str(_val(t, "sn", "terminal_sn", default="")).strip()
            alias = str(_val(t, "alias", "terminal_name", default=sn)).strip()
            if sn: terminals_map[sn] = alias
    except Exception:
        pass

    # 4. Transacciones
    start_time = f"{start_date} 00:00:00"
    end_time = f"{end_date} 23:59:59"
    url_tx = f"{EP_TRANSACC}?start_time={start_time}&end_time={end_time}&page_size=10000"
    r_tx = cli.sesion.get(cli.base + url_tx)
    all_txs = r_tx.json().get("data", []) if r_tx.status_code == 200 else []

    # Filtrar transacciones por los empleados seleccionados
    txs = [t for t in all_txs if str(t.get("emp_code") or "").strip() in filtered_emps]

    # Diccionarios de mapeo
    punch_states = {
        "0": "Entrada", "1": "Salida", "2": "Salida Refrigerio",
        "3": "Entrada Refrigerio", "4": "Entrada Extra", "5": "Salida Extra"
    }
    verify_types = {
        "15": "Rostro (VL Face)", "1": "Huella Digital",
        "3": "Contraseña", "4": "Tarjeta RFID", "0": "Automático"
    }

    rep_def = next((r for r in REPORT_CATALOG if r["id"] == report_type), REPORT_CATALOG[0])
    columns = rep_def["columns"]
    rows: List[Dict[str, Any]] = []

    # Generar fechas del período
    d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    delta_days = (d_end - d_start).days + 1
    dates_list = [(d_start + timedelta(days=i)) for i in range(max(1, min(delta_days, 62)))]

    if report_type == "transactions":
        for t in txs:
            code = str(t.get("emp_code") or "").strip()
            emp = filtered_emps.get(code, emps_map.get(code, {"name": f"Emp {code}", "dept_name": "--", "company_name": "--"}))
            sn = str(t.get("terminal_sn") or "")
            t_alias = terminals_map.get(sn, sn or "Biométrico")
            st_code = str(t.get("punch_state", "0"))
            vt_code = str(t.get("verify_type", "15"))

            rows.append({
                "punch_time": t.get("punch_time", ""),
                "emp_code": code,
                "emp_name": emp["name"],
                "dept_name": emp["dept_name"],
                "company_name": emp["company_name"],
                "terminal_alias": t_alias,
                "punch_state_str": punch_states.get(st_code, f"Marcación ({st_code})"),
                "verify_type_str": verify_types.get(vt_code, f"Método {vt_code}"),
            })
        rows.sort(key=lambda x: x["punch_time"], reverse=True)

    elif report_type in ("first_last", "late_arrivals", "absences", "summary", "daily_hours"):
        daily_punches: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for t in txs:
            code = str(t.get("emp_code") or "").strip()
            ptime = t.get("punch_time") or ""
            if not code or not ptime: continue
            day_str = ptime.split(" ")[0]
            daily_punches.setdefault((code, day_str), []).append(t)

        if report_type == "first_last":
            for (code, day), p_list in daily_punches.items():
                p_sorted = sorted(p_list, key=lambda x: x.get("punch_time") or "")
                emp = filtered_emps.get(code, emps_map.get(code, {"name": f"Emp {code}", "dept_name": "--", "company_name": "--"}))
                t_in = p_sorted[0].get("punch_time").split(" ")[1]
                t_out = p_sorted[-1].get("punch_time").split(" ")[1] if len(p_sorted) > 1 else t_in
                
                dt_in = datetime.strptime(p_sorted[0].get("punch_time"), "%Y-%m-%d %H:%M:%S")
                dt_out = datetime.strptime(p_sorted[-1].get("punch_time"), "%Y-%m-%d %H:%M:%S")
                diff_sec = max(0, int((dt_out - dt_in).total_seconds()))
                hours = diff_sec // 3600
                mins = (diff_sec % 3600) // 60
                time_spent = f"{hours:02d}h {mins:02d}m" if len(p_sorted) > 1 else "--"
                hours_dec = round(diff_sec / 3600.0, 2) if len(p_sorted) > 1 else 0.0

                sn_in = str(p_sorted[0].get("terminal_sn") or "")
                sn_out = str(p_sorted[-1].get("terminal_sn") or "")

                rows.append({
                    "att_date": day,
                    "emp_code": code,
                    "emp_name": emp["name"],
                    "dept_name": emp["dept_name"],
                    "first_punch": t_in,
                    "last_punch": t_out if len(p_sorted) > 1 else "Sin salida",
                    "total_punches": len(p_sorted),
                    "time_spent": time_spent,
                    "hours_decimal": hours_dec,
                    "first_terminal": terminals_map.get(sn_in, sn_in or "--"),
                    "last_terminal": terminals_map.get(sn_out, sn_out or "--"),
                })
            rows.sort(key=lambda x: (x["att_date"], x["emp_name"]))

        elif report_type == "late_arrivals":
            expected_h, expected_m = 7, 0
            tolerance_mins = 10
            threshold_sec = (expected_h * 3600) + (expected_m * 60) + (tolerance_mins * 60)

            for (code, day), p_list in daily_punches.items():
                p_sorted = sorted(p_list, key=lambda x: x.get("punch_time") or "")
                first_pt = p_sorted[0].get("punch_time")
                dt_in = datetime.strptime(first_pt, "%Y-%m-%d %H:%M:%S")
                time_in_sec = dt_in.hour * 3600 + dt_in.minute * 60 + dt_in.second

                if time_in_sec > threshold_sec:
                    delay_sec = time_in_sec - ((expected_h * 3600) + (expected_m * 60))
                    delay_m = delay_sec // 60
                    emp = filtered_emps.get(code, emps_map.get(code, {"name": f"Emp {code}", "dept_name": "--"}))
                    
                    if delay_m <= 15:
                        severity = "Leve (≤ 15m)"
                    elif delay_m <= 30:
                        severity = "Moderada (16-30m)"
                    else:
                        severity = "Crítica (> 30m)"

                    rows.append({
                        "att_date": day,
                        "emp_code": code,
                        "emp_name": emp["name"],
                        "dept_name": emp["dept_name"],
                        "scheduled_in": f"{expected_h:02d}:{expected_m:02d}:00",
                        "first_punch": dt_in.strftime("%H:%M:%S"),
                        "delay_minutes": delay_m,
                        "severity": severity,
                    })
            rows.sort(key=lambda x: (x["att_date"], -x["delay_minutes"]))

        elif report_type == "absences":
            for d in dates_list:
                if d.weekday() == 6:
                    continue
                day_str = d.strftime("%Y-%m-%d")
                for code, emp in filtered_emps.items():
                    if (code, day_str) not in daily_punches:
                        rows.append({
                            "att_date": day_str,
                            "emp_code": code,
                            "emp_name": emp["name"],
                            "dept_name": emp["dept_name"],
                            "position_name": emp["position_name"],
                            "status": "Inasistencia sin registro",
                        })
            rows.sort(key=lambda x: (x["att_date"], x["dept_name"], x["emp_name"]))

        elif report_type == "summary":
            labor_days = [d for d in dates_list if d.weekday() != 6]
            total_labor_days = max(1, len(labor_days))

            for code, emp in filtered_emps.items():
                attended_days = set()
                total_hours_sum = 0.0
                late_count = 0
                total_delay_min = 0

                for d in dates_list:
                    day_str = d.strftime("%Y-%m-%d")
                    if (code, day_str) in daily_punches:
                        attended_days.add(day_str)
                        p_list = sorted(daily_punches[(code, day_str)], key=lambda x: x.get("punch_time") or "")
                        dt_in = datetime.strptime(p_list[0].get("punch_time"), "%Y-%m-%d %H:%M:%S")
                        dt_out = datetime.strptime(p_list[-1].get("punch_time"), "%Y-%m-%d %H:%M:%S")
                        
                        sec_in = dt_in.hour * 3600 + dt_in.minute * 60 + dt_in.second
                        if sec_in > (7 * 3600 + 10 * 60):
                            late_count += 1
                            total_delay_min += (sec_in - 7 * 3600) // 60

                        if len(p_list) > 1:
                            diff_h = (dt_out - dt_in).total_seconds() / 3600.0
                            total_hours_sum += max(0.0, diff_h)

                d_attended = len(attended_days)
                d_absent = max(0, total_labor_days - d_attended)
                att_pct = round((d_attended / total_labor_days) * 100, 1)

                rows.append({
                    "emp_code": code,
                    "emp_name": emp["name"],
                    "dept_name": emp["dept_name"],
                    "company_name": emp["company_name"],
                    "days_attended": d_attended,
                    "days_absent": d_absent,
                    "late_count": late_count,
                    "total_delay_min": total_delay_min,
                    "total_hours": round(total_hours_sum, 1),
                    "attendance_rate": f"{att_pct}%",
                })
            rows.sort(key=lambda x: (x["dept_name"], x["emp_name"]))

        elif report_type == "daily_hours":
            # 1. Intentar consultar datos precalculados oficiales de BioTime
            native_found = False
            try:
                r_bt = cli.sesion.get(f"{cli.base}{EP_DAILY_HOURS}?start_date={start_date}&end_date={end_date}&page=1&limit=5000", timeout=TIMEOUT)
                if r_bt.status_code == 200:
                    bt_json = r_bt.json()
                    bt_data = bt_json.get("data", [])
                    if len(bt_data) > 0:
                        for item in bt_data:
                            code = str(item.get("emp_code") or "").strip()
                            if code in filtered_emps:
                                emp = filtered_emps[code]
                                rows.append({
                                    "att_date": str(item.get("att_date") or ""),
                                    "emp_code": code,
                                    "emp_name": emp["name"],
                                    "dept_name": emp["dept_name"],
                                    "company_name": emp["company_name"],
                                    "weekday_str": str(item.get("weekday") or ""),
                                    "timetable": str(item.get("timetable") or "--"),
                                    "check_in": str(item.get("check_in") or "--"),
                                    "check_out": str(item.get("check_out") or "--"),
                                    "total_time": float(item.get("total_time") or 0.0),
                                    "dayWT": float(item.get("dayWT") or 0.0),
                                    "ntWT": float(item.get("ntWT") or 0.0),
                                    "dayOT": float(item.get("dayOT") or item.get("pc_1") or 0.0),
                                    "ntOT": float(item.get("ntOT") or item.get("pc_2") or 0.0),
                                    "daySundayOT": float(item.get("daySundayOT") or item.get("pc_3") or 0.0),
                                    "ntSundayOT": float(item.get("ntSundayOT") or item.get("pc_4") or 0.0),
                                    "pc_5": float(item.get("pc_5") or 0.0),
                                    "pc_7": float(item.get("pc_7") or 0.0),
                                    "pc_8": float(item.get("pc_8") or 0.0),
                                    "novelty": "--",
                                })
                        native_found = len(rows) > 0
            except Exception:
                native_found = False

            # 2. Si BioTime aún no tiene procesados estos días, calcular con el motor de conceptos laborales
            if not native_found:
                weekday_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                for (code, day), p_list in daily_punches.items():
                    emp = filtered_emps.get(code, emps_map.get(code, {"name": f"Emp {code}", "dept_name": "--", "company_name": "--"}))
                    d_obj = datetime.strptime(day, "%Y-%m-%d").date()
                    w_name = weekday_names[d_obj.weekday()]

                    sorted_p = sorted(p_list, key=lambda x: x.get("punch_time") or "")
                    p_in = sorted_p[0].get("punch_time")
                    p_out = sorted_p[-1].get("punch_time") if len(sorted_p) > 1 else None

                    if p_in and p_out and p_in != p_out:
                        calc = _compute_daily_hours(p_in, p_out, d_obj)
                        t_in_str = p_in.split(" ")[1]
                        t_out_str = p_out.split(" ")[1]
                        novelty_str = "--"
                    else:
                        calc = {
                            "total_time": 0.0, "dayWT": 0.0, "ntWT": 0.0,
                            "dayOT": 0.0, "ntOT": 0.0, "daySundayOT": 0.0, "ntSundayOT": 0.0,
                            "pc_5": 0.0, "pc_7": 0.0, "pc_8": 0.0
                        }
                        t_in_str = p_in.split(" ")[1] if p_in else "--"
                        t_out_str = "--"
                        novelty_str = "Marcación única (sin salida)"

                    rows.append({
                        "att_date": day,
                        "emp_code": code,
                        "emp_name": emp["name"],
                        "dept_name": emp["dept_name"],
                        "company_name": emp["company_name"],
                        "weekday_str": w_name,
                        "timetable": "Programación Estándar" if d_obj.weekday() != 6 else "Turno / Descanso Dominical",
                        "check_in": t_in_str,
                        "check_out": t_out_str,
                        "total_time": calc["total_time"],
                        "dayWT": calc["dayWT"],
                        "ntWT": calc["ntWT"],
                        "dayOT": calc["dayOT"],
                        "ntOT": calc["ntOT"],
                        "daySundayOT": calc["daySundayOT"],
                        "ntSundayOT": calc["ntSundayOT"],
                        "pc_5": calc["pc_5"],
                        "pc_7": calc["pc_7"],
                        "pc_8": calc["pc_8"],
                        "novelty": novelty_str,
                    })
                rows.sort(key=lambda x: (x["att_date"], x["emp_name"]))

    unique_emps = len(set(r.get("emp_code") for r in rows if r.get("emp_code")))
    metrics = {
        "total_records": len(rows),
        "unique_employees": unique_emps,
        "date_range": f"{start_date} al {end_date}",
    }
    if report_type == "daily_hours":
        metrics["total_hours"] = round(sum(float(r.get("total_time") or 0.0) for r in rows), 1)
        metrics["total_overtime"] = round(sum(float(r.get("dayOT") or 0.0) + float(r.get("ntOT") or 0.0) + float(r.get("daySundayOT") or 0.0) + float(r.get("ntSundayOT") or 0.0) for r in rows), 1)
        metrics["total_surcharges"] = round(sum(float(r.get("pc_5") or 0.0) + float(r.get("pc_7") or 0.0) + float(r.get("pc_8") or 0.0) for r in rows), 1)

    return rows, metrics, columns


@app.get("/api/reports/types")
def list_report_types():
    """Catálogo de tipos de reportes de asistencia disponibles."""
    return {"reports": REPORT_CATALOG}


@app.get("/api/reports/data")
def get_report_data(
    report_type: str = Query("first_last"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    department_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    emp_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=5000),
):
    """Obtiene los datos paginados del reporte de asistencia seleccionado."""
    cli = get_client()
    try:
        rows, metrics, columns = _build_report_dataset(
            cli, report_type, start_date, end_date, department_id, company_id, emp_code
        )
        total = len(rows)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paged_rows = rows[start_idx:end_idx]

        return {
            "success": True,
            "report_type": report_type,
            "columns": columns,
            "metrics": metrics,
            "total": total,
            "page": page,
            "limit": limit,
            "data": paged_rows
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error generando reporte {report_type}: {e}")


@app.get("/api/reports/export")
def export_report_excel(
    report_type: str = Query("first_last"),
    start_date: str = Query(...),
    end_date: str = Query(...),
    department_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    emp_code: Optional[str] = Query(None),
):
    """Exporta los datos completos del reporte a un archivo Excel (.xlsx) corporativo."""
    cli = get_client()
    try:
        rows, metrics, columns = _build_report_dataset(
            cli, report_type, start_date, end_date, department_id, company_id, emp_code
        )
        rep_def = next((r for r in REPORT_CATALOG if r["id"] == report_type), REPORT_CATALOG[0])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = rep_def["name"][:31]
        ws.views.sheetView[0].showGridLines = True

        # Paleta y fuentes corporativas
        font_title = Font(name="Calibri", size=15, bold=True, color="0F172A")
        font_subtitle = Font(name="Calibri", size=10, italic=True, color="475569")
        fill_header = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        font_header = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        fill_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        font_data = Font(name="Calibri", size=10, color="1E293B")
        
        border_thin = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        align_center = Alignment(horizontal="center", vertical="center")
        align_left = Alignment(horizontal="left", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        # Bloque de Título
        ws.merge_cells("A1:G1")
        cell_title = ws.cell(row=1, column=1, value=f"BIOTIME · {rep_def['name'].upper()}")
        cell_title.font = font_title
        cell_title.alignment = align_left

        ws.merge_cells("A2:G2")
        cell_sub = ws.cell(row=2, column=1, value=f"Período: {start_date} al {end_date}  |  Total Registros: {len(rows)}  |  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        cell_sub.font = font_subtitle
        cell_sub.alignment = align_left

        # Fila de Encabezados (fila 4)
        ws.row_dimensions[4].height = 25
        for col_idx, col in enumerate(columns, 1):
            cell = ws.cell(row=4, column=col_idx, value=col["label"])
            cell.fill = fill_header
            cell.font = font_header
            cell.alignment = align_center
            cell.border = border_thin

        # Filas de Datos (a partir de fila 5)
        for r_idx, row_data in enumerate(rows, 5):
            ws.row_dimensions[r_idx].height = 20
            is_alt = (r_idx % 2 == 0)
            for c_idx, col in enumerate(columns, 1):
                val = row_data.get(col["key"], "")
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = font_data
                cell.border = border_thin
                if is_alt:
                    cell.fill = fill_alt

                if col["key"] in ("punch_time", "att_date", "emp_code", "first_punch", "last_punch", "scheduled_in", "total_punches", "delay_minutes", "days_attended", "days_absent", "late_count", "attendance_rate", "weekday_str", "check_in", "check_out"):
                    cell.alignment = align_center
                elif col["key"] in ("hours_decimal", "total_hours", "total_delay_min", "total_time", "dayWT", "ntWT", "dayOT", "ntOT", "daySundayOT", "ntSundayOT", "pc_5", "pc_7", "pc_8"):
                    cell.alignment = align_right
                else:
                    cell.alignment = align_left

        # Ajuste dinámico de anchos de columna
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 13)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"Reporte_{report_type}_{start_date}_a_{end_date}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error exportando reporte a Excel: {e}")


class CalculateBioTimeRequest(BaseModel):
    start_date: str
    end_date: str
    emp_codes: Optional[List[str]] = None
    departments: Optional[List[str]] = None


@app.post("/api/reports/calculate_biotime")
def api_calculate_biotime(req: CalculateBioTimeRequest):
    """Dispara el cálculo oficial nativo de asistencia en BioTime para los empleados y fechas seleccionadas."""
    try:
        s = _get_biotime_web_session()
        r_page = s.get(BASE_URL + EP_CALCULATION, timeout=TIMEOUT)
        for c in s.cookies: c.secure = False
        csrf = s.cookies.get("csrftoken")

        cli = get_client()
        emps = cli.get_todo(EP_EMPLEADOS)
        target_ids = []
        if req.emp_codes and len(req.emp_codes) > 0:
            emp_set = set(req.emp_codes)
            for e in emps:
                if str(e.get("emp_code") or "").strip() in emp_set:
                    target_ids.append(str(e.get("id")))
        else:
            target_ids = [str(e.get("id")) for e in emps[:300]]

        post_data = [
            ("csrfmiddlewaretoken", csrf),
            ("start_date", req.start_date),
            ("end_date", req.end_date),
        ]
        for eid in target_ids:
            post_data.append(("emp", eid))

        headers = {
            "X-CSRFToken": csrf,
            "Referer": BASE_URL + EP_CALCULATION,
            "X-Requested-With": "XMLHttpRequest"
        }
        r_calc = s.post(BASE_URL + EP_CALCULATION, data=post_data, headers=headers, timeout=TIMEOUT)
        res_json = r_calc.json() if r_calc.status_code == 200 else {"code": -1, "msg": r_calc.text}

        return {
            "success": res_json.get("code") == 0,
            "message": res_json.get("msg", "Cálculo ejecutado en BioTime"),
            "target_employees": len(target_ids),
            "start_date": req.start_date,
            "end_date": req.end_date,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al invocar cálculo en BioTime: {str(e)}")


# Servir la interfaz estática
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main():
    import uvicorn
    print("\n" + "═" * 65)
    print("  BIOTIME MANAGER & EXPLORER  ·  Servidor Web")
    print("  Acceso Local:    http://localhost:8000")
    print("  Acceso en Red:   http://172.16.1.178:8000")
    print("═" * 65 + "\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
