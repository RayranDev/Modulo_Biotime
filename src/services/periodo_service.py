"""
Servicio de Gestión de Ciclos 11→10, Bloqueo de RRHH y Exportación Sinergy (Fase 6).
Controla la máquina de estados del período y la generación del archivo plano auditado.
"""
from datetime import datetime, date, timezone, timedelta
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.domain.models.periodo import PeriodoNomina, ExportacionSinergy
from src.domain.models.calculo import ResultadoDiario
from src.domain.models.identidad import Empleado, MapeoIdentidad
from src.adapters.sinergy.exporter import SinergyExporterAdapter
from src.core.audit import AuditService


class PeriodoService:
    @classmethod
    def calcular_fechas_ciclo(cls, anio: int, mes: int) -> Tuple[date, date]:
        """Calcula el rango de fechas 11→10 para un mes dado."""
        fecha_fin = date(anio, mes, 10)
        # Fecha inicio: día 11 del mes anterior
        if mes == 1:
            fecha_inicio = date(anio - 1, 12, 11)
        else:
            fecha_inicio = date(anio, mes - 1, 11)
        return fecha_inicio, fecha_fin

    @classmethod
    def obtener_o_crear_periodo(cls, db: Session, anio: int, mes: int) -> PeriodoNomina:
        """Abre o recupera un período de nómina 11→10."""
        f_ini, f_fin = cls.calcular_fechas_ciclo(anio, mes)
        codigo = f"PER_{anio}_{mes:02d}"

        periodo = db.query(PeriodoNomina).filter(PeriodoNomina.codigo == codigo).first()
        if not periodo:
            periodo = PeriodoNomina(
                codigo=codigo,
                fecha_inicio=f_ini,
                fecha_fin=f_fin,
                estado="ABIERTO",
            )
            db.add(periodo)
            db.commit()
            db.refresh(periodo)

        return periodo

    @classmethod
    def iniciar_procesamiento_rrhh(
        cls,
        db: Session,
        periodo_id: int,
        usuario_id: str,
        usuario_nombre: str,
        rol: str = "RRHH",
        ip_origen: str = "127.0.0.1",
    ) -> PeriodoNomina:
        """
        Bloquea modificaciones de supervisores al iniciar el procesamiento de RRHH (Día 11).
        Máquina de estados: ABIERTO -> EN_PROCESAMIENTO.
        """
        periodo = db.query(PeriodoNomina).filter(PeriodoNomina.id == periodo_id).first()
        if not periodo:
            raise ValueError(f"No existe período con ID {periodo_id}")

        if periodo.estado == "CERRADO":
            raise ValueError("El período ya se encuentra CERRADO.")

        now_utc = datetime.now(timezone.utc)
        periodo.estado = "EN_PROCESAMIENTO"
        periodo.bloqueado_en = now_utc
        periodo.bloqueado_por = usuario_id
        db.commit()

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="BLOQUEO_PROCESAMIENTO_RRHH",
            entidad="rrhh_periodo_nomina",
            entidad_id=str(periodo_id),
            motivo_justificacion="Inicio de procesamiento de nómina por RRHH: bloqueo de modificaciones para supervisores",
            valor_nuevo={"estado": "EN_PROCESAMIENTO", "bloqueado_en": now_utc.isoformat()},
        )

        return periodo

    @classmethod
    def validar_pendientes(cls, db: Session, periodo_id: int) -> int:
        """Retorna la cantidad de conceptos aún pendientes de aprobación en el período."""
        periodo = db.query(PeriodoNomina).filter(PeriodoNomina.id == periodo_id).first()
        if not periodo:
            return 0

        return (
            db.query(ResultadoDiario)
            .filter(
                ResultadoDiario.fecha_imputacion >= periodo.fecha_inicio,
                ResultadoDiario.fecha_imputacion <= periodo.fecha_fin,
                ResultadoDiario.estado_aprobacion == "PENDIENTE",
            )
            .count()
        )

    @classmethod
    def cerrar_y_exportar_sinergy(
        cls,
        db: Session,
        periodo_id: int,
        usuario_id: str,
        usuario_nombre: str,
        rol: str = "RRHH",
        ip_origen: str = "127.0.0.1",
        forzar_cierre: bool = False,
    ) -> ExportacionSinergy:
        """
        Cierra el período y genera el archivo plano oficial FINAL_SINER_*.txt.
        Si hay conceptos pendientes, rechaza el cierre a menos que se fuerce con justificación.
        """
        periodo = db.query(PeriodoNomina).filter(PeriodoNomina.id == periodo_id).first()
        if not periodo:
            raise ValueError(f"No existe período con ID {periodo_id}")

        pendientes = cls.validar_pendientes(db, periodo_id)
        if pendientes > 0 and not forzar_cierre:
            raise ValueError(f"No se puede cerrar el período: existen {pendientes} conceptos en estado PENDIENTE de aprobación.")

        # Consultar conceptos aprobados y ajustados para el período
        filas = (
            db.query(
                MapeoIdentidad.sinergy_emp_code,
                ResultadoDiario.concepto_dominio,
                func.sum(ResultadoDiario.cantidad_horas).label("total_horas"),
            )
            .join(Empleado, ResultadoDiario.empleado_id == Empleado.id)
            .join(MapeoIdentidad, Empleado.id == MapeoIdentidad.empleado_id)
            .filter(
                ResultadoDiario.fecha_imputacion >= periodo.fecha_inicio,
                ResultadoDiario.fecha_imputacion <= periodo.fecha_fin,
                ResultadoDiario.estado_aprobacion.in_(["APROBADO", "AJUSTADO"]),
            )
            .group_by(MapeoIdentidad.sinergy_emp_code, ResultadoDiario.concepto_dominio)
            .order_by(MapeoIdentidad.sinergy_emp_code.asc(), ResultadoDiario.concepto_dominio.asc())
            .all()
        )

        registros = [
            {
                "sinergy_emp_code": f[0],
                "concepto_dominio": f[1],
                "cantidad_horas": float(f[2]),
            }
            for f in filas
        ]

        nombre_arch, txt_content, hash_sha, total_horas = SinergyExporterAdapter.generar_archivo_plano(
            fecha_inicio=periodo.fecha_inicio,
            fecha_fin=periodo.fecha_fin,
            registros_agrupados=registros,
        )

        now_utc = datetime.now(timezone.utc)
        exportacion = ExportacionSinergy(
            periodo_id=periodo.id,
            nombre_archivo=nombre_arch,
            contenido_txt=txt_content,
            hash_sha256=hash_sha,
            total_lineas=len(registros),
            total_horas=total_horas,
            generado_por=usuario_id,
            generado_el=now_utc,
        )
        db.add(exportacion)

        # Transición de estado a CERRADO
        periodo.estado = "CERRADO"
        periodo.cerrado_en = now_utc
        periodo.cerrado_por = usuario_id
        db.commit()
        db.refresh(exportacion)

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="CIERRE_PERIODO_EXPORTACION_SINERGY",
            entidad="rrhh_periodo_nomina",
            entidad_id=str(periodo_id),
            motivo_justificacion=f"Cierre de período {periodo.codigo} y generación de archivo plano {nombre_arch} (SHA-256: {hash_sha[:16]}...)",
            valor_nuevo={
                "archivo": nombre_arch,
                "hash": hash_sha,
                "total_lineas": len(registros),
                "total_horas": total_horas,
            },
        )

        return exportacion

    @classmethod
    def reabrir_periodo(
        cls,
        db: Session,
        periodo_id: int,
        motivo_justificacion: str,
        usuario_id: str,
        usuario_nombre: str,
        rol: str,
        ip_origen: str = "127.0.0.1",
    ) -> PeriodoNomina:
        """
        Reapertura deliberadamente difícil de un período cerrado.
        Exige rol elevado (ADMIN/RRHH_DIR) y justificación obligatoria.
        """
        if rol not in ("ADMIN", "RRHH_DIR"):
            raise PermissionError("Solo un usuario con rol 'ADMIN' o 'RRHH_DIR' puede reabrir un período cerrado.")

        if not motivo_justificacion or not motivo_justificacion.strip():
            raise ValueError("La reapertura de un período exige un motivo/justificación formal obligatoria.")

        periodo = db.query(PeriodoNomina).filter(PeriodoNomina.id == periodo_id).first()
        if not periodo:
            raise ValueError(f"No existe período con ID {periodo_id}")

        valor_ant = {"estado": periodo.estado, "cerrado_en": periodo.cerrado_en.isoformat() if periodo.cerrado_en else None}

        periodo.estado = "REABIERTO"
        periodo.motivo_reapertura = motivo_justificacion.strip()
        db.commit()

        AuditService.registrar_evento(
            db=db,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion="REAPERTURA_PERIODO",
            entidad="rrhh_periodo_nomina",
            entidad_id=str(periodo_id),
            motivo_justificacion=motivo_justificacion.strip(),
            valor_anterior=valor_ant,
            valor_nuevo={"estado": "REABIERTO", "motivo": motivo_justificacion.strip()},
        )

        return periodo
