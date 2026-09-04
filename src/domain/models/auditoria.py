"""
Modelo de datos para la Auditoría Inmutable.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from src.core.database import Base


class AuditoriaEvento(Base):
    __tablename__ = "sys_auditoria_trazabilidad"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp_utc = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    usuario_id = Column(String(50), nullable=False)
    usuario_nombre = Column(String(100), nullable=False)
    rol = Column(String(50), nullable=False)
    ip_origen = Column(String(45), nullable=False)
    accion = Column(String(50), nullable=False)           # 'APROBAR', 'AJUSTAR', 'RECHAZAR', 'CREAR', etc.
    entidad = Column(String(50), nullable=False)          # 'jornada_resuelta', 'turno', 'empleado'
    entidad_id = Column(String(50), nullable=False)
    valor_anterior = Column(JSON, nullable=True)
    valor_nuevo = Column(JSON, nullable=True)
    motivo_justificacion = Column(Text, nullable=False)    # Obligatorio por norma de calidad
    signature_hash = Column(String(64), nullable=False)    # SHA-256 de los campos para verificar no-manipulación

    def __repr__(self):
        return f"<AuditoriaEvento {self.id} | {self.accion} | {self.entidad}:{self.entidad_id} | por {self.usuario_id}>"
