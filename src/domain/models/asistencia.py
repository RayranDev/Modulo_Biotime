"""
Modelos de Datos para las Etapas 1 y 2 del Pipeline de Cálculo:
- Etapa 1: Marcación Cruda (Inmutable, PK natural = biotime_trans_id)
- Etapa 2: Marcación Normalizada (Limpieza, duplicados, emparejamiento)
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.core.database import Base


class MarcacionCruda(Base):
    """
    Etapa 1: Registro crudo inmutable recibido directamente desde BioTime 8.5.
    La clave primaria es el ID numérico asignado por BioTime.
    """
    __tablename__ = "rrhh_marcacion_cruda"

    biotime_trans_id = Column(BigInteger, primary_key=True) # ID nativo de BioTime (ej. 423969)
    emp_code = Column(String(50), nullable=False, index=True)
    punch_time = Column(DateTime, nullable=False, index=True)
    upload_time = Column(DateTime, nullable=False, index=True)
    punch_state = Column(String(10), nullable=False)        # '0' (In), '1' (Out), '255' (Auto)
    verify_type = Column(Integer, nullable=True)
    terminal_sn = Column(String(50), nullable=False, index=True)
    terminal_alias = Column(String(100), nullable=True)
    area_alias = Column(String(100), nullable=True)
    raw_payload = Column(JSON, nullable=False)              # Payload JSON completo original
    ingestado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    normalizada = relationship("MarcacionNormalizada", back_populates="cruda", uselist=False)

    def __repr__(self):
        return f"<MarcacionCruda id={self.biotime_trans_id} emp={self.emp_code} punch={self.punch_time}>"


class MarcacionNormalizada(Base):
    """
    Etapa 2: Marcación procesada y validada contra la identidad de SIRH.
    Identifica tipo de evento (entrada/salida), duplicados y correcciones manuales.
    """
    __tablename__ = "rrhh_marcacion_normalizada"

    id = Column(Integer, primary_key=True, autoincrement=True)
    biotime_trans_id = Column(BigInteger, ForeignKey("rrhh_marcacion_cruda.biotime_trans_id"), unique=True, nullable=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=False, index=True)
    timestamp_efectivo = Column(DateTime, nullable=False, index=True)
    tipo_evento = Column(String(20), nullable=False)        # 'ENTRADA', 'SALIDA', 'INDETERMINADO'
    es_duplicada = Column(Boolean, nullable=False, default=False)
    es_manual = Column(Boolean, nullable=False, default=False)
    justificacion_tipificada = Column(String(100), nullable=True) # 'Permiso remunerado', 'Olvido de marcación', etc.
    motivo_detalle = Column(String(255), nullable=True)
    modificado_por = Column(String(50), nullable=True)
    procesado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    cruda = relationship("MarcacionCruda", back_populates="normalizada")
    empleado = relationship("Empleado")

    def __repr__(self):
        return f"<MarcacionNormalizada id={self.id} emp_id={self.empleado_id} tipo={self.tipo_evento} time={self.timestamp_efectivo}>"
