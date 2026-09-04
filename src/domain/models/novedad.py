"""
Modelo de Condiciones Especiales y Novedades con Vigencia Temporal.
Implementa el requerimiento P2 (Lactancia modelada como condición con vigencia).
"""
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from src.core.database import Base


class CondicionEspecialEmpleado(Base):
    """
    Condición temporal con vigencia estricta (ej. Lactancia Art. 238 CST).
    Modifica el cálculo de la jornada del trabajador mientras esté activa.
    """
    __tablename__ = "rrhh_condicion_especial"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("rrhh_empleado.id"), nullable=False, index=True)
    tipo_condicion = Column(String(50), nullable=False) # 'LACTANCIA', 'PERMISO_ESTUDIO', 'RESTRICCION_MEDICA'
    fecha_inicio = Column(Date, nullable=False, index=True)
    fecha_fin = Column(Date, nullable=False, index=True)
    minutos_reconocidos_dia = Column(Integer, nullable=False, default=60) # 60 min para lactancia
    es_activa = Column(Boolean, nullable=False, default=True)
    motivo_soporte = Column(Text, nullable=True)
    creado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    empleado = relationship("Empleado")

    def es_vigente_en(self, fecha: date) -> bool:
        if not self.es_activa:
            return False
        return self.fecha_inicio <= fecha <= self.fecha_fin
