"""
Pruebas Unitarias e Integración para Fase 2: Núcleo, Identidad, Turnos y Auditoría.
"""
import pytest
from datetime import date, time, datetime, timedelta
from src.core.database import SessionLocal, Base, engine
from src.core.audit import AuditService
from src.domain.models.auditoria import AuditoriaEvento
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.turno import Turno, CicloRotativo, CicloDetalleDia
from src.domain.models.regla import ReglaLaboral
from src.services.catalogo_service import CatalogoService






def test_auditoria_inmutable_exige_motivo(db):
    """La auditoría debe rechazar cualquier acción sin justificación obligatoria."""
    with pytest.raises(ValueError, match="El motivo/justificación es obligatorio"):
        AuditService.registrar_evento(
            db=db,
            usuario_id="TEST_USER",
            usuario_nombre="Tester",
            rol="SUPERVISOR",
            ip_origen="127.0.0.1",
            accion="AJUSTAR",
            entidad="jornada",
            entidad_id="1",
            motivo_justificacion="",  # Vacío deliberado
        )


def test_auditoria_genera_firma_sha256(db):
    """Un evento de auditoría válido debe generar un hash SHA-256 no vacío de 64 caracteres."""
    evento = AuditService.registrar_evento(
        db=db,
        usuario_id="SUPERVISOR_01",
        usuario_nombre="Carlos Supervisor",
        rol="SUPERVISOR",
        ip_origen="192.168.1.50",
        accion="APROBAR",
        entidad="jornada_resuelta",
        entidad_id="101",
        motivo_justificacion="Aprobación normal de jornada sin novedades",
        valor_nuevo={"horas": 12.0},
    )
    assert evento.id is not None
    assert len(evento.signature_hash) == 64
    assert evento.usuario_id == "SUPERVISOR_01"


def test_mapeo_identidad_multisistema(db):
    """Valida la tabla explícita de correspondencia multi-sistema."""
    # 1. Crear Cargo con perfil rotativo
    cargo = Cargo(codigo="OP_INYECCION", nombre="Operario de Inyección", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    # 2. Crear Empleado
    emp = Empleado(
        sirh_emp_id="SIRH-1001",
        nombres="Juan",
        apellidos="Pérez",
        cargo_id=cargo.id,
        fecha_ingreso=date(2024, 1, 15),
    )
    db.add(emp)
    db.commit()

    # 3. Mapeo Explícito multi-sistema
    mapeo = MapeoIdentidad(
        empleado_id=emp.id,
        sirh_emp_id=emp.sirh_emp_id,
        biotime_emp_id=1281,
        biotime_emp_code="7334",
        sinergy_emp_code="8639",
        tipo_vinculacion="DIRECTO",
    )
    db.add(mapeo)
    db.commit()

    assert mapeo.biotime_emp_code == "7334"
    assert mapeo.sinergy_emp_code == "8639"
    assert emp.cargo.perfil_laboral == "ROTATIVO"


def test_turno_proyeccion_fecha_cruza_medianoche():
    """Un turno 18:00 de 12 horas debe terminar a las 06:00 del día SIGUIENTE sin perder el día."""
    turno = Turno(
        codigo="T_12H_NOCHE",
        alias="Turno 12h Noche",
        hora_inicio=time(18, 0),
        duracion_minutos=720,
        es_rotativo=True,
    )
    fecha_inicio = date(2026, 9, 4)
    fin_proyectado = turno.calcular_fin_proyectado(fecha_inicio)

    assert fin_proyectado == datetime(2026, 9, 5, 6, 0)
    assert fin_proyectado.date() == date(2026, 9, 5)


def test_ciclo_rotativo_4x3(db):
    """Valida la estructura de un ciclo 4x3 de 7 días."""
    t_dia = Turno(codigo="T_12H_DIA_TEST", alias="12h Día", hora_inicio=time(6, 0), duracion_minutos=720)
    t_noche = Turno(codigo="T_12H_NOCHE_TEST", alias="12h Noche", hora_inicio=time(18, 0), duracion_minutos=720)
    db.add_all([t_dia, t_noche])
    db.commit()

    ciclo = CicloRotativo(codigo="CICLO_TEST_4X3", nombre="Ciclo Rotativo 4x3 Planta", duracion_dias=7)
    db.add(ciclo)
    db.commit()

    # Días 1 y 2: Día, Días 3 y 4: Noche, Días 5, 6 y 7: Descanso
    dias_def = [
        (1, t_dia.id, False),
        (2, t_dia.id, False),
        (3, t_noche.id, False),
        (4, t_noche.id, False),
        (5, None, True),
        (6, None, True),
        (7, None, True),
    ]
    for idx, t_id, es_desc in dias_def:
        db.add(CicloDetalleDia(ciclo_id=ciclo.id, dia_indice=idx, turno_id=t_id, es_descanso=es_desc))
    db.commit()

    assert len(ciclo.dias) == 7
    descansos = [d for d in ciclo.dias if d.es_descanso]
    assert len(descansos) == 3


def test_reglas_laborales_vigencia(db):
    """Valida que las reglas de 42h y franja nocturna respeten su vigencia temporal."""
    # Buscar regla jornada máxima
    reglas_42 = db.query(ReglaLaboral).filter(ReglaLaboral.codigo == "JORNADA_MAXIMA_SEMANAL").all()
    assert len(reglas_42) >= 2

    # En noviembre 2025 la jornada máxima era 44h
    regla_2025 = [r for r in reglas_42 if r.es_vigente_en(date(2025, 11, 1))][0]
    assert regla_2025.parametros["horas_semanales"] == 44

    # En septiembre 2026 la jornada máxima es 42h
    regla_2026 = [r for r in reglas_42 if r.es_vigente_en(date(2026, 9, 4))][0]
    assert regla_2026.parametros["horas_semanales"] == 42

    # Franja nocturna
    reglas_noct = db.query(ReglaLaboral).filter(ReglaLaboral.codigo == "FRANJA_NOCTURNA").all()
    noct_2025 = [r for r in reglas_noct if r.es_vigente_en(date(2025, 11, 1))][0]
    assert noct_2025.parametros["hora_inicio"] == "21:00"

    noct_2026 = [r for r in reglas_noct if r.es_vigente_en(date(2026, 9, 4))][0]
    assert noct_2026.parametros["hora_inicio"] == "19:00"
