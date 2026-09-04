"""
Modelo de Reglas Laborales y Políticas Versionadas por Fecha.
Principio inviolable: Ninguna regla laboral rígida en el código.
"""
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, JSON
from src.core.database import Base


class ReglaLaboral(Base):
    """
    Representa una regla de cálculo laboral con vigencia temporal estricta.
    Permite reproducir cálculos pasados con las reglas exactas vigentes a esa fecha.
    """
    __tablename__ = "sys_regla_laboral"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), nullable=False, index=True)
    clasificacion = Column(String(20), nullable=False) # 'LEGAL', 'POLITICA', 'CONVENCION', 'CONFIG'
    version = Column(Integer, nullable=False, default=1)
    fecha_inicio_vigencia = Column(Date, nullable=False)
    fecha_fin_vigencia = Column(Date, nullable=True)     # NULL indica vigencia actual indefinida
    parametros = Column(JSON, nullable=False)            # Ej: {"horas_semanales": 42} o {"hora_inicio": "19:00"}
    fuente_normativa = Column(String(100), nullable=True) # Ej: "Ley 2101 de 2021, Art. 3"
    descripcion = Column(Text, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    creado_el = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def es_vigente_en(self, fecha: date) -> bool:
        """Verifica si la regla aplica para una fecha de imputación determinada."""
        if fecha < self.fecha_inicio_vigencia:
            return False
        if self.fecha_fin_vigencia and fecha > self.fecha_fin_vigencia:
            return False
        return self.activo
