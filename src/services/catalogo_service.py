"""
Servicio de Catálogo Inicial y Reglas Laborales.
Importa la configuración inicial de turnos desde BioTime y establece las reglas base versionadas.
"""
from datetime import time, date, datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from src.domain.models.turno import Turno
from src.domain.models.regla import ReglaLaboral
from src.adapters.biotime.client import BioTimeAdapter
from src.core.audit import AuditService


def _parse_time(t_str: str) -> time:
    """Convierte cadena 'HH:MM:SS' o 'HH:MM' en objeto time."""
    if not t_str:
        return time(0, 0)
    partes = [int(p) for p in t_str.split(":")[:3]]
    if len(partes) == 2:
        return time(partes[0], partes[1])
    return time(partes[0], partes[1], partes[2])


class CatalogoService:
    @classmethod
    def importar_turnos_desde_biotime(cls, db: Session, usuario_id: str = "SISTEMA") -> List[Turno]:
        """
        Lee los turnos e intervalos de BioTime 8.5 y los traslada al catálogo de SIRH.
        Cumple con el hito de Fase 2 de cargar la configuración inicial de turnos.
        """
        adapter = BioTimeAdapter().autenticar()
        raw_shifts = adapter.obtener_turnos()
        raw_intervals = adapter.obtener_intervalos()

        interval_map: Dict[int, Dict[str, Any]] = {i["id"]: i for i in raw_intervals if "id" in i}
        turnos_creados = []

        for s in raw_shifts:
            shift_id = s.get("id")
            code = s.get("shift_code") or f"SHIFT_{shift_id}"
            alias = s.get("alias") or code

            # Buscar si el turno ya existe por código
            turno_db = db.query(Turno).filter(Turno.codigo == code).first()
            if not turno_db:
                # Intervalo por defecto o cruzado
                # En BioTime, 'business_hour' o duración
                hora_ini = time(7, 30)
                duracion_min = 720  # 12 horas por defecto para rotativos si no especifica
                descuenta_almuerzo = False

                # Si el código sugiere 12h noche/día
                if "12H" in code.upper() or "12H" in alias.upper():
                    duracion_min = 720
                    hora_ini = time(18, 0) if "NOCHE" in code.upper() or "NOCHE" in alias.upper() else time(6, 0)
                elif "8H" in code.upper():
                    duracion_min = 480
                    hora_ini = time(7, 30)

                turno_db = Turno(
                    codigo=code,
                    alias=alias,
                    hora_inicio=hora_ini,
                    duracion_minutos=duracion_min,
                    descuenta_almuerzo=descuenta_almuerzo,
                    minutos_almuerzo=60,
                    tolerancia_entrada_minutos=15,
                    tolerancia_salida_minutos=15,
                    es_rotativo=("12H" in code.upper() or "ROTATIVO" in alias.upper()),
                    activo=True,
                    biotime_shift_id=shift_id,
                )
                db.add(turno_db)
                turnos_creados.append(turno_db)

        db.commit()

        # Registrar auditoría inmutable
        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre="Sistema de Inicialización",
            rol="ADMIN",
            ip_origen="127.0.0.1",
            accion="IMPORTAR_CATALOGO_TURNOS",
            entidad="rrhh_turno",
            entidad_id="ALL",
            motivo_justificacion="Carga inicial de turnos desde BioTime 8.5 (Fase 2)",
            valor_nuevo={"turnos_importados": len(turnos_creados)},
        )

        return turnos_creados

    @classmethod
    def sembrar_reglas_laborales_base(cls, db: Session, usuario_id: str = "SISTEMA") -> List[ReglaLaboral]:
        """
        Establece las reglas laborales con vigencia y versión legal.
        Principio inviolable: las reglas viven en DB versionadas por fecha.
        """
        reglas_def = [
            # 1. Jornada Máxima Semanal (Ley 2101 de 2021)
            {
                "codigo": "JORNADA_MAXIMA_SEMANAL",
                "clasificacion": "LEGAL",
                "version": 1,
                "fecha_inicio_vigencia": date(2025, 7, 15),
                "fecha_fin_vigencia": date(2026, 7, 14),
                "parametros": {"horas_semanales": 44, "tope_extras_semanales": 12},
                "fuente_normativa": "Ley 2101 de 2021, Art. 3",
                "descripcion": "Jornada ordinaria máxima de 44 horas semanales previa al escalón final",
            },
            {
                "codigo": "JORNADA_MAXIMA_SEMANAL",
                "clasificacion": "LEGAL",
                "version": 2,
                "fecha_inicio_vigencia": date(2026, 7, 15),
                "fecha_fin_vigencia": None,
                "parametros": {"horas_semanales": 42, "tope_extras_semanales": 12},
                "fuente_normativa": "Ley 2101 de 2021, Art. 3",
                "descripcion": "Jornada ordinaria máxima de 42 horas semanales a partir del 15-jul-2026",
            },
            # 2. Franja Nocturna (Ley 2466 de 2025)
            {
                "codigo": "FRANJA_NOCTURNA",
                "clasificacion": "LEGAL",
                "version": 1,
                "fecha_inicio_vigencia": date(2020, 1, 1),
                "fecha_fin_vigencia": date(2025, 12, 31),
                "parametros": {"hora_inicio": "21:00", "hora_fin": "06:00"},
                "fuente_normativa": "Código Sustantivo del Trabajo anterior",
                "descripcion": "Franja nocturna histórica de 21:00 a 06:00",
            },
            {
                "codigo": "FRANJA_NOCTURNA",
                "clasificacion": "LEGAL",
                "version": 2,
                "fecha_inicio_vigencia": date(2026, 1, 1),
                "fecha_fin_vigencia": None,
                "parametros": {"hora_inicio": "19:00", "hora_fin": "06:00"},
                "fuente_normativa": "Ley 2466 de 2025",
                "descripcion": "Franja nocturna reformada a partir de las 19:00",
            },
            # 3. Redondeo de Extras (Política Plastitec P4 / §4)
            {
                "codigo": "REDONDEO_HORAS_EXTRAS",
                "clasificacion": "CONFIG",
                "version": 1,
                "fecha_inicio_vigencia": date(2026, 1, 1),
                "fecha_fin_vigencia": None,
                "parametros": {
                    "puntos_corte_minutos": [25, 50],
                    "incremento_horas": 0.5,
                    "tolerancia_gracia_minutos": 5,
                },
                "fuente_normativa": "Política Interna Plastitec §4",
                "descripcion": "Redondeo a media hora con cortes en minuto :25 y :50 de reloj",
            },
            # 4. Descanso de Almuerzo y Café
            {
                "codigo": "TIEMPOS_DESCANSOS_TURNO",
                "clasificacion": "POLITICA",
                "version": 1,
                "fecha_inicio_vigencia": date(2026, 1, 1),
                "fecha_fin_vigencia": None,
                "parametros": {
                    "almuerzo_minutos": 60,
                    "almuerzo_descontable": True,
                    "cafe_minutos": 20,
                    "cafe_descontable": False,
                },
                "fuente_normativa": "Política Interna Plastitec §5",
                "descripcion": "Almuerzo de 60 min descontable si el turno lo habilita; café de 20 min no descontable",
            },
        ]

        creadas = []
        for r_dict in reglas_def:
            regla_existente = (
                db.query(ReglaLaboral)
                .filter(
                    ReglaLaboral.codigo == r_dict["codigo"],
                    ReglaLaboral.version == r_dict["version"],
                )
                .first()
            )
            if not regla_existente:
                nueva = ReglaLaboral(**r_dict)
                db.add(nueva)
                creadas.append(nueva)

        db.commit()

        if creadas:
            AuditService.registrar_evento(
                db=db,
                usuario_id=usuario_id,
                usuario_nombre="Sistema de Inicialización",
                rol="ADMIN",
                ip_origen="127.0.0.1",
                accion="SEMBRAR_REGLAS_LABORALES",
                entidad="sys_regla_laboral",
                entidad_id="ALL",
                motivo_justificacion="Siembra de reglas laborales legales y políticas versionadas (Fase 2)",
                valor_nuevo={"reglas_creadas": len(creadas)},
            )

        return creadas
