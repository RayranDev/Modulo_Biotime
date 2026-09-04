"""
Modelos de Dominio para Turnos, Ciclos Rotativos y Programación en SIRH.
"""
from datetime import datetime, timezone, time, timedelta
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Time, Date, ForeignKey
from sqlalchemy.orm import relationship
from src.core.database import Base


class Turno(Base):
    """
    Definición de turno en SIRH.
    La salida siempre se proyecta como timestamp completo con fecha y hora
    a partir de la hora de inicio + duracion_minutos.
    """
    __tablename__ = "rrhh_turno"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    alias = Column(String(100), nullable=False)
    hora_inicio = Column(Time, nullable=False)
    duracion_minutos = Column(Integer, nullable=False)
    descuenta_almuerzo = Column(Boolean, nullable=False, default=False)
    minutos_almuerzo = Column(Integer, nullable=False, default=60)
    tolerancia_entrada_minutos = Column(Integer, nullable=False, default=15)
    tolerancia_salida_minutos = Column(Integer, nullable=False, default=15)
    es_rotativo = Column(Boolean, nullable=False, default=True)
    activo = Column(Boolean, nullable=False, default=True)
    biotime_shift_id = Column(Integer, nullable=True)  # ID original de BioTime para trazabilidad inicial

    def calcular_fin_proyectado(self, fecha_inicio: datetime.date) -> datetime:
        """Calcula la fecha y hora exacta de fin del turno sin perder el cambio de día."""
        inicio_dt = datetime.combine(fecha_inicio, self.hora_inicio)
        return inicio_dt + timedelta(minutes=self.duracion_minutos)


class CicloRotativo(Base):
    """
    Plantilla de rotación recurrente (ej. 4x3 de 7 días: 2 días día, 2 noches, 3 descansos).
    """
    __tablename__ = "rrhh_ciclo_rotativo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    duracion_dias = Column(Integer, nullable=False, default=7)

    dias = relationship("CicloDetalleDia", back_populates="ciclo", cascade="all, delete-orphan")


class CicloDetalleDia(Base):
    """
    Detalle de un día específico dentro del ciclo (Día 1 a Día N).
    """
    __tablename__ = "rrhh_ciclo_detalle_dia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ciclo_id = Column(Integer, ForeignKey("rrhh_ciclo_rotativo.id"), nullable=False)
    dia_indice = Column(Integer, nullable=False)             # 1 a duracion_dias
    turno_id = Column(Integer, ForeignKey("rrhh_turno.id"), nullable=True) # NULL si es descanso
    es_descanso = Column(Boolean, nullable=False, default=False)

    ciclo = relationship("CicloRotativo", back_populates="dias")
    turno = relationship("Turno")


class ProgramacionEmpleado(Base):
    """
    Asignación de turno o ciclo a un empleado por rango de vigencia.
    """
    __tablename__ = "rrhh_programacion_empleado"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=False, index=True)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    ciclo_id = Column(Integer, ForeignKey("rrhh_ciclo_rotativo.id"), nullable=True)
    turno_fijo_id = Column(Integer, ForeignKey("rrhh_turno.id"), nullable=True) # Para administrativos
    dia_inicio_ciclo = Column(Integer, nullable=False, default=1)               # Offset inicial en el ciclo
    creado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    empleado = relationship("Empleado")
    ciclo = relationship("CicloRotativo")
    turno_fijo = relationship("Turno")
