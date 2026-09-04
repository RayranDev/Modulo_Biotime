"""
Pruebas Unitarias del Motor de Cálculo y Pipeline de Etapas 3, 4, 5 y 6 (Fase 4).
Incluye los casos de prueba obligatorios:
- Redondeos :25 y :50
- Segmentación temporal atómica cruzando medianoche y frontera nocturna
- Umbral semanal de 42 horas para personal rotativo (Casos 7 y 8 del prompt maestro)
- Imputación estricta al día de inicio del turno
"""
import pytest
from datetime import date, time, datetime, timedelta
import uuid
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.turno import Turno, ProgramacionEmpleado
from src.domain.models.asistencia import MarcacionNormalizada
from src.domain.models.calculo import JornadaResuelta, SegmentoTemporal, ResultadoDiario
from src.services.motor_calculo import MotorCalculoService


def test_redondeo_horas_extras_puntos_corte_25_50():
    """Valida los puntos de corte obligatorios de la tabla del §4 de la especificación."""
    # Turno termina a las 17:00
    # 17:00 a 17:24 (24 min) -> 0.0 h
    assert MotorCalculoService.redondear_minutos_extra(24) == 0.0
    # 17:25 a 17:49 (25 a 49 min) -> 0.5 h
    assert MotorCalculoService.redondear_minutos_extra(25) == 0.5
    assert MotorCalculoService.redondear_minutos_extra(49) == 0.5
    # 17:50 a 18:24 (50 a 84 min) -> 1.0 h
    assert MotorCalculoService.redondear_minutos_extra(50) == 1.0
    assert MotorCalculoService.redondear_minutos_extra(84) == 1.0
    # 18:25 a 18:49 (85 a 109 min) -> 1.5 h
    assert MotorCalculoService.redondear_minutos_extra(85) == 1.5
    assert MotorCalculoService.redondear_minutos_extra(109) == 1.5
    # 18:50 a 19:24 (110 a 144 min) -> 2.0 h
    assert MotorCalculoService.redondear_minutos_extra(110) == 2.0
    assert MotorCalculoService.redondear_minutos_extra(144) == 2.0


