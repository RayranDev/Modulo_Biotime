"""
Motor de Cálculo de Asistencia y Tiempos SIRH Plastitec.
Pipeline de 6 etapas:
- Etapa 3: Jornada Resuelta y cruce contra programación
- Etapa 4: Segmentación Temporal Atómica
- Etapa 5: Clasificación en 3 Pasadas (Diaria, Semanal 42h, Mensual Habitual)
- Etapa 6: Agregación para Aprobación
"""
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
import uuid
from sqlalchemy.orm import Session
from src.domain.models.identidad import Empleado, Cargo
from src.domain.models.turno import Turno, ProgramacionEmpleado
from src.domain.models.asistencia import MarcacionNormalizada
from src.domain.models.calculo import (
    JornadaResuelta,
    SegmentoTemporal,
    ClasificacionSegmento,
    ResultadoDiario,
)
from src.domain.models.regla import ReglaLaboral
from src.core.audit import AuditService


class MotorCalculoService:
    @staticmethod
    def redondear_minutos_extra(minutos: int) -> float:
        """
        Regla P4 / §4: Redondeo de horas extras con cortes en :25 y :50.
        Incrementos de 0.5 h con 5 min de gracia.
        - 0 a 24 min -> 0.0 h
        - 25 a 49 min -> 0.5 h
        - 50 a 84 min -> 1.0 h
        - 85 a 109 min -> 1.5 h
        - 110 a 144 min -> 2.0 h
        """
        if minutos < 25:
            return 0.0
        horas_enteras = minutos // 60
        resto = minutos % 60
        if resto < 25:
            return float(horas_enteras)
        elif resto < 50:
            return float(horas_enteras) + 0.5
        else:
            return float(horas_enteras) + 1.0

    @classmethod
    def obtener_hora_nocturna_inicio(cls, db: Session, fecha_eval: date) -> time:
        """Obtiene la hora de inicio de la franja nocturna según las reglas vigentes a esa fecha."""
        reglas = db.query(ReglaLaboral).filter(ReglaLaboral.codigo == "FRANJA_NOCTURNA").all()
        for r in reglas:
            if r.es_vigente_en(fecha_eval):
                h_str = r.parametros.get("hora_inicio", "19:00")
                partes = [int(p) for p in h_str.split(":")[:2]]
                return time(partes[0], partes[1])
        # Fallback histórico: si es 2026+ es 19:00, sino 21:00
        return time(19, 0) if fecha_eval >= date(2026, 1, 1) else time(21, 0)

    @classmethod
    def es_franja_nocturna(cls, dt: datetime, hora_ini_nocturna: time) -> bool:
        """Determina si un timestamp cae en horario nocturno (ej. 19:00 a 06:00)."""
        t = dt.time()
        if hora_ini_nocturna >= time(12, 0): # ej. 19:00 o 21:00
            return t >= hora_ini_nocturna or t < time(6, 0)
        return time(6, 0) > t >= hora_ini_nocturna

    @classmethod
    def resolver_jornada_empleado_dia(
        cls,
        db: Session,
        empleado_id: int,
        fecha_imputacion: date,
        calculo_id: str,
    ) -> Optional[JornadaResuelta]:
        """
        Etapa 3: Busca marcaciones del empleado para el día de imputación y las cruza
        con su turno programado. Imputa al DÍA DE INICIO del turno.
        """
        emp = db.query(Empleado).filter(Empleado.id == empleado_id).first()
        if not emp:
            return None

        # 1. Obtener turno programado para la fecha
        prog = (
            db.query(ProgramacionEmpleado)
            .filter(
                ProgramacionEmpleado.empleado_id == empleado_id,
                ProgramacionEmpleado.fecha_inicio <= fecha_imputacion,
                ProgramacionEmpleado.fecha_fin >= fecha_imputacion,
            )
            .first()
        )
        turno: Optional[Turno] = None
        if prog:
            if prog.turno_fijo:
                turno = prog.turno_fijo
            elif prog.ciclo and prog.ciclo.dias:
                # Calcular día dentro del ciclo
                dias_transcurridos = (fecha_imputacion - prog.fecha_inicio).days
                idx_dia = ((prog.dia_inicio_ciclo - 1 + dias_transcurridos) % prog.ciclo.duracion_dias) + 1
                detalle = [d for d in prog.ciclo.dias if d.dia_indice == idx_dia]
                if detalle and detalle[0].turno:
                    turno = detalle[0].turno

        # Ventana de búsqueda de marcaciones: desde fecha_imputacion 00:00 hasta fecha_imputacion + 36h
        # para atrapar salidas de turnos que cruzan medianoche
        dt_inicio_busqueda = datetime.combine(fecha_imputacion, time(0, 0))
        dt_fin_busqueda = dt_inicio_busqueda + timedelta(hours=36)

        marcaciones = (
            db.query(MarcacionNormalizada)
            .filter(
                MarcacionNormalizada.empleado_id == empleado_id,
                MarcacionNormalizada.timestamp_efectivo >= dt_inicio_busqueda,
                MarcacionNormalizada.timestamp_efectivo <= dt_fin_busqueda,
                MarcacionNormalizada.es_duplicada == False,
            )
            .order_by(MarcacionNormalizada.timestamp_efectivo.asc())
            .all()
        )

        if not marcaciones and not turno:
            return None

        inicio_real = marcaciones[0].timestamp_efectivo if marcaciones else None
        fin_real = marcaciones[-1].timestamp_efectivo if len(marcaciones) > 1 else inicio_real

        inicio_prog = None
        fin_prog = None
        minutos_almuerzo = 0
        descuenta_almuerzo = False

        if turno:
            inicio_prog = datetime.combine(fecha_imputacion, turno.hora_inicio)
            fin_prog = inicio_prog + timedelta(minutes=turno.duracion_minutos)
            descuenta_almuerzo = turno.descuenta_almuerzo
            if descuenta_almuerzo:
                minutos_almuerzo = turno.minutos_almuerzo

        minutos_brutos = 0
        if inicio_real and fin_real and fin_real > inicio_real:
            minutos_brutos = int((fin_real - inicio_real).total_seconds() // 60)

        minutos_netos = max(0, minutos_brutos - minutos_almuerzo)

        # Requerimiento P2 / Caso 19: Lactancia como condición especial vigente
        from src.domain.models.novedad import CondicionEspecialEmpleado
        cond_lactancia = (
            db.query(CondicionEspecialEmpleado)
            .filter(
                CondicionEspecialEmpleado.empleado_id == empleado_id,
                CondicionEspecialEmpleado.tipo_condicion == "LACTANCIA",
                CondicionEspecialEmpleado.es_activa == True,
                CondicionEspecialEmpleado.fecha_inicio <= fecha_imputacion,
                CondicionEspecialEmpleado.fecha_fin >= fecha_imputacion,
            )
            .first()
        )
        if cond_lactancia and turno and minutos_netos > 0:
            minutos_netos = min(turno.duracion_minutos, minutos_netos + cond_lactancia.minutos_reconocidos_dia)

        if inicio_real and fin_real and inicio_real != fin_real:
            estado = "COMPLETA"
        elif inicio_real and (not fin_real or fin_real == inicio_real):
            estado = "SIN_SALIDA"
        else:
            estado = "SIN_ENTRADA"

        # Calcular horas extra tentativas redondeadas sobre el exceso del turno
        minutos_extra_brutos = 0
        if turno and fin_real and fin_prog and fin_real > fin_prog:
            minutos_extra_brutos = int((fin_real - fin_prog).total_seconds() // 60)

        horas_extra_redondeadas = cls.redondear_minutos_extra(minutos_extra_brutos)

        jornada = JornadaResuelta(
            empleado_id=empleado_id,
            fecha_imputacion=fecha_imputacion,
            turno_id=turno.id if turno else None,
            inicio_programado=inicio_prog,
            fin_programado=fin_prog,
            inicio_real=inicio_real,
            fin_real=fin_real,
            minutos_trabajados_brutos=minutos_brutos,
            minutos_descuento_almuerzo=minutos_almuerzo,
            minutos_trabajados_netos=minutos_netos,
            horas_extra_redondeadas=horas_extra_redondeadas,
            estado_jornada=estado,
            calculo_id=calculo_id,
        )
        db.add(jornada)
        db.flush()
        return jornada

    @classmethod
    def segmentar_jornada(
        cls,
        db: Session,
        jornada: JornadaResuelta,
        hora_ini_nocturna: time,
        festivos_set: Optional[Set[date]] = None,
    ) -> List[SegmentoTemporal]:
        """
        Etapa 4: Segmentación Temporal Atómica.
        Parte el tiempo efectivamente trabajado entre inicio_real y fin_real
        por medianoche, frontera nocturna y límites programados.
        """
        if not jornada.inicio_real or not jornada.fin_real or jornada.inicio_real >= jornada.fin_real:
            return []

        festivos = festivos_set or set()
        pivotes: Set[datetime] = {jornada.inicio_real, jornada.fin_real}

        if jornada.inicio_programado and jornada.inicio_real < jornada.inicio_programado < jornada.fin_real:
            pivotes.add(jornada.inicio_programado)
        if jornada.fin_programado and jornada.inicio_real < jornada.fin_programado < jornada.fin_real:
            pivotes.add(jornada.fin_programado)

        # Generar cortes por medianoche y fronteras nocturnas (06:00 y hora_ini_nocturna)
        curr_dia = jornada.inicio_real.date()
        dia_final = jornada.fin_real.date()
        while curr_dia <= dia_final + timedelta(days=1):
            c_med = datetime.combine(curr_dia, time(0, 0))
            c_06 = datetime.combine(curr_dia, time(6, 0))
            c_noc = datetime.combine(curr_dia, hora_ini_nocturna)

            for c in (c_med, c_06, c_noc):
                if jornada.inicio_real < c < jornada.fin_real:
                    pivotes.add(c)
            curr_dia += timedelta(days=1)

        sorted_pivotes = sorted(pivotes)
        segmentos: List[SegmentoTemporal] = []

        for i in range(len(sorted_pivotes) - 1):
            t_ini = sorted_pivotes[i]
            t_fin = sorted_pivotes[i + 1]
            dur_min = int((t_fin - t_ini).total_seconds() // 60)
            if dur_min <= 0:
                continue

            # Punto medio para evaluar franja y tipo de día
            mid_point = t_ini + (t_fin - t_ini) / 2
            es_noc = cls.es_franja_nocturna(mid_point, hora_ini_nocturna)
            tipo_franja = "NOCTURNO" if es_noc else "DIURNO"

            # Tipo de día
            dia_mid = mid_point.date()
            if dia_mid in festivos:
                tipo_dia = "FESTIVO"
            elif mid_point.weekday() == 6: # Domingo
                tipo_dia = "DOMINICAL"
            else:
                tipo_dia = "ORDINARIO"

            # Dentro o fuera de jornada programada
            es_dentro = False
            if jornada.inicio_programado and jornada.fin_programado:
                es_dentro = (jornada.inicio_programado <= mid_point <= jornada.fin_programado)

            seg = SegmentoTemporal(
                jornada_id=jornada.id,
                inicio=t_ini,
                fin=t_fin,
                duracion_minutos=dur_min,
                tipo_franja=tipo_franja,
                tipo_dia=tipo_dia,
                es_dentro_jornada=es_dentro,
            )
            db.add(seg)
            segmentos.append(seg)

        db.flush()
        return segmentos

    @classmethod
    def clasificar_semana_42h_rotativo(
        cls,
        db: Session,
        empleado_id: int,
        jornadas_semana: List[JornadaResuelta],
        calculo_id: str,
        umbral_semanal_horas: float = 42.0,
    ) -> List[ResultadoDiario]:
        """
        Etapa 5 (Pasada 2): UMBRAL SEMANAL DE 42 HORAS (P1).
        Para personal rotativo, las primeras 42h acumuladas de lunes a domingo
        son ordinarias (con recargos si aplica). A partir de la hora 42.0,
        el excedente se reclasifica a HORAS EXTRAS.
        """
        resultados: List[ResultadoDiario] = []
        acumulado_horas = 0.0

        for jornada in sorted(jornadas_semana, key=lambda j: j.fecha_imputacion):
            horas_jornada = jornada.minutos_trabajados_netos / 60.0
            if horas_jornada <= 0:
                continue

            # Evaluar segmentos de la jornada
            for seg in jornada.segmentos:
                seg_horas = seg.duracion_minutos / 60.0
                horas_previas = acumulado_horas
                acumulado_horas += seg_horas

                # Determinar si el segmento cae dentro de las 42h o por encima
                if acumulado_horas <= umbral_semanal_horas:
                    # 100% dentro de las 42h: Horas Ordinarias
                    concepto = "ORDINARIA"
                    if seg.tipo_dia in ("DOMINICAL", "FESTIVO"):
                        # Recargo dominical / festivo (0252/0253)
                        cls._agregar_resultado(resultados, empleado_id, jornada.fecha_imputacion, "0252", seg_horas, calculo_id)
                    if seg.tipo_franja == "NOCTURNO":
                        # Recargo nocturno ordinario (0220)
                        cls._agregar_resultado(resultados, empleado_id, jornada.fecha_imputacion, "0220", seg_horas, calculo_id)

                    cls._crear_clasificacion(db, seg.id, calculo_id, concepto, seg_horas, pasada=1)

                elif horas_previas < umbral_semanal_horas < acumulado_horas:
                    # Segmento fronterizo: parte ordinario, parte extra
                    horas_ord = umbral_semanal_horas - horas_previas
                    horas_extra = acumulado_horas - umbral_semanal_horas

                    # Parte ordinaria
                    if seg.tipo_franja == "NOCTURNO":
                        cls._agregar_resultado(resultados, empleado_id, jornada.fecha_imputacion, "0220", horas_ord, calculo_id)
                    cls._crear_clasificacion(db, seg.id, calculo_id, "ORDINARIA", horas_ord, pasada=1)

                    # Parte extra por encima de 42h (Reclasificada en Pasada 2)
                    concepto_extra = cls._resolver_concepto_extra(seg.tipo_franja, seg.tipo_dia)
                    cls._agregar_resultado(resultados, empleado_id, jornada.fecha_imputacion, concepto_extra, horas_extra, calculo_id)
                    cls._crear_clasificacion(db, seg.id, calculo_id, concepto_extra, horas_extra, pasada=2)

                else:
                    # 100% por encima de las 42h acumuladas: Extra directa
                    concepto_extra = cls._resolver_concepto_extra(seg.tipo_franja, seg.tipo_dia)
                    cls._agregar_resultado(resultados, empleado_id, jornada.fecha_imputacion, concepto_extra, seg_horas, calculo_id)
                    cls._crear_clasificacion(db, seg.id, calculo_id, concepto_extra, seg_horas, pasada=2)

        # Persistir resultados en DB
        for r in resultados:
            db.add(r)
        db.commit()
        return resultados

    @staticmethod
    def _resolver_concepto_extra(tipo_franja: str, tipo_dia: str) -> str:
        """Mapea franja y tipo de día al código de concepto de nómina."""
        if tipo_dia in ("DOMINICAL", "FESTIVO"):
            return "0260" if tipo_franja == "NOCTURNO" else "0250" # Extra festiva nocturna / diurna
        return "0210" if tipo_franja == "NOCTURNO" else "0200"     # Extra ordinaria nocturna / diurna

    @staticmethod
    def _crear_clasificacion(db: Session, seg_id: int, calc_id: str, concepto: str, horas: float, pasada: int):
        c = ClasificacionSegmento(
            segmento_id=seg_id,
            calculo_id=calc_id,
            concepto_dominio=concepto,
            horas=round(horas, 2),
            pasada=pasada,
        )
        db.add(c)

    @staticmethod
    def _agregar_resultado(
        resultados: List[ResultadoDiario],
        empleado_id: int,
        fecha: date,
        concepto: str,
        horas: float,
        calculo_id: str,
    ):
        # Buscar si ya existe para acumular
        horas_red = round(horas, 2)
        if horas_red <= 0:
            return
        for r in resultados:
            if r.empleado_id == empleado_id and r.fecha_imputacion == fecha and r.concepto_dominio == concepto:
                r.cantidad_horas = float(r.cantidad_horas) + horas_red
                return
        res = ResultadoDiario(
            empleado_id=empleado_id,
            fecha_imputacion=fecha,
            concepto_dominio=concepto,
            cantidad_horas=horas_red,
            estado_aprobacion="PENDIENTE",
            calculo_id=calculo_id,
        )
        resultados.append(res)
