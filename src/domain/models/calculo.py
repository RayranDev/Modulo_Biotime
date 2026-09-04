"""
Modelos de Datos para las Etapas 3, 4, 5 y 6 del Pipeline de Cálculo:
- Etapa 3: Jornada Resuelta (Cruce con turno, imputación a día de inicio)
- Etapa 4: Segmentación Temporal Atómica (Partición por medianoche, franja, tipo de día)
- Etapa 5: Clasificación en 3 Pasadas (Diaria, Semanal 42h, Mensual Habitual)
- Etapa 6: Resultado Diario / Agregación para Aprobación
"""
from datetime import datetime, timezone, date
import uuid
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Date, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.core.database import Base


class JornadaResuelta(Base):
    """
    Etapa 3: Jornada de trabajo consolidada cruzando marcaciones contra turno programado.
    Principio inviolable: La imputación es SIEMPRE al DÍA DE INICIO del turno.
    """
    __tablename__ = "rrhh_jornada_resuelta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=False, index=True)
    fecha_imputacion = Column(Date, nullable=False, index=True) # Día de inicio del turno
    turno_id = Column(Integer, ForeignKey("rrhh_turno.id"), nullable=True)

    inicio_programado = Column(DateTime, nullable=True)
    fin_programado = Column(DateTime, nullable=True)

    inicio_real = Column(DateTime, nullable=True)
    fin_real = Column(DateTime, nullable=True)

    minutos_trabajados_brutos = Column(Integer, nullable=False, default=0)
    minutos_descuento_almuerzo = Column(Integer, nullable=False, default=0)
    minutos_trabajados_netos = Column(Integer, nullable=False, default=0)
    horas_extra_redondeadas = Column(Numeric(6, 2), nullable=False, default=0.0)

    estado_jornada = Column(String(30), nullable=False, default="COMPLETA") # 'COMPLETA', 'SIN_ENTRADA', 'SIN_SALIDA', 'SIN_TURNO'
    calculo_id = Column(String(36), nullable=False, index=True)
    calculado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    empleado = relationship("Empleado")
    turno = relationship("Turno")
    segmentos = relationship("SegmentoTemporal", back_populates="jornada", cascade="all, delete-orphan")


class SegmentoTemporal(Base):
    """
    Etapa 4: Segmento atómico indivisible delimitado por fronteras:
    - Medianoche (00:00:00)
    - Frontera nocturna (ej. 19:00 a 06:00)
    - Tipo de día (Ordinario / Festivo / Descanso)
    - Límites de jornada programada (dentro/fuera)
    """
    __tablename__ = "rrhh_segmento_temporal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    jornada_id = Column(Integer, ForeignKey("rrhh_jornada_resuelta.id"), nullable=False, index=True)
    inicio = Column(DateTime, nullable=False)
    fin = Column(DateTime, nullable=False)
    duracion_minutos = Column(Integer, nullable=False)
    tipo_franja = Column(String(20), nullable=False)         # 'DIURNO', 'NOCTURNO'
    tipo_dia = Column(String(30), nullable=False)            # 'ORDINARIO', 'DOMINICAL', 'FESTIVO', 'DESCANSO'
    es_dentro_jornada = Column(Boolean, nullable=False)       # True si cae dentro del horario programado

    jornada = relationship("JornadaResuelta", back_populates="segmentos")
    clasificaciones = relationship("ClasificacionSegmento", back_populates="segmento", cascade="all, delete-orphan")


class ClasificacionSegmento(Base):
    """
    Etapa 5: Asignación de conceptos de nómina al segmento.
    Persiste las 3 pasadas sin sobreescribir.
    """
    __tablename__ = "rrhh_clasificacion_segmento"

    id = Column(Integer, primary_key=True, autoincrement=True)
    segmento_id = Column(Integer, ForeignKey("rrhh_segmento_temporal.id"), nullable=False, index=True)
    calculo_id = Column(String(36), nullable=False, index=True)
    concepto_dominio = Column(String(50), nullable=False)    # 'ORDINARIA', 'RN', 'HEDO', 'HENO', 'HEDF', 'HENF', 'RDF'
    horas = Column(Numeric(6, 2), nullable=False)
    pasada = Column(Integer, nullable=False)                 # 1 = Diaria, 2 = Semanal 42h, 3 = Mensual Habitual
    regla_version_id = Column(Integer, nullable=True)

    segmento = relationship("SegmentoTemporal", back_populates="clasificaciones")


class ResultadoDiario(Base):
    """
    Etapa 6: Conceptos agregados por empleado y fecha de imputación para aprobación del jefe y exportación.
    """
    __tablename__ = "rrhh_resultado_diario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=False, index=True)
    fecha_imputacion = Column(Date, nullable=False, index=True)
    concepto_dominio = Column(String(50), nullable=False)    # Ej: '0200', '0210', '0220', etc.
    cantidad_horas = Column(Numeric(6, 2), nullable=False)
    estado_aprobacion = Column(String(20), nullable=False, default="PENDIENTE") # 'PENDIENTE', 'APROBADO', 'AJUSTADO', 'RECHAZADO'
    supervisor_id = Column(String(50), nullable=True)
    ajuste_horas = Column(Numeric(6, 2), nullable=True)
    motivo_ajuste = Column(String(255), nullable=True)
    calculo_id = Column(String(36), nullable=False, index=True)
    aprobado_el = Column(DateTime, nullable=True)

    empleado = relationship("Empleado")
