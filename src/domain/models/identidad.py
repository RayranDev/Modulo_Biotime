"""
Modelos de Identidad, Organización y Mapeo Multi-Sistema.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Date
from sqlalchemy.orm import relationship
from src.core.database import Base


class Cargo(Base):
    __tablename__ = "rrhh_cargo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    # Regla D14: El perfil laboral se determina por CARGO
    perfil_laboral = Column(String(30), nullable=False, default="ROTATIVO") # 'ROTATIVO' o 'ADMINISTRATIVO'
    activo = Column(Boolean, nullable=False, default=True)


class Departamento(Base):
    __tablename__ = "rrhh_departamento"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)


class Area(Base):
    __tablename__ = "rrhh_area"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False)
    nombre = Column(String(100), nullable=False)
    departamento_id = Column(Integer, ForeignKey("rrhh_departamento.id"), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)


class Empleado(Base):
    __tablename__ = "rrhh_empleado"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sirh_emp_id = Column(String(50), unique=True, nullable=False, index=True)
    nombres = Column(String(100), nullable=False)
    apellidos = Column(String(100), nullable=False)
    cargo_id = Column(Integer, ForeignKey("rrhh_cargo.id"), nullable=False)
    departamento_id = Column(Integer, ForeignKey("rrhh_departamento.id"), nullable=True)
    area_id = Column(Integer, ForeignKey("rrhh_area.id"), nullable=True)
    jefe_inmediato_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=True)
    fecha_ingreso = Column(Date, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    creado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    cargo = relationship("Cargo")
    departamento = relationship("Departamento")
    area = relationship("Area")
    jefe_inmediato = relationship("Empleado", remote_side=[id])


class MapeoIdentidad(Base):
    """
    Tabla explícita de correspondencia multi-sistema.
    Prohíbe heurísticas de ceros a la izquierda o conjeturas de IDs.
    """
    __tablename__ = "sys_mapeo_identidad"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), unique=True, nullable=False)
    sirh_emp_id = Column(String(50), unique=True, nullable=False, index=True)
    biotime_emp_id = Column(Integer, unique=True, nullable=False, index=True)       # ID interno BioTime (ej. 1281)
    biotime_emp_code = Column(String(50), unique=True, nullable=False, index=True)   # emp_code en reloj (ej. "7334")
    sinergy_emp_code = Column(String(50), unique=True, nullable=False, index=True)   # código en nómina (ej. "8639")
    tipo_vinculacion = Column(String(30), nullable=False, default="DIRECTO")         # 'DIRECTO', 'GRANSERVICIOS', 'SENA'
    activo = Column(Boolean, nullable=False, default=True)
    actualizado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    empleado = relationship("Empleado")


class SupervisorAlcance(Base):
    """
    Define el ámbito organizacional de un supervisor para aprobación por excepción.
    """
    __tablename__ = "rrhh_supervisor_alcance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    supervisor_usuario_id = Column(String(50), nullable=False, index=True)
    departamento_id = Column(Integer, ForeignKey("rrhh_departamento.id"), nullable=True)
    area_id = Column(Integer, ForeignKey("rrhh_area.id"), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
