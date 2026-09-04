"""
Adaptador de Exportación para Sinergy Nómina (Fase 6).
Genera el archivo plano oficial FINAL_SINER_<YYYY-MM-DD>_<YYYY-MM-DD>.txt
con mapeo de códigos versionado por fecha (Caso 25 / §10.2).
"""
import hashlib
from datetime import date
from typing import List, Dict, Any, Tuple
from decimal import Decimal


def _formatear_fecha_sinergy(d: date) -> str:
    """Formato D/MM/YYYY requerido por Sinergy (ej. 11/09/2026 o 1/10/2026)."""
    return f"{d.day}/{d.month:02d}/{d.year}"


def _formatear_cantidad(horas: float) -> str:
    """Formato decimal de horas sin ceros superfluos (ej. 6.5 o 12)."""
    val = round(float(horas), 2)
    if val.is_integer():
        return str(int(val))
    # Quitar ceros a la derecha si es ej. 6.50 -> 6.5
    s = f"{val:.2f}".rstrip("0").rstrip(".")
    return s


class SinergyExporterAdapter:
    # Fecha de corte de la reforma de recargo dominical (Ley 2466 / 2101)
    FECHA_ESCALON_RECARGO = date(2026, 7, 15)

    @classmethod
    def resolver_codigo_concepto(cls, concepto_dominio: str, fecha_periodo: date) -> str:
        """
        Resuelve el código de 4 dígitos de Sinergy según la fecha del período (§10.2).
        Antes del 15-jul-2026: Dominical = 0253, Nocturno Festivo = 0259
        Desde el 15-jul-2026: Dominical = 0252, Nocturno Festivo = 0258
        """
        c = str(concepto_dominio).strip().upper()

        if c in ("RECARGO_DOMINICAL_FESTIVO", "RECARGO_DOMINICAL", "0252", "0253"):
            return "0252" if fecha_periodo >= cls.FECHA_ESCALON_RECARGO else "0253"

        if c in ("RECARGO_NOCTURNO_FESTIVO", "0258", "0259"):
            return "0258" if fecha_periodo >= cls.FECHA_ESCALON_RECARGO else "0259"

        if c in ("EXTRA_DIURNA_ORD", "HEDO", "0200"):
            return "0200"

        if c in ("EXTRA_NOCTURNA_ORD", "HENO", "0210"):
            return "0210"

        if c in ("EXTRA_DIURNA_FEST", "HEDF", "0250"):
            return "0250"

        if c in ("EXTRA_NOCTURNA_FEST", "HENF", "0260"):
            return "0260"

        if c in ("RECARGO_NOCTURNO", "RN", "0220"):
            return "0220"

        # Si ya es un código de 4 dígitos, retornarlo con zero-fill
        if c.isdigit():
            return f"{int(c):04d}"

        raise ValueError(f"Concepto de dominio desconocido para Sinergy: '{concepto_dominio}'")

    @classmethod
    def generar_linea_plano(
        cls,
        sinergy_emp_code: str,
        concepto_codigo: str,
        fecha_inicio: date,
        fecha_fin: date,
        cantidad_horas: float,
    ) -> str:
        """
        Estructura de 12 campos delimitados por TAB:
        1: Código empleado en Sinergy (numérico sin ceros a la izquierda)
        2: Código concepto (4 dígitos)
        3: '+'
        4: Fecha inicio (D/MM/YYYY)
        5: Cantidad (decimal máx 2)
        6: Fecha fin (D/MM/YYYY)
        7 a 12: Vacíos
        """
        emp_clean = str(int(sinergy_emp_code)) if sinergy_emp_code.isdigit() else sinergy_emp_code.strip()
        f_ini_str = _formatear_fecha_sinergy(fecha_inicio)
        f_fin_str = _formatear_fecha_sinergy(fecha_fin)
        cant_str = _formatear_cantidad(cantidad_horas)

        campos = [
            emp_clean,           # 1
            concepto_codigo,     # 2
            "+",                 # 3
            f_ini_str,           # 4
            cant_str,            # 5
            f_fin_str,           # 6
            "",                  # 7
            "",                  # 8
            "",                  # 9
            "",                  # 10
            "",                  # 11
            "",                  # 12
        ]
        return "\t".join(campos)

    @classmethod
    def generar_archivo_plano(
        cls,
        fecha_inicio: date,
        fecha_fin: date,
        registros_agrupados: List[Dict[str, Any]],
    ) -> Tuple[str, str, str, float]:
        """
        Genera el archivo plano completo para Sinergy.
        Retorna: (nombre_archivo, contenido_txt, hash_sha256, total_horas)
        """
        lineas = []
        total_horas = 0.0

        for reg in registros_agrupados:
            sinergy_code = str(reg["sinergy_emp_code"])
            concepto_dom = str(reg["concepto_dominio"])
            horas = float(reg["cantidad_horas"])
            if horas <= 0:
                continue

            codigo_sinergy = cls.resolver_codigo_concepto(concepto_dom, fecha_fin)
            linea = cls.generar_linea_plano(
                sinergy_emp_code=sinergy_code,
                concepto_codigo=codigo_sinergy,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                cantidad_horas=horas,
            )
            lineas.append(linea)
            total_horas += horas

        # Fin de línea LF estricto (\n)
        contenido_txt = "\n".join(lineas)
        if contenido_txt:
            contenido_txt += "\n"

        # Nombre del archivo estándar recuperado del generador actual
        nombre_archivo = f"FINAL_SINER_{fecha_inicio.isoformat()}_{fecha_fin.isoformat()}.txt"

        # Hash criptográfico SHA-256 para auditoría de calidad
        hash_sha256 = hashlib.sha256(contenido_txt.encode("utf-8")).hexdigest()

        return nombre_archivo, contenido_txt, hash_sha256, round(total_horas, 2)
