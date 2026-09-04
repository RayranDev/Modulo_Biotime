"""
Modelos de Datos para el Ciclo de Períodos 11→10 y Registro de Exportaciones Sinergy (Fase 6).
"""
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Numeric, ForeignKey, Text
from sqlalchemy.orm import relationship
from src.core.database import Base


class PeriodoNomina(Base):
    """
    Ciclo mensual de conceptos variables: del día 11 del mes anterior al día 10 del mes actual.
    Máquina de estados:
    - ABIERTO: Supervisores aprueban a diario.
    - EN_PROCESAMIENTO: Bloqueo de modificaciones para supervisores; RRHH valida.
    - CERRADO: Archivo plano generado para Sinergy; inmutable.
    - REABIERTO: Reapertura controlada con rol elevado y traza obligatoria.
    """
    __tablename__ = "rrhh_periodo_nomina"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True) # Ej: 'PER_2026_09'
    fecha_inicio = Column(Date, nullable=False, index=True)              # Día 11
    fecha_fin = Column(Date, nullable=False, index=True)                 # Día 10
    estado = Column(String(25), nullable=False, default="ABIERTO")       # 'ABIERTO', 'EN_PROCESAMIENTO', 'CERRADO', 'REABIERTO'

    bloqueado_en = Column(DateTime, nullable=True)
    bloqueado_por = Column(String(50), nullable=True)
    cerrado_en = Column(DateTime, nullable=True)
    cerrado_por = Column(String(50), nullable=True)
    motivo_reapertura = Column(Text, nullable=True)
    creado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    exportaciones = relationship("ExportacionSinergy", back_populates="periodo", cascade="all, delete-orphan")

    def esta_bloqueado_para_supervisores(self) -> bool:
        return self.estado in ("EN_PROCESAMIENTO", "CERRADO")


class ExportacionSinergy(Base):
    """
    Registro inmutable del archivo plano generado para Sinergy.
    Almacena hash criptográfico SHA-256 para verificación en auditorías.
    """
    __tablename__ = "rrhh_exportacion_sinergy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    periodo_id = Column(Integer, ForeignKey("rrhh_periodo_nomina.id"), nullable=False, index=True)
    nombre_archivo = Column(String(100), nullable=False) # FINAL_SINER_<YYYY-MM-DD>_<YYYY-MM-DD>.txt
    contenido_txt = Column(Text, nullable=False)
    hash_sha256 = Column(String(64), nullable=False)
    total_lineas = Column(Integer, nullable=False)
    total_horas = Column(Numeric(10, 2), nullable=False)
    generado_por = Column(String(50), nullable=False)
    generado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    periodo = relationship("PeriodoNomina", back_populates="exportaciones")
