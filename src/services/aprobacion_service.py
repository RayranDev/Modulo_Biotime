"""
Servicio de Aprobación Continua por Jefe Inmediato (Fase 5 / Requisito P3).
- Aprobación por excepción, individual o en bloque
- Ajuste con justificación obligatoria
- Aprobación sustituta por RRHH con anotación obligatoria
- Trazabilidad inmutable completa
"""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.domain.models.calculo import ResultadoDiario, JornadaResuelta
from src.domain.models.identidad import Empleado, SupervisorAlcance
from src.core.audit import AuditService


class AprobacionService:
    CONCEPTO_DESCRIPCIONES = {
        "0100": "Horas Ordinarias (Diurnas)",
        "0150": "Recargo Nocturno Ordinario",
        "0200": "Hora Extra Diurna (HED)",
        "0210": "Hora Extra Nocturna (HEN)",
        "0220": "Recargo Nocturno Ordinario (19h/21h)",
        "0250": "Hora Extra Diurna Festiva (HEDF)",
        "0252": "Recargo Dominical/Festivo Diurno",
        "0253": "Recargo Dominical/Festivo Diurno (Pre-2026)",
        "0258": "Recargo Dominical/Festivo Nocturno",
        "0259": "Recargo Dominical/Festivo Nocturno (Pre-2026)",
        "0260": "Hora Extra Nocturna Festiva (HENF)",
        "0300": "Recargo Festivo Diurno",
        "0350": "Recargo Festivo Nocturno",
        "ORDINARIA": "Horas Ordinarias de Turno",
    }

    @classmethod
    def obtener_bandeja_supervisor(
        cls,
        db: Session,
        supervisor_id: str,
        rol: str = "SUPERVISOR",
        solo_excepciones: bool = False,
        estado: Optional[str] = "PENDIENTE",
    ) -> List[Dict[str, Any]]:
        """
        Consulta la bandeja de aprobación según el alcance organizacional del supervisor.
        Si es rol 'RRHH' o 'ADMIN', puede ver todos los empleados.
        """
        query = (
            db.query(ResultadoDiario)
            .join(Empleado, ResultadoDiario.empleado_id == Empleado.id)
        )

        if estado and estado.upper() != "TODOS":
            query = query.filter(ResultadoDiario.estado_aprobacion == estado.upper())

        if rol not in ("RRHH", "ADMIN") and supervisor_id != "SUPERVISOR_TODOS":
            # Filtrar por alcance del supervisor
            alcances = db.query(SupervisorAlcance).filter(
                SupervisorAlcance.supervisor_usuario_id == supervisor_id,
                SupervisorAlcance.es_activo == True,
            ).all()
            depts = [a.departamento_id for a in alcances if a.departamento_id]
            areas = [a.area_id for a in alcances if a.area_id]
            if depts or areas:
                query = query.filter(
                    (Empleado.departamento_id.in_(depts)) | (Empleado.area_id.in_(areas))
                )
            else:
                # Si no tiene alcance explícito, solo aprueba sus reportes directos
                query = query.filter(Empleado.jefe_inmediato_id == supervisor_id)

        if solo_excepciones:
            # Excepciones: horas extras (> 0), conceptos de horas extras (0200, 0210, 0250, 0260)
            query = query.filter(ResultadoDiario.concepto_dominio.in_(["0200", "0210", "0250", "0260"]))

        resultados = query.order_by(ResultadoDiario.fecha_imputacion.desc(), ResultadoDiario.id.desc()).all()
        return [
            {
                "resultado_id": r.id,
                "empleado_id": r.empleado_id,
                "emp_code": r.empleado.sirh_emp_id,
                "empleado_nombre": f"{r.empleado.nombres} {r.empleado.apellidos}",
                "departamento": r.empleado.departamento.nombre if r.empleado.departamento else "Planta Producción",
                "fecha_imputacion": r.fecha_imputacion.isoformat(),
                "concepto": r.concepto_dominio,
                "concepto_descripcion": cls.CONCEPTO_DESCRIPCIONES.get(r.concepto_dominio, r.concepto_dominio),
                "horas": float(r.cantidad_horas),
                "estado": r.estado_aprobacion,
                "es_extra": r.concepto_dominio in ("0200", "0210", "0250", "0260"),
                "ajuste_horas": float(r.ajuste_horas) if r.ajuste_horas is not None else None,
                "motivo_ajuste": r.motivo_ajuste,
                "supervisor_id": r.supervisor_id,
                "aprobado_el": r.aprobado_el.isoformat() if r.aprobado_el else None,
            }
            for r in resultados
        ]

    @classmethod
    def aprobar_en_bloque(
        cls,
        db: Session,
        resultado_ids: List[int],
        usuario_id: str,
        usuario_nombre: str,
        rol: str,
        ip_origen: str = "127.0.0.1",
        es_sustitucion_rrhh: bool = False,
        anotacion: Optional[str] = None,
    ) -> int:
        """
        Aprueba un conjunto de resultados en un solo clic.
        Si RRHH aprueba por sustitución del jefe, la anotación es OBLIGATORIA por política.
        """
        if es_sustitucion_rrhh and (not anotacion or not anotacion.strip()):
            raise ValueError("La aprobación sustituta por RRHH exige una anotación obligatoria.")

        now_utc = datetime.now(timezone.utc)
        resultados = db.query(ResultadoDiario).filter(ResultadoDiario.id.in_(resultado_ids)).all()

        for r in resultados:
            r.estado_aprobacion = "APROBADO"
            r.supervisor_id = usuario_id
            r.aprobado_el = now_utc

        db.commit()

        motivo = (
            f"Aprobación sustituta por RRHH: {anotacion.strip()}"
            if es_sustitucion_rrhh
            else f"Aprobación en bloque de {len(resultados)} conceptos por {rol}"
        )

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="APROBACION_BLOQUE",
            entidad="rrhh_resultado_diario",
            entidad_id=f"LOTE_{len(resultado_ids)}",
            motivo_justificacion=motivo,
            valor_nuevo={"aprobados_count": len(resultados), "resultado_ids": resultado_ids},
        )

        return len(resultados)

    @classmethod
    def ajustar_resultado(
        cls,
        db: Session,
        resultado_id: int,
        nuevas_horas: float,
        motivo_justificacion: str,
        usuario_id: str,
        usuario_nombre: str,
        rol: str,
        ip_origen: str = "127.0.0.1",
    ) -> ResultadoDiario:
        """
        Ajuste manual de horas calculado. Exige justificación tipificada u obligatoria.
        Principio inviolable: Queda trazado con valor anterior y valor nuevo.
        """
        if not motivo_justificacion or not motivo_justificacion.strip():
            raise ValueError("El ajuste manual de horas exige una justificación obligatoria.")

        resultado = db.query(ResultadoDiario).filter(ResultadoDiario.id == resultado_id).first()
        if not resultado:
            raise ValueError(f"No existe el resultado con id {resultado_id}")

        valor_ant = {"horas": float(resultado.cantidad_horas), "estado": resultado.estado_aprobacion}
        now_utc = datetime.now(timezone.utc)

        resultado.ajuste_horas = nuevas_horas
        resultado.cantidad_horas = nuevas_horas
        resultado.motivo_ajuste = motivo_justificacion.strip()
        resultado.estado_aprobacion = "AJUSTADO"
        resultado.supervisor_id = usuario_id
        resultado.aprobado_el = now_utc

        db.commit()

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="AJUSTAR_HORAS",
            entidad="rrhh_resultado_diario",
            entidad_id=str(resultado_id),
            motivo_justificacion=motivo_justificacion.strip(),
            valor_anterior=valor_ant,
            valor_nuevo={"horas": nuevas_horas, "estado": "AJUSTADO"},
        )

        return resultado

    @classmethod
    def rechazar_resultado(
        cls,
        db: Session,
        resultado_id: int,
        motivo_rechazo: str,
        usuario_id: str,
        usuario_nombre: str,
        rol: str,
        ip_origen: str = "127.0.0.1",
    ) -> ResultadoDiario:
        """Rechaza un concepto calculado con justificación obligatoria."""
        if not motivo_rechazo or not motivo_rechazo.strip():
            raise ValueError("El rechazo de un cálculo exige un motivo obligatorio.")

        resultado = db.query(ResultadoDiario).filter(ResultadoDiario.id == resultado_id).first()
        if not resultado:
            raise ValueError(f"No existe el resultado con id {resultado_id}")

        valor_ant = {"estado": resultado.estado_aprobacion, "horas": float(resultado.cantidad_horas)}
        resultado.estado_aprobacion = "RECHAZADO"
        resultado.motivo_ajuste = motivo_rechazo.strip()
        resultado.supervisor_id = usuario_id
        resultado.aprobado_el = datetime.now(timezone.utc)

        db.commit()

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="RECHAZAR_HORAS",
            entidad="rrhh_resultado_diario",
            entidad_id=str(resultado_id),
            motivo_justificacion=motivo_rechazo.strip(),
            valor_anterior=valor_ant,
            valor_nuevo={"estado": "RECHAZADO"},
        )

        return resultado
