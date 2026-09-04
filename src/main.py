"""
SIRH Plastitec — Módulo de Tiempos y Asistencia
Punto de entrada FastAPI para la API de Gestión, Ingesta, Aprobación y Exportación.
"""
import uuid
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db, Base, engine
from src.core.config import settings
from src.domain.models import (
    Empleado,
    Cargo,
    Turno,
    CicloRotativo,
    AuditoriaEvento,
    PeriodoNomina,
    ResultadoDiario,
)
from src.services.catalogo_service import CatalogoService
from src.services.ingesta_service import IngestaService
from src.services.motor_calculo import MotorCalculoService
from src.services.aprobacion_service import AprobacionService
from src.services.periodo_service import PeriodoService
from src.services.comparador_service import ComparadorParaleloService

# Asegurar tablas en la base de datos
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SIRH Plastitec — Módulo de Tiempos y Asistencia",
    description="Motor de cálculo de asistencia, turnos rotativos, umbral de 42h y exportador para Sinergy Nómina.",
    version="1.0.0",
)


# --- DTOs Pydantic ---
class IngestaSyncRequest(BaseModel):
    start_time: Optional[str] = Field(None, description="Formato 'YYYY-MM-DD HH:MM:SS'")
    end_time: Optional[str] = Field(None, description="Formato 'YYYY-MM-DD HH:MM:SS'")
    usuario_id: str = "USUARIO_WEB"


class AprobacionBloqueRequest(BaseModel):
    resultado_ids: List[int]
    usuario_id: str
    usuario_nombre: str
    rol: str = "SUPERVISOR"
    es_sustitucion_rrhh: bool = False
    anotacion: Optional[str] = None


class AjusteHorasRequest(BaseModel):
    resultado_id: int
    nuevas_horas: float
    motivo_justificacion: str
    usuario_id: str
    usuario_nombre: str
    rol: str = "SUPERVISOR"


class ReabrirPeriodoRequest(BaseModel):
    motivo_justificacion: str
    usuario_id: str
    usuario_nombre: str
    rol: str = "ADMIN"


# --- Endpoints ---

