"""
Servicio de Ingesta y Normalización de Marcaciones (Etapas 1 y 2).
Garantiza idempotencia estricta por biotime_trans_id y trazabilidad inmutable.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.domain.models.asistencia import MarcacionCruda, MarcacionNormalizada
from src.domain.models.identidad import MapeoIdentidad, Empleado, Cargo
from src.adapters.biotime.client import BioTimeAdapter
from src.core.audit import AuditService


def _parse_iso_or_space(dt_str: Any) -> Optional[datetime]:
    if not dt_str:
        return None
    if isinstance(dt_str, datetime):
        return dt_str
    s = str(dt_str).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


class IngestaService:
    @classmethod
    def normalizar_evento(cls, punch_state: str) -> str:
        """Determina el tipo de evento a partir del estado de BioTime."""
        st = str(punch_state).strip()
        if st == "0":
            return "ENTRADA"
        elif st == "1":
            return "SALIDA"
        return "INDETERMINADO"

    @classmethod
    def ingestar_transacciones(
        cls,
        db: Session,
        raw_list: List[Dict[str, Any]],
        usuario_id: str = "JOB_INGESTA",
    ) -> Dict[str, int]:
        """
        Procesa un lote de transacciones crudas de BioTime.
        1. Inserta en rrhh_marcacion_cruda con idempotencia por biotime_trans_id.
        2. Genera la rrhh_marcacion_normalizada correspondiente vinculando a la identidad SIRH.
        """
        insertadas = 0
        duplicadas_ignoradas = 0
        marcas_duplicadas_detectadas = 0

        # Cache de mapeo de identidad para rendimiento
        mapeos = {m.biotime_emp_code: m.empleado_id for m in db.query(MapeoIdentidad).all()}

        # Cargo por defecto para empleados nuevos auto-descubiertos
        cargo_def = db.query(Cargo).first()
        if not cargo_def:
            cargo_def = Cargo(codigo="GENERAL", nombre="Personal de Planta", perfil_laboral="ROTATIVO")
            db.add(cargo_def)
            db.commit()

        for raw in raw_list:
            trans_id = raw.get("id")
            if not trans_id:
                continue

            # Idempotencia: Verificar si ya fue ingestada previamente
            existe_cruda = db.query(MarcacionCruda).filter(MarcacionCruda.biotime_trans_id == trans_id).first()
            if existe_cruda:
                duplicadas_ignoradas += 1
                continue

            emp_code = str(raw.get("emp_code") or "").strip()
            punch_time = _parse_iso_or_space(raw.get("punch_time") or raw.get("att_time") or raw.get("checktime"))
            upload_time = _parse_iso_or_space(raw.get("upload_time") or raw.get("sync_time")) or punch_time
            punch_state = str(raw.get("punch_state") or "255")
            terminal_sn = str(raw.get("terminal_sn") or "UNKNOWN")
            terminal_alias = raw.get("terminal_alias")
            area_alias = raw.get("area_alias")

            if not punch_time:
                continue

            # 1. Crear Marcación Cruda
            cruda = MarcacionCruda(
                biotime_trans_id=trans_id,
                emp_code=emp_code,
                punch_time=punch_time,
                upload_time=upload_time,
                punch_state=punch_state,
                verify_type=raw.get("verify_type"),
                terminal_sn=terminal_sn,
                terminal_alias=terminal_alias,
                area_alias=area_alias,
                raw_payload=raw,
            )
            db.add(cruda)

            # 2. Resolver Empleado en SIRH
            empleado_id = mapeos.get(emp_code)
            if not empleado_id:
                # Si el empleado no estaba mapeado, crear empleado e identidad para no perder la marcación
                nuevo_emp = Empleado(
                    sirh_emp_id=f"AUTO-{emp_code}",
                    nombres=f"Empleado {emp_code}",
                    apellidos="Importado",
                    cargo_id=cargo_def.id,
                )
                db.add(nuevo_emp)
                db.flush()

                nuevo_mapeo = MapeoIdentidad(
                    empleado_id=nuevo_emp.id,
                    sirh_emp_id=nuevo_emp.sirh_emp_id,
                    biotime_emp_id=raw.get("emp") or int(emp_code) if emp_code.isdigit() else 0,
                    biotime_emp_code=emp_code,
                    sinergy_emp_code=emp_code,
                    tipo_vinculacion="DIRECTO",
                )
                db.add(nuevo_mapeo)
                db.flush()
                empleado_id = nuevo_emp.id
                mapeos[emp_code] = empleado_id

            # 3. Detección de marcación doble/duplicada en la misma terminal (< 2 minutos)
            limite_inf = punch_time - timedelta(minutes=2)
            limite_sup = punch_time + timedelta(minutes=2)
            existe_cercana = (
                db.query(MarcacionNormalizada)
                .join(MarcacionCruda, MarcacionNormalizada.biotime_trans_id == MarcacionCruda.biotime_trans_id)
                .filter(
                    MarcacionNormalizada.empleado_id == empleado_id,
                    MarcacionCruda.terminal_sn == terminal_sn,
                    MarcacionNormalizada.timestamp_efectivo >= limite_inf,
                    MarcacionNormalizada.timestamp_efectivo <= limite_sup,
                )
                .first()
            )
            es_duplicada = existe_cercana is not None
            if es_duplicada:
                marcas_duplicadas_detectadas += 1

            # 4. Crear Marcación Normalizada
            tipo_evento = cls.normalizar_evento(punch_state)
            normalizada = MarcacionNormalizada(
                biotime_trans_id=trans_id,
                empleado_id=empleado_id,
                timestamp_efectivo=punch_time,
                tipo_evento=tipo_evento,
                es_duplicada=es_duplicada,
                es_manual=False,
            )
            db.add(normalizada)
            db.flush()
            insertadas += 1

        db.commit()

        if insertadas > 0:
            AuditService.registrar_evento(
                db=db,
                usuario_id=usuario_id,
                usuario_nombre="Job de Ingesta Asistencia",
                rol="SISTEMA",
                ip_origen="127.0.0.1",
                accion="INGESTAR_MARCACIONES",
                entidad="rrhh_marcacion_cruda",
                entidad_id=f"LOTE_{len(raw_list)}",
                motivo_justificacion=f"Ingesta incremental: {insertadas} nuevas, {duplicadas_ignoradas} ya existentes",
                valor_nuevo={
                    "insertadas": insertadas,
                    "duplicadas_ignoradas": duplicadas_ignoradas,
                    "marcas_rebote_detectadas": marcas_duplicadas_detectadas,
                },
            )

        return {
            "total_recibidas": len(raw_list),
            "insertadas": insertadas,
            "duplicadas_ignoradas": duplicadas_ignoradas,
            "marcas_rebote_detectadas": marcas_duplicadas_detectadas,
        }

    @classmethod
    def sincronizar_desde_biotime(
        cls,
        db: Session,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        usuario_id: str = "JOB_INGESTA",
    ) -> Dict[str, int]:
        """Extrae transacciones de BioTime 8.5 y las procesa en el pipeline."""
        adapter = BioTimeAdapter().autenticar()
        transacciones = adapter.obtener_transacciones(start_time=start_time, end_time=end_time)
        return cls.ingestar_transacciones(db=db, raw_list=transacciones, usuario_id=usuario_id)
