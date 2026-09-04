"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CONFIGURACIÓN CENTRALIZADA · BIOTIME                                        ║
║  Lee exclusivamente desde el archivo .env o variables de entorno del sistema. ║
║  No contiene IPs, credenciales ni rutas privadas hardcodeadas.              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
from pathlib import Path
from typing import List

# Cargar .env si existe
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent / ".env"
    if _env_file.exists():
        load_dotenv(dotenv_path=_env_file)
except ImportError:
    pass


def _require_env(key: str) -> str:
    """Obtiene una variable obligatoria o advierte si falta."""
    val = os.getenv(key)
    if not val:
        return ""
    return val.strip()


def _bool_from_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "si", "s")


def _list_from_env(key: str) -> List[str]:
    val = os.getenv(key)
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


# --- Servidor y credenciales (100% desde .env) ------------------------------
BASE_URL: str   = _require_env("BIOTIME_BASE_URL").rstrip("/")
USUARIO: str    = _require_env("BIOTIME_USER")
CLAVE: str      = _require_env("BIOTIME_PASS")

# --- Rendimiento de red -----------------------------------------------------
TIMEOUT: int    = int(os.getenv("BIOTIME_TIMEOUT", "60"))
PAGE_SIZE: int  = int(os.getenv("BIOTIME_PAGE_SIZE", "500"))
VERIFY_SSL: bool= _bool_from_env("BIOTIME_VERIFY_SSL", False)

# --- Endpoints Base (Personal & Organización) ------------------------------
EP_TOKEN: str             = os.getenv("BIOTIME_EP_TOKEN", "/jwt-api-token-auth/")
EP_EMPLEADOS: str         = os.getenv("BIOTIME_EP_EMPLEADOS", "/personnel/api/employees/")
EP_EMPLEADO_ADD: str      = os.getenv("BIOTIME_EP_EMPLEADO_ADD", "/personnel/employee/add/")
EP_EMPLEADO_EDIT: str     = os.getenv("BIOTIME_EP_EMPLEADO_EDIT", "/personnel/employee/edit/")
EP_DEPARTAMENTOS: str     = os.getenv("BIOTIME_EP_DEPARTAMENTOS", "/personnel/api/departments/")
EP_CARGOS: str            = os.getenv("BIOTIME_EP_CARGOS", "/personnel/api/positions/")
EP_AREAS: str             = os.getenv("BIOTIME_EP_AREAS", "/personnel/api/areas/")
EP_EMPRESAS: str          = os.getenv("BIOTIME_EP_EMPRESAS", "/personnel/api/company/")
EP_COMPANIAS: str         = os.getenv("BIOTIME_EP_COMPANIAS", "/personnel/api/department/tree/")
EP_CENTROS_COSTOS: str    = os.getenv("BIOTIME_EP_CENTROS_COSTOS", "/personnel/api/costcenters/")

# --- Endpoints Base (Asistencia & Turnos) ----------------------------------
EP_TRANSACC: str          = os.getenv("BIOTIME_EP_TRANSACC", "/iclock/api/transactions/")
EP_TIMEINTERVALS: str     = os.getenv("BIOTIME_EP_TIMEINTERVALS", "/att/api/timeintervals/")
EP_SHIFT_DETAILS: str     = os.getenv("BIOTIME_EP_SHIFT_DETAILS", "/att/api/shift_details/")
EP_ATTSHIFTS: str         = os.getenv("BIOTIME_EP_ATTSHIFTS", "/att/api/attshifts/")
EP_ATTSCHEDULES: str      = os.getenv("BIOTIME_EP_ATTSCHEDULES", "/att/api/attschedules/")
EP_TEMPSCHEDULES: str     = os.getenv("BIOTIME_EP_TEMPSCHEDULES", "/att/api/tempschedules/")
EP_LEAVE: str             = os.getenv("BIOTIME_EP_LEAVE", "/att/api/leave/")
EP_BREAKTIME: str         = os.getenv("BIOTIME_EP_BREAKTIME", "/att/api/breaktime/")

# --- Endpoints Base (Dispositivos & Terminales) ----------------------------
EP_TERMINALS: str         = os.getenv("BIOTIME_EP_TERMINALS", "/iclock/api/terminals/")
EP_DEVICE_STATUS: str     = os.getenv("BIOTIME_EP_DEVICE_STATUS", "/base/api/deviceStatus/")

# --- Endpoints Oficiales de Motor de Cálculo y Reportes BioTime ------------
EP_CALCULATION: str       = os.getenv("BIOTIME_EP_CALCULATION", "/att/calculation_view/")
EP_SETTLEMENT_CALC: str   = os.getenv("BIOTIME_EP_SETTLEMENT_CALC", "/att/settlement_calculation/")
EP_DAILY_HOURS: str       = os.getenv("BIOTIME_EP_DAILY_HOURS", "/att/api/dailyHourReport/")
EP_FIRST_LAST_REPORT: str = os.getenv("BIOTIME_EP_FIRST_LAST_REPORT", "/att/api/firstLastReport/")
EP_DAILY_ATT_REPORT: str  = os.getenv("BIOTIME_EP_DAILY_ATT_REPORT", "/att/api/dailyAttendanceReport/")
EP_LATE_REPORT: str       = os.getenv("BIOTIME_EP_LATE_REPORT", "/att/api/lateReport/")
EP_ABSENT_REPORT: str     = os.getenv("BIOTIME_EP_ABSENT_REPORT", "/att/api/absentReport/")
EP_PAYROLL_CONCEPTS: str  = os.getenv("BIOTIME_EP_PAYROLL_CONCEPTS", "/att/payrollconceptcode/table/")

# --- Endpoints candidatos con fallback --------------------------------------
EP_TURNOS_CANDIDATOS: List[str]   = _list_from_env("BIOTIME_EP_TURNOS_CANDIDATOS")
EP_HORARIOS_CANDIDATOS: List[str] = _list_from_env("BIOTIME_EP_HORARIOS_CANDIDATOS")


def validar_configuracion() -> bool:
    """Verifica que las variables mínimas para operar existan en el entorno."""
    faltantes = []
    if not BASE_URL:
        faltantes.append("BIOTIME_BASE_URL")
    if not USUARIO:
        faltantes.append("BIOTIME_USER")
    if not CLAVE:
        faltantes.append("BIOTIME_PASS")

    if faltantes:
        print(f"\n  ✗ Falta configurar en el archivo .env: {', '.join(faltantes)}")
        print("    Copia .env.example a .env y define los valores requeridos.\n")
        return False
    return True
