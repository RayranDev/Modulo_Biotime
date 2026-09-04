"""
Pruebas Unitarias para Fase 6: Ciclos 11→10, Bloqueo de RRHH y Exportación Sinergy.
Incluye:
- Caso 25: Resolución de código por fecha (0252/0258 vs 0253/0259 a partir del 15-jul-2026)
- Formato estricto de 12 campos delimitados por TAB con campos 7-12 vacíos
- Máquina de estados de períodos y bloqueo para supervisores
- Auditoría y firma SHA-256 del archivo plano
- Control de reapertura
"""
import pytest
from datetime import date, datetime
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.calculo import ResultadoDiario
from src.domain.models.periodo import PeriodoNomina, ExportacionSinergy
from src.adapters.sinergy.exporter import SinergyExporterAdapter
from src.services.periodo_service import PeriodoService


def test_fechas_ciclo_11_a_10():
    """Valida la generación de rangos para el ciclo de variables 11 al 10."""
    # Septiembre 2026 -> 11 de agosto a 10 de septiembre
    f_ini_sep, f_fin_sep = PeriodoService.calcular_fechas_ciclo(2026, 9)
    assert f_ini_sep == date(2026, 8, 11)
    assert f_fin_sep == date(2026, 9, 10)

    # Enero 2027 -> 11 de diciembre 2026 a 10 de enero 2027
    f_ini_ene, f_fin_ene = PeriodoService.calcular_fechas_ciclo(2027, 1)
    assert f_ini_ene == date(2026, 12, 11)
    assert f_fin_ene == date(2027, 1, 10)


def test_caso_25_resolucion_codigo_sinergy_segun_fecha():
    """
    Caso 25 del prompt maestro / §10.2:
    - Período antes del 15-jul-2026 -> Códigos 0253 y 0259
    - Período desde el 15-jul-2026 -> Códigos 0252 y 0258
    """
    fecha_pre_reforma = date(2026, 6, 10)
    fecha_post_reforma = date(2026, 9, 10)

    # Recargo dominical / festivo
    cod_pre = SinergyExporterAdapter.resolver_codigo_concepto("RECARGO_DOMINICAL_FESTIVO", fecha_pre_reforma)
    assert cod_pre == "0253"

    cod_post = SinergyExporterAdapter.resolver_codigo_concepto("RECARGO_DOMINICAL_FESTIVO", fecha_post_reforma)
    assert cod_post == "0252" # Caso 25 estricto

    # Recargo nocturno festivo
    cod_noc_pre = SinergyExporterAdapter.resolver_codigo_concepto("RECARGO_NOCTURNO_FESTIVO", fecha_pre_reforma)
    assert cod_noc_pre == "0259"

    cod_noc_post = SinergyExporterAdapter.resolver_codigo_concepto("RECARGO_NOCTURNO_FESTIVO", fecha_post_reforma)
    assert cod_noc_post == "0258" # Caso 25 estricto


def test_formato_archivo_plano_12_campos():
    """Valida los 12 campos exactos delimitados por TAB, fecha D/MM/YYYY y campos 7-12 vacíos."""
    linea = SinergyExporterAdapter.generar_linea_plano(
        sinergy_emp_code="8639",
        concepto_codigo="0200",
        fecha_inicio=date(2026, 9, 11),
        fecha_fin=date(2026, 10, 10),
        cantidad_horas=6.5,
    )

    columnas = linea.split("\t")
    # Exactamente 12 campos
    assert len(columnas) == 12
    assert columnas[0] == "8639"
    assert columnas[1] == "0200"
    assert columnas[2] == "+"
    assert columnas[3] == "11/09/2026"
    assert columnas[4] == "6.5"
    assert columnas[5] == "10/10/2026"
    # Campos 7 a 12 deben ser strings vacíos intencionales
    for col_idx in range(6, 12):
        assert columnas[col_idx] == ""