def test_segmentacion_temporal_turno_noche_cruza_medianoche(db):
    """
    Un turno de 18:00 a 06:00 (12 horas) se parte atómicamente por:
    - 18:00 a 19:00: Diurno
    - 19:00 a 24:00: Nocturno del Día 1
    - 00:00 a 06:00: Nocturno del Día 2
    """
    cargo = Cargo(codigo="OP_TEST", nombre="Operario", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    emp = Empleado(sirh_emp_id="EMP-SEG-01", nombres="Carlos", apellidos="Ruiz", cargo_id=cargo.id)
    db.add(emp)
    db.commit()

    t_noche = Turno(codigo="T_12H_NOCHE_SEG", alias="12h Noche", hora_inicio=time(18, 0), duracion_minutos=720)
    db.add(t_noche)
    db.commit()

    fecha_turno = date(2026, 9, 4)
    ini_real = datetime(2026, 9, 4, 18, 0)
    fin_real = datetime(2026, 9, 5, 6, 0)

    jornada = JornadaResuelta(
        empleado_id=emp.id,
        fecha_imputacion=fecha_turno,
        turno_id=t_noche.id,
        inicio_programado=ini_real,
        fin_programado=fin_real,
        inicio_real=ini_real,
        fin_real=fin_real,
        minutos_trabajados_brutos=720,
        minutos_trabajados_netos=720,
        estado_jornada="COMPLETA",
        calculo_id=str(uuid.uuid4()),
    )
    db.add(jornada)
    db.commit()

    segmentos = MotorCalculoService.segmentar_jornada(
        db=db,
        jornada=jornada,
        hora_ini_nocturna=time(19, 0), # Franja nocturna vigente Ley 2466
    )

    # Debe producir exactamente 3 segmentos atómicos
    assert len(segmentos) == 3
    # Suma total exacta de minutos = 720 (12 horas)
    total_min = sum(s.duracion_minutos for s in segmentos)
    assert total_min == 720

    # Segmento 1: 18:00 a 19:00 (Diurno, 60 min)
    assert segmentos[0].inicio == datetime(2026, 9, 4, 18, 0)
    assert segmentos[0].fin == datetime(2026, 9, 4, 19, 0)
    assert segmentos[0].tipo_franja == "DIURNO"
    assert segmentos[0].duracion_minutos == 60

    # Segmento 2: 19:00 a 00:00 (Nocturno, 300 min)
    assert segmentos[1].inicio == datetime(2026, 9, 4, 19, 0)
    assert segmentos[1].fin == datetime(2026, 9, 5, 0, 0)
    assert segmentos[1].tipo_franja == "NOCTURNO"
    assert segmentos[1].duracion_minutos == 300

    # Segmento 3: 00:00 a 06:00 (Nocturno del día siguiente, 360 min)
    assert segmentos[2].inicio == datetime(2026, 9, 5, 0, 0)
    assert segmentos[2].fin == datetime(2026, 9, 5, 6, 0)
    assert segmentos[2].tipo_franja == "NOCTURNO"
    assert segmentos[2].duracion_minutos == 360


def test_umbral_42h_semana_rotativo_casos_7_y_8(db):
    """
    Caso 7 del prompt: Semana de rotativo que no alcanza 42 h (36 h en 3 días de 12h) -> 0 extras.
    Caso 8 del prompt: Semana de rotativo que supera 42 h (48 h en 4 días de 12h) -> 6 extras exactas.
    """
    cargo = Cargo(codigo="OP_ROT_42", nombre="Operario Rotativo", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    emp = Empleado(sirh_emp_id="EMP-ROT-42", nombres="Pedro", apellidos="Gómez", cargo_id=cargo.id)
    db.add(emp)
    db.commit()

    calc_id = str(uuid.uuid4())
    jornadas_semana = []

    # Crear 4 días de 12 horas en la misma semana (Lunes a Jueves de 06:00 a 18:00)
    lunes = date(2026, 8, 31)
    for i in range(4):
        f_dia = lunes + timedelta(days=i)
        ini_dt = datetime.combine(f_dia, time(6, 0))
        fin_dt = datetime.combine(f_dia, time(18, 0))

        j = JornadaResuelta(
            empleado_id=emp.id,
            fecha_imputacion=f_dia,
            inicio_programado=ini_dt,
            fin_programado=fin_dt,
            inicio_real=ini_dt,
            fin_real=fin_dt,
            minutos_trabajados_brutos=720,
            minutos_trabajados_netos=720, # 12.0 horas netas
            estado_jornada="COMPLETA",
            calculo_id=calc_id,
        )
        db.add(j)
        db.commit()

        # Segmentar
        MotorCalculoService.segmentar_jornada(db, j, hora_ini_nocturna=time(19, 0))
        jornadas_semana.append(j)

    # --- Test Caso 7: Evaluar solo los primeros 3 días (36 horas) ---
    res_3dias = MotorCalculoService.clasificar_semana_42h_rotativo(
        db=db,
        empleado_id=emp.id,
        jornadas_semana=jornadas_semana[:3], # 36 horas
        calculo_id=calc_id,
        umbral_semanal_horas=42.0,
    )
    # Ninguna hora extra generada
    extras_3dias = [r for r in res_3dias if r.concepto_dominio in ("0200", "0210", "0250", "0260")]
    assert len(extras_3dias) == 0, "No debe generar extras si la semana acumula menos de 42h"

    # --- Test Caso 8: Evaluar los 4 días completos (48 horas) ---
    calc_id_4dias = str(uuid.uuid4())
    res_4dias = MotorCalculoService.clasificar_semana_42h_rotativo(
        db=db,
        empleado_id=emp.id,
        jornadas_semana=jornadas_semana, # 48 horas acumuladas
        calculo_id=calc_id_4dias,
        umbral_semanal_horas=42.0,
    )

    # Debe generar exactamente 6.0 horas extras en concepto 0200 (diurna) en el 4to día
    extras_4dias = [r for r in res_4dias if r.concepto_dominio == "0200"]
    assert len(extras_4dias) == 1
    assert float(extras_4dias[0].cantidad_horas) == 6.0
    # Imputadas al 4to día (Jueves 2026-09-03)
    assert extras_4dias[0].fecha_imputacion == date(2026, 9, 3)
