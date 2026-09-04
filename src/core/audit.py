"""
Servicio de Auditoría Inmutable.
Garantiza registro append-only con firma criptográfica SHA-256.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from src.domain.models.auditoria import AuditoriaEvento


class AuditService:
    @staticmethod
    def _calcular_hash(
        timestamp_iso: str,
        usuario_id: str,
        accion: str,
        entidad: str,
        entidad_id: str,
        valor_anterior: Optional[Dict[str, Any]],
        valor_nuevo: Optional[Dict[str, Any]],
        motivo: str
    ) -> str:
        payload = {
            "timestamp": timestamp_iso,
            "usuario_id": usuario_id,
            "accion": accion,
            "entidad": entidad,
            "entidad_id": entidad_id,
            "valor_anterior": valor_anterior,
            "valor_nuevo": valor_nuevo,
            "motivo": motivo
        }
        raw_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()

    @classmethod
    def registrar_evento(
        cls,
        db: Session,
        usuario_id: str,
        usuario_nombre: str,
        rol: str,
        ip_origen: str,
        accion: str,
        entidad: str,
        entidad_id: str,
        motivo_justificacion: str,
        valor_anterior: Optional[Dict[str, Any]] = None,
        valor_nuevo: Optional[Dict[str, Any]] = None,
    ) -> AuditoriaEvento:
        """
        Registra un evento inmutable con cálculo de firma SHA-256.
        """
        if not motivo_justificacion or not motivo_justificacion.strip():
            raise ValueError("El motivo/justificación es obligatorio para todo evento de auditoría.")

        now_utc = datetime.now(timezone.utc)
        sig_hash = cls._calcular_hash(
            timestamp_iso=now_utc.isoformat(),
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            motivo=motivo_justificacion.strip()
        )

        evento = AuditoriaEvento(
            timestamp_utc=now_utc,
            usuario_id=usuario_id,
            usuario_nombre=usuario_nombre,
            rol=rol,
            ip_origen=ip_origen,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            valor_anterior=valor_anterior,
            valor_nuevo=valor_nuevo,
            motivo_justificacion=motivo_justificacion.strip(),
            signature_hash=sig_hash
        )

        db.add(evento)
        db.commit()
        db.refresh(evento)
        return evento