def test_ciclo_completo_periodo_bloqueo_y_exportacion(db):
    """Prueba integral de apertura, bloqueo de RRHH, cierre y exportación con firma SHA-256."""
    # 1. Crear Empleado y mapeo
    cargo = Cargo(codigo="OP_SINER", nombre="Operario", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    emp = Empleado(sirh_emp_id="EMP-SIN-01", nombres="Mario", apellidos="Ríos", cargo_id=cargo.id)
    db.add(emp)
    db.commit()

    mapeo = MapeoIdentidad(
        empleado_id=emp.id,
        sirh_emp_id=emp.sirh_emp_id,
        biotime_emp_id=3001,
        biotime_emp_code="7500",
        sinergy_emp_code="8639",
        tipo_vinculacion="DIRECTO",
    )
    db.add(mapeo)
    db.commit()

    # 2. Abrir período de septiembre 2026 (11/08/2026 a 10/09/2026)
    periodo = PeriodoService.obtener_o_crear_periodo(db, 2026, 9)
    assert periodo.estado == "ABIERTO"
    assert periodo.esta_bloqueado_para_supervisores() is False

    # 3. Crear resultados aprobados en el período
    r1 = ResultadoDiario(
        empleado_id=emp.id,
        fecha_imputacion=date(2026, 8, 20),
        concepto_dominio="EXTRA_DIURNA_ORD",
        cantidad_horas=4.0,
        estado_aprobacion="APROBADO",
        calculo_id="CALC-EXP-1",
    )
    r2 = ResultadoDiario(
        empleado_id=emp.id,
        fecha_imputacion=date(2026, 8, 21),
        concepto_dominio="RECARGO_DOMINICAL_FESTIVO",
        cantidad_horas=8.0,
        estado_aprobacion="APROBADO",
        calculo_id="CALC-EXP-1",
    )
    db.add_all([r1, r2])
    db.commit()

    # 4. Día 11: RRHH inicia procesamiento y bloquea a supervisores
    PeriodoService.iniciar_procesamiento_rrhh(
        db=db,
        periodo_id=periodo.id,
        usuario_id="ANALISTA_RRHH",
        usuario_nombre="Ana RRHH",
    )
    assert periodo.estado == "EN_PROCESAMIENTO"
    assert periodo.esta_bloqueado_para_supervisores() is True

    # 5. Cerrar período y exportar a Sinergy
    exp = PeriodoService.cerrar_y_exportar_sinergy(
        db=db,
        periodo_id=periodo.id,
        usuario_id="ANALISTA_RRHH",
        usuario_nombre="Ana RRHH",
    )

    assert periodo.estado == "CERRADO"
    assert exp.nombre_archivo == "FINAL_SINER_2026-08-11_2026-09-10.txt"
    assert len(exp.hash_sha256) == 64
    assert exp.total_horas == 12.0
    assert "8639\t0200\t+\t11/08/2026\t4\t10/09/2026\t\t\t\t\t\t" in exp.contenido_txt
    assert "8639\t0252\t+\t11/08/2026\t8\t10/09/2026\t\t\t\t\t\t" in exp.contenido_txt # Caso 25: 0252


def test_reapertura_periodo_seguridad(db):
    """La reapertura requiere rol elevado y justificación obligatoria."""
    periodo = PeriodoService.obtener_o_crear_periodo(db, 2026, 8)
    periodo.estado = "CERRADO"
    db.commit()

    # Intento por supervisor (rechazado)
    with pytest.raises(PermissionError, match="Solo un usuario con rol 'ADMIN' o 'RRHH_DIR'"):
        PeriodoService.reabrir_periodo(
            db=db,
            periodo_id=periodo.id,
            motivo_justificacion="Corregir error",
            usuario_id="SUP_01",
            usuario_nombre="Supervisor",
            rol="SUPERVISOR",
        )

    # Intento por Admin sin motivo (rechazado)
    with pytest.raises(ValueError, match="exige un motivo/justificación formal obligatoria"):
        PeriodoService.reabrir_periodo(
            db=db,
            periodo_id=periodo.id,
            motivo_justificacion="",
            usuario_id="GERENTE_RRHH",
            usuario_nombre="Gerente",
            rol="ADMIN",
        )

    # Reapertura válida
    p_reabierto = PeriodoService.reabrir_periodo(
        db=db,
        periodo_id=periodo.id,
        motivo_justificacion="Ajuste ordenado por Dirección General para incluir horas de mantenimiento extraordinario",
        usuario_id="GERENTE_RRHH",
        usuario_nombre="Gerente",
        rol="ADMIN",
    )
    assert p_reabierto.estado == "REABIERTO"
