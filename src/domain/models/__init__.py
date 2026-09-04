"""
Modelos de dominio centralizados para el Módulo de Tiempos SIRH.
"""
from src.domain.models.auditoria import AuditoriaEvento
from src.domain.models.identidad import (
    Cargo,
    Departamento,
    Area,
    Empleado,
    MapeoIdentidad,
    SupervisorAlcance,
)
from src.domain.models.turno import (
    Turno,
    CicloRotativo,
    CicloDetalleDia,
    ProgramacionEmpleado,
)
from src.domain.models.regla import ReglaLaboral

__all__ = [
    "AuditoriaEvento",
    "Cargo",
    "Departamento",
    "Area",
    "Empleado",
    "MapeoIdentidad",
    "SupervisorAlcance",
    "Turno",
    "CicloRotativo",
    "CicloDetalleDia",
    "ProgramacionEmpleado",
    "ReglaLaboral",
]
