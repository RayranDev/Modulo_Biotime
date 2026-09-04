"""
Pruebas de Integración para Fase 7: API REST y Herramienta de Comparación en Paralelo.
"""
import pytest
from datetime import date
from fastapi.testclient import TestClient
from src.main import app
from src.core.database import SessionLocal, Base, engine, get_db
from src.services.comparador_service import ComparadorParaleloService
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.calculo import JornadaResuelta

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()




def test_api_health(client):
    """Valida el endpoint de salud de la aplicación."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "SIRH Plastitec" in data["app"]


def test_api_flujo_periodo_completo(client, db):
    """Valida el flujo de endpoints: abrir período -> bloquear por RRHH -> exportar archivo plano."""
    # 1. Abrir período de septiembre 2026
    resp_abrir = client.post("/api/v1/periodos/2026/9/abrir")
    assert resp_abrir.status_code == 200
    p_data = resp_abrir.json()
    periodo_id = p_data["id"]
    assert p_data["estado"] == "ABIERTO"

    # 2. Bloquear para procesamiento por RRHH
    resp_bloq = client.post(f"/api/v1/periodos/{periodo_id}/bloquear-rrhh")
    assert resp_bloq.status_code == 200
    assert resp_bloq.json()["estado"] == "EN_PROCESAMIENTO"

    # 3. Exportar a Sinergy (forzando cierre para el test)
    resp_exp = client.post(f"/api/v1/periodos/{periodo_id}/exportar-sinergy?forzar=true")
    assert resp_exp.status_code == 200
    exp_data = resp_exp.json()
    assert "FINAL_SINER_" in exp_data["archivo"]
    assert len(exp_data["hash_sha256"]) == 64


def test_comparador_paralelo_clasificacion_diagnosticos(db):
    """Valida la clasificación de coincidencias y desvíos esperados (P1/P4) en la conciliación."""
    cargo = Cargo(codigo="OP_COMP", nombre="Operario", perfil_laboral="ROTATIVO")
    db.add(cargo)
    db.commit()

    emp = Empleado(sirh_emp_id="EMP-COMP-01", nombres="Julio", apellidos="Mora", cargo_id=cargo.id)
    db.add(emp)
    db.commit()

    mapeo = MapeoIdentidad(
        empleado_id=emp.id,
        sirh_emp_id=emp.sirh_emp_id,
        biotime_emp_id=4001,
        biotime_emp_code="8888",
        sinergy_emp_code="8888",
        tipo_vinculacion="DIRECTO",
    )
    db.add(mapeo)
    db.commit()

    # Crear una jornada de prueba
    f_imput = date(2026, 9, 2)
    j = JornadaResuelta(
        empleado_id=emp.id,
        fecha_imputacion=f_imput,
        minutos_trabajados_brutos=720,
        minutos_descuento_almuerzo=60,
        minutos_trabajados_netos=660, # 11.0 horas netas
        estado_jornada="COMPLETA",
        calculo_id="CALC-COMP-1",
    )
    db.add(j)
    db.commit()

    # Ejecutar conciliación
    res = ComparadorParaleloService.conciliar_jornadas_vs_biotime(
        db=db,
        fecha_inicio=date(2026, 9, 1),
        fecha_fin=date(2026, 9, 5),
        emp_code="8888",
    )

    assert res["total_evaluadas"] >= 1
    assert "coincidencias" in res
    assert "desvios_explicables_p1_p4" in res
