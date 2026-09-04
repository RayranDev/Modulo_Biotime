"""
Servicio de Conciliación y Comparador para Ejecución en Paralelo (Fase 7).
Compara 'lo que calcula nuestro motor' vs 'lo que reporta BioTime (dailyHourReport)'
y clasifica discrepancias esperadas (P1 42h y P4 Redondeo) vs alertas a investigar.
"""
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.domain.models.calculo import JornadaResuelta, ResultadoDiario
from src.domain.models.identidad import Empleado, MapeoIdentidad
from src.adapters.biotime.client import BioTimeAdapter


class ComparadorParaleloService:
    @classmethod
    def conciliar_jornadas_vs_biotime(
        cls,
        db: Session,
        fecha_inicio: date,
        fecha_fin: date,
        emp_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta la conciliación entre el cálculo de SIRH y los reportes testigo de BioTime.
        Identifica discrepancias legítimas por reglas de negocio (P1 y P4) vs bugs o desvíos.
        """
        adapter = BioTimeAdapter().autenticar()

        # 1. Obtener reporte testigo de BioTime (/att/api/dailyHourReport/)
        params = {
            "start_date": fecha_inicio.isoformat(),
            "end_date": fecha_fin.isoformat(),
            "page_size": 1000,
        }
        if emp_code:
            params["emp_code"] = emp_code

        try:
            raw_biotime = adapter._get_paginado("/att/api/dailyHourReport/", params=params, max_paginas=10)
        except Exception as e:
            raw_biotime = []

        biotime_map: Dict[Tuple[str, str], float] = {}
        for r in raw_biotime:
            code = str(r.get("emp_code") or "").strip()
            f_str = str(r.get("att_date") or "").strip()
            total_h = float(r.get("work_time") or r.get("total_time") or 0.0)
            if code and f_str:
                biotime_map[(code, f_str)] = total_h

        # 2. Consultar jornadas resueltas en SIRH
        query = (
            db.query(JornadaResuelta)
            .join(Empleado, JornadaResuelta.empleado_id == Empleado.id)
            .join(MapeoIdentidad, Empleado.id == MapeoIdentidad.empleado_id)
            .filter(
                JornadaResuelta.fecha_imputacion >= fecha_inicio,
                JornadaResuelta.fecha_imputacion <= fecha_fin,
            )
        )
        if emp_code:
            query = query.filter(MapeoIdentidad.biotime_emp_code == emp_code)

        jornadas_sirh = query.all()

        conciliaciones = []
        total_coincidencias = 0
        total_desvios_esperados = 0
        total_discrepancias = 0

        for j in jornadas_sirh:
            code = j.empleado.mapeo.biotime_emp_code if hasattr(j.empleado, "mapeo") and j.empleado.mapeo else j.empleado.sirh_emp_id
            f_str = j.fecha_imputacion.isoformat()
            horas_sirh = round(j.minutos_trabajados_netos / 60.0, 2)
            horas_bt = biotime_map.get((code, f_str), 0.0)

            delta = round(horas_sirh - horas_bt, 2)

            if abs(delta) == 0.0:
                diagnostico = "COINCIDENCIA_EXACTA"
                total_coincidencias += 1
            elif abs(delta) == 1.0 and j.minutos_descuento_almuerzo == 60:
                diagnostico = "DIFERENCIA_ESPERADA_DESCUENTO_ALMUERZO"
                total_desvios_esperados += 1
            elif abs(delta) in (0.5, 1.0, 1.5, 2.0):
                diagnostico = "DIFERENCIA_ESPERADA_P4_REDONDEO"
                total_desvios_esperados += 1
            else:
                diagnostico = "DISCREPANCIA_A_INVESTIGAR"
                total_discrepancias += 1

            conciliaciones.append({
                "emp_code": code,
                "fecha": f_str,
                "horas_sirh": horas_sirh,
                "horas_biotime": horas_bt,
                "delta": delta,
                "diagnostico": diagnostico,
                "estado_jornada": j.estado_jornada,
            })

        return {
            "rango": f"{fecha_inicio.isoformat()} a {fecha_fin.isoformat()}",
            "total_evaluadas": len(conciliaciones),
            "coincidencias": total_coincidencias,
            "desvios_explicables_p1_p4": total_desvios_esperados,
            "discrepancias_a_investigar": total_discrepancias,
            "detalle": conciliaciones[:100], # Muestra de hasta 100 filas
        }
