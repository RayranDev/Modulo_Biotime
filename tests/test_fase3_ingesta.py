"""
Pruebas de Ingesta, Idempotencia y Normalización (Fase 3).
"""
import pytest
from datetime import datetime, timedelta
from src.core.database import SessionLocal, Base, engine
from src.domain.models.asistencia import MarcacionCruda, MarcacionNormalizada
from src.domain.models.identidad import Cargo, Empleado, MapeoIdentidad
from src.domain.models.auditoria import AuditoriaEvento
from src.services.ingesta_service import IngestaService






def test_ingesta_idempotencia_estricta(db):
    """Re-ingestar la misma transacción no debe duplicarla ni causar error de integridad."""
    raw_lote = [
        {
            "id": 999001,
            "emp_code": "9001",
            "punch_time": "2026-09-04 05:55:00",
            "upload_time": "2026-09-04 05:55:03",
            "punch_state": "0",
            "terminal_sn": "TERM_01",
            "terminal_alias": "PLANTA INYECCION 1",
        },
        {
            "id": 999002,
            "emp_code": "9001",
            "punch_time": "2026-09-04 18:05:00",
            "upload_time": "2026-09-04 18:05:04",
            "punch_state": "1",
            "terminal_sn": "TERM_01",
            "terminal_alias": "PLANTA INYECCION 1",
        },
    ]

    # Primera ingesta
    res1 = IngestaService.ingestar_transacciones(db=db, raw_list=raw_lote, usuario_id="TEST_JOB")
    assert res1["insertadas"] == 2
    assert res1["duplicadas_ignoradas"] == 0

    # Segunda ingesta exactamente con los mismos IDs
    res2 = IngestaService.ingestar_transacciones(db=db, raw_list=raw_lote, usuario_id="TEST_JOB")
    assert res2["insertadas"] == 0
    assert res2["duplicadas_ignoradas"] == 2

    # Verificar que en base de datos siguen habiendo solo 2 registros
    total_crudas = db.query(MarcacionCruda).filter(MarcacionCruda.biotime_trans_id.in_([999001, 999002])).count()
    assert total_crudas == 2


def test_deteccion_doble_marcacion_rebote(db):
    """Dos marcaciones en la misma terminal en menos de 2 minutos deben marcarse como rebote/duplicada."""
    t_base = datetime(2026, 9, 4, 6, 0, 0)
    raw_rebote = [
        {
            "id": 999010,
            "emp_code": "9002",
            "punch_time": t_base.strftime("%Y-%m-%d %H:%M:%S"),
            "upload_time": t_base.strftime("%Y-%m-%d %H:%M:%S"),
            "punch_state": "0",
            "terminal_sn": "TERM_REBOTE",
        },
        {
            "id": 999011,
            "emp_code": "9002",
            "punch_time": (t_base + timedelta(seconds=45)).strftime("%Y-%m-%d %H:%M:%S"),
            "upload_time": t_base.strftime("%Y-%m-%d %H:%M:%S"),
            "punch_state": "0",
            "terminal_sn": "TERM_REBOTE",
        },
    ]

    res = IngestaService.ingestar_transacciones(db=db, raw_list=raw_rebote, usuario_id="TEST_JOB")
    assert res["insertadas"] == 2
    assert res["marcas_rebote_detectadas"] == 1

    norm_segunda = db.query(MarcacionNormalizada).filter(MarcacionNormalizada.biotime_trans_id == 999011).first()
    assert norm_segunda.es_duplicada is True


def test_marcacion_rezagada_imputacion_correcta(db):
    """Una marcación que llega 3 días tarde por terminal offline debe conservar su fecha real."""
    punch_real = datetime(2026, 9, 1, 14, 0, 0)  # Hace 3 días
    upload_hoy = datetime(2026, 9, 4, 9, 0, 0)   # Sube hoy

    raw_rezagada = [
        {
            "id": 999020,
            "emp_code": "9003",
            "punch_time": punch_real.strftime("%Y-%m-%d %H:%M:%S"),
            "upload_time": upload_hoy.strftime("%Y-%m-%d %H:%M:%S"),
            "punch_state": "1",
            "terminal_sn": "TERM_OFFLINE",
        }
    ]

    res = IngestaService.ingestar_transacciones(db=db, raw_list=raw_rezagada, usuario_id="TEST_JOB")
    assert res["insertadas"] == 1

    cruda = db.query(MarcacionCruda).filter(MarcacionCruda.biotime_trans_id == 999020).first()
    assert cruda.punch_time == punch_real
    assert cruda.upload_time == upload_hoy

    norm = db.query(MarcacionNormalizada).filter(MarcacionNormalizada.biotime_trans_id == 999020).first()
    assert norm.timestamp_efectivo == punch_real
    assert norm.tipo_evento == "SALIDA"