@app.get("/api/v1/health", tags=["Salud"])
def health_check():
    return {
        "status": "ok",
        "app": "SIRH Plastitec Módulo de Tiempos",
        "env": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/v1/catalogo/inicializar", tags=["Catálogo"])
def inicializar_catalogo(db: Session = Depends(get_db)):
    """Importa los turnos desde BioTime 8.5 y siembra las reglas legales base."""
    reglas = CatalogoService.sembrar_reglas_laborales_base(db)
    turnos = CatalogoService.importar_turnos_desde_biotime(db)
    return {
        "mensaje": "Catálogo inicializado con éxito",
        "turnos_importados": len(turnos),
        "reglas_sembradas": len(reglas),
    }


@app.post("/api/v1/ingesta/sincronizar", tags=["Ingesta"])
def sincronizar_asistencia(req: IngestaSyncRequest, db: Session = Depends(get_db)):
    """Ejecuta ingesta incremental e idempotente desde BioTime 8.5."""
    try:
        resultado = IngestaService.sincronizar_desde_biotime(
            db=db,
            start_time=req.start_time,
            end_time=req.end_time,
            usuario_id=req.usuario_id,
        )
        return resultado
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/aprobacion/bandeja", tags=["Aprobación Continua"])
def obtener_bandeja_supervisor(
    supervisor_id: str = Query(..., description="ID del supervisor"),
    rol: str = Query("SUPERVISOR"),
    solo_excepciones: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Consulta la bandeja diaria de conceptos a aprobar según el alcance del supervisor."""
    return AprobacionService.obtener_bandeja_supervisor(
        db=db,
        supervisor_id=supervisor_id,
        rol=rol,
        solo_excepciones=solo_excepciones,
    )


@app.post("/api/v1/aprobacion/aprobar-bloque", tags=["Aprobación Continua"])
def aprobar_en_bloque(req: AprobacionBloqueRequest, db: Session = Depends(get_db)):
    """Aprueba un conjunto de resultados en un solo clic."""
    try:
        aprobados = AprobacionService.aprobar_en_bloque(
            db=db,
            resultado_ids=req.resultado_ids,
            usuario_id=req.usuario_id,
            usuario_nombre=req.usuario_nombre,
            rol=req.rol,
            es_sustitucion_rrhh=req.es_sustitucion_rrhh,
            anotacion=req.anotacion,
        )
        return {"mensaje": f"Se aprobaron {aprobados} conceptos exitosamente."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/api/v1/aprobacion/ajustar", tags=["Aprobación Continua"])
def ajustar_horas(req: AjusteHorasRequest, db: Session = Depends(get_db)):
    """Ajuste manual de horas calculado con justificación obligatoria."""
    try:
        res = AprobacionService.ajustar_resultado(
            db=db,
            resultado_id=req.resultado_id,
            nuevas_horas=req.nuevas_horas,
            motivo_justificacion=req.motivo_justificacion,
            usuario_id=req.usuario_id,
            usuario_nombre=req.usuario_nombre,
            rol=req.rol,
        )
        return {
            "mensaje": "Ajuste registrado exitosamente",
            "resultado_id": res.id,
            "horas_finales": float(res.cantidad_horas),
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/api/v1/periodos/{anio}/{mes}/abrir", tags=["Períodos y Nómina"])
def abrir_periodo(anio: int, mes: int, db: Session = Depends(get_db)):
    """Abre o consulta el período 11 al 10 para el mes indicado."""
    p = PeriodoService.obtener_o_crear_periodo(db, anio, mes)
    return {
        "id": p.id,
        "codigo": p.codigo,
        "fecha_inicio": p.fecha_inicio.isoformat(),
        "fecha_fin": p.fecha_fin.isoformat(),
        "estado": p.estado,
    }


@app.post("/api/v1/periodos/{periodo_id}/bloquear-rrhh", tags=["Períodos y Nómina"])
def bloquear_procesamiento_rrhh(
    periodo_id: int,
    usuario_id: str = "RRHH_ADMIN",
    usuario_nombre: str = "Responsable RRHH",
    db: Session = Depends(get_db),
):
    """Bloquea modificaciones de supervisores al iniciar el procesamiento de RRHH."""
    try:
        p = PeriodoService.iniciar_procesamiento_rrhh(
            db=db,
            periodo_id=periodo_id,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
        )
        return {"mensaje": "Período bloqueado exitosamente para supervisores.", "estado": p.estado}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/api/v1/periodos/{periodo_id}/exportar-sinergy", tags=["Períodos y Nómina"])
def exportar_sinergy(
    periodo_id: int,
    usuario_id: str = "RRHH_ADMIN",
    usuario_nombre: str = "Responsable RRHH",
    forzar: bool = False,
    db: Session = Depends(get_db),
):
    """Cierra el período y genera el archivo plano oficial FINAL_SINER_*.txt para Sinergy."""
    try:
        exp = PeriodoService.cerrar_y_exportar_sinergy(
            db=db,
            periodo_id=periodo_id,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            forzar_cierre=forzar,
        )
        return {
            "mensaje": "Archivo plano generado exitosamente",
            "archivo": exp.nombre_archivo,
            "hash_sha256": exp.hash_sha256,
            "total_lineas": exp.total_lineas,
            "total_horas": float(exp.total_horas),
            "preview_contenido": exp.contenido_txt[:500],
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.post("/api/v1/periodos/{periodo_id}/reabrir", tags=["Períodos y Nómina"])
def reabrir_periodo(
    periodo_id: int,
    req: ReabrirPeriodoRequest,
    db: Session = Depends(get_db),
):
    """Reapertura excepcional de período con justificación obligatoria y rol elevado."""
    try:
        p = PeriodoService.reabrir_periodo(
            db=db,
            periodo_id=periodo_id,
            motivo_justificacion=req.motivo_justificacion,
            usuario_id=req.usuario_id,
            usuario_nombre=req.usuario_nombre,
            rol=req.rol,
        )
        return {"mensaje": "Período reabierto", "estado": p.estado}
    except (ValueError, PermissionError) as err:
        raise HTTPException(status_code=400, detail=str(err))


@app.get("/api/v1/paralelo/conciliar", tags=["Paralelo y Auditoría"])
def conciliar_paralelo(
    desde: date = Query(..., description="Fecha inicio YYYY-MM-DD"),
    hasta: date = Query(..., description="Fecha fin YYYY-MM-DD"),
    emp_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Ejecuta conciliación de cálculo vs reporte dailyHourReport de BioTime."""
    return ComparadorParaleloService.conciliar_jornadas_vs_biotime(
        db=db,
        fecha_inicio=desde,
        fecha_fin=hasta,
        emp_code=emp_code,
    )
