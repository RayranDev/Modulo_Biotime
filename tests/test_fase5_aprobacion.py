"""
Pruebas Unitarias para Fase 5: Aprobación Continua por Jefe Inmediato y Condiciones Especiales.
Incluye:
- Caso 19: Lactancia (Turno de 8h, trabaja 7h, se calculan 8h)
- Aprobación por excepción en bloque
- Ajuste con justificación obligatoria y trazabilidad
- Aprobación sustituta por RRHH con anotación obligatoria
"""
import pytest
from datetime import date, time, datetime, timedelta
import uuid
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.turno import Turno, ProgramacionEmpleado
from src.domain.models.asistencia import MarcacionNormalizada
from src.domain.models.novedad import CondicionEspecialEmpleado
from src.domain.models.calculo import ResultadoDiario
from src.domain.models.auditoria import AuditoriaEvento
from src.services.motor_calculo import MotorCalculoService
from src.services.aprobacion_service import AprobacionService


def test_lactancia_compensacion_caso_19(db):
    """Caso 19: Turno de 8h, trabaja 7h, se calculan 8h por beneficio de lactancia vigente."""
    cargo = Cargo(codigo="OP_ENVASE", nombre="Operaria de Envase", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    emp = Empleado(sirh_emp_id="EMP-LACT-01", nombres="María", apellidos="López", cargo_id=cargo.id)
    db.add(emp)
    db.commit()

    # Turno de 8 horas (07:30 a 15:30)
    t_8h = Turno(codigo="T_8H_DIA", alias="Turno 8h", hora_inicio=time(7, 30), duracion_minutos=480, descuenta_almuerzo=False)
    db.add(t_8h)
    db.commit()

    fecha_eval = date(2026, 9, 4)
    # Programación del empleado
    prog = ProgramacionEmpleado(
        empleado_id=emp.id,
        fecha_inicio=date(2026, 9, 1),
        fecha_fin=date(2026, 9, 30),
        turno_fijo_id=t_8h.id,
    )
    db.add(prog)

    # Condición de Lactancia activa para esa fecha (60 min diarios reconocidos)
    lactancia = CondicionEspecialEmpleado(
        empleado_id=emp.id,
        tipo_condicion="LACTANCIA",
        fecha_inicio=date(2026, 8, 1),
        fecha_fin=date(2027, 2, 1), # 6 meses
        minutos_reconocidos_dia=60,
        es_activa=True,
        motivo_soporte="Certificado médico de nacimiento y periodo de lactancia",
    )
    db.add(lactancia)

    # Marcaciones: Entra 07:30 y sale a las 14:30 (7 horas trabajadas = 420 minutos)
    m_in = MarcacionNormalizada(
        empleado_id=emp.id,
        timestamp_efectivo=datetime(2026, 9, 4, 7, 30),
        tipo_evento="ENTRADA",
    )
    m_out = MarcacionNormalizada(
        empleado_id=emp.id,
        timestamp_efectivo=datetime(2026, 9, 4, 14, 30),
        tipo_evento="SALIDA",
    )
    db.add_all([m_in, m_out])
    db.commit()

    calc_id = str(uuid.uuid4())
    jornada = MotorCalculoService.resolver_jornada_empleado_dia(
        db=db,
        empleado_id=emp.id,
        fecha_imputacion=fecha_eval,
        calculo_id=calc_id,
    )

    assert jornada is not None
    # Minutos brutos trabajados = 420 (7 horas)
    assert jornada.minutos_trabajados_brutos == 420
    # Con la compensación de lactancia (60 min), los minutos netos computados son exactamente 480 (8.0 horas)
    assert jornada.minutos_trabajados_netos == 480


def test_aprobacion_en_bloque_supervisor(db):
    """Supervisor aprueba en bloque jornadas pendientes."""
    emp = Empleado(sirh_emp_id="EMP-APR-01", nombres="Andrés", apellidos="Pardo", cargo_id=1)
    db.add(emp)
    db.commit()

    r1 = ResultadoDiario(empleado_id=emp.id, fecha_imputacion=date(2026, 9, 1), concepto_dominio="ORDINARIA", cantidad_horas=8.0, estado_aprobacion="PENDIENTE", calculo_id="CALC-1")
    r2 = ResultadoDiario(empleado_id=emp.id, fecha_imputacion=date(2026, 9, 2), concepto_dominio="ORDINARIA", cantidad_horas=8.0, estado_aprobacion="PENDIENTE", calculo_id="CALC-1")
    db.add_all([r1, r2])
    db.commit()

    total_aprobados = AprobacionService.aprobar_en_bloque(
        db=db,
        resultado_ids=[r1.id, r2.id],
        usuario_id="SUP_PLANTA_01",
        usuario_nombre="Carlos Supervisor",
        rol="SUPERVISOR",
    )

    assert total_aprobados == 2
    assert r1.estado_aprobacion == "APROBADO"
    assert r2.estado_aprobacion == "APROBADO"
    assert r1.supervisor_id == "SUP_PLANTA_01"


def test_ajuste_horas_justificacion_obligatoria(db):
    """Un ajuste manual sin justificación debe ser rechazado inmediatamente por auditoría."""
    emp = Empleado(sirh_emp_id="EMP-AJU-01", nombres="Laura", apellidos="Mejía", cargo_id=1)
    db.add(emp)
    db.commit()

    res = ResultadoDiario(empleado_id=emp.id, fecha_imputacion=date(2026, 9, 3), concepto_dominio="0200", cantidad_horas=2.0, estado_aprobacion="PENDIENTE", calculo_id="CALC-2")
    db.add(res)
    db.commit()

    # Intento de ajuste sin justificación (falla)
    with pytest.raises(ValueError, match="El ajuste manual de horas exige una justificación obligatoria"):
        AprobacionService.ajustar_resultado(
            db=db,
            resultado_id=res.id,
            nuevas_horas=3.0,
            motivo_justificacion="", # Vacío
            usuario_id="SUP_01",
            usuario_nombre="Supervisor",
            rol="SUPERVISOR",
        )

    # Ajuste con justificación válida
    ajustado = AprobacionService.ajustar_resultado(
        db=db,
        resultado_id=res.id,
        nuevas_horas=2.5,
        motivo_justificacion="Empleado se quedó 30 minutos adicionales para entrega de turno a solicitud de producción",
        usuario_id="SUP_01",
        usuario_nombre="Supervisor",
        rol="SUPERVISOR",
    )

    assert ajustado.estado_aprobacion == "AJUSTADO"
    assert float(ajustado.cantidad_horas) == 2.5
    assert float(ajustado.ajuste_horas) == 2.5


def test_aprobacion_sustituta_rrhh_exige_anotacion(db):
    """RRHH aprobando por el supervisor exige anotación obligatoria como vía de escape auditada."""
    emp = Empleado(sirh_emp_id="EMP-RRHH-01", nombres="Diego", apellidos="Sanz", cargo_id=1)
    db.add(emp)
    db.commit()

    r = ResultadoDiario(empleado_id=emp.id, fecha_imputacion=date(2026, 9, 4), concepto_dominio="ORDINARIA", cantidad_horas=12.0, estado_aprobacion="PENDIENTE", calculo_id="CALC-3")
    db.add(r)
    db.commit()

    # Falla sin anotación
    with pytest.raises(ValueError, match="La aprobación sustituta por RRHH exige una anotación obligatoria"):
        AprobacionService.aprobar_en_bloque(
            db=db,
            resultado_ids=[r.id],
            usuario_id="RRHH_ANALISTA",
            usuario_nombre="Analista RRHH",
            rol="RRHH",
            es_sustitucion_rrhh=True,
            anotacion="", # Vacío
        )

    # Con anotación de escape
    ok_count = AprobacionService.aprobar_en_bloque(
        db=db,
        resultado_ids=[r.id],
        usuario_id="RRHH_ANALISTA",
        usuario_nombre="Analista RRHH",
        rol="RRHH",
        es_sustitucion_rrhh=True,
        anotacion="Aprobación por cierre de ciclo mensual: supervisor se encuentra en descanso compensatorio",
    )
    assert ok_count == 1
    assert r.estado_aprobacion == "APROBADO"
