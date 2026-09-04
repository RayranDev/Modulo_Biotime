"""
Adaptador BioTime 8.5 tipado y seguro.
El dominio jamás conoce rutas ni detalles internos de BioTime.
"""
from typing import List, Dict, Any, Optional
import requests
import urllib3
from src.core.config import settings

if not settings.BIOTIME_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BioTimeAdapter:
    def __init__(
        self,
        base_url: str = settings.BIOTIME_BASE_URL,
        usuario: str = settings.BIOTIME_USER,
        clave: str = settings.BIOTIME_PASS,
        timeout: int = settings.BIOTIME_TIMEOUT,
        verify_ssl: bool = settings.BIOTIME_VERIFY_SSL,
    ):
        self.base_url = base_url.rstrip("/")
        self.usuario = usuario
        self.clave = clave
        self.timeout = timeout
        self.verify = verify_ssl
        self.token: Optional[str] = None
        self.session = requests.Session()

    def autenticar(self) -> "BioTimeAdapter":
        """Obtiene JWT de BioTime 8.5."""
        url = f"{self.base_url}/jwt-api-token-auth/"
        resp = self.session.post(
            url,
            json={"username": self.usuario, "password": self.clave},
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
            verify=self.verify,
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data.get("token") or data.get("access") or data.get("jwt")
        if not self.token:
            raise RuntimeError("BioTime no retornó un token JWT válido.")

        self.session.headers.update({
            "Authorization": f"JWT {self.token}",
            "Content-Type": "application/json",
        })
        return self

    def _get_paginado(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        max_paginas: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Descarga páginas de un endpoint en BioTime con límite de seguridad."""
        if not self.token:
            self.autenticar()

        url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else f"{self.base_url}/{endpoint}"
        p = dict(params or {})
        p.setdefault("page_size", settings.BIOTIME_PAGE_SIZE)
        p["page"] = 1

        resultados = []
        paginas_leidas = 0
        while True:
            resp = self.session.get(url, params=p, timeout=self.timeout, verify=self.verify)
            resp.raise_for_status()
            data = resp.json()
            filas = data.get("data") or data.get("results") or []
            resultados.extend(filas)
            paginas_leidas += 1

            if max_paginas and paginas_leidas >= max_paginas:
                break
            if not data.get("next"):
                break
            p["page"] += 1

        return resultados

    def obtener_turnos(self) -> List[Dict[str, Any]]:
        """Lee los turnos configurados en BioTime (/att/api/attshifts/)."""
        return self._get_paginado("/att/api/attshifts/")

    def obtener_intervalos(self) -> List[Dict[str, Any]]:
        """Lee los intervalos de tiempo en BioTime (/att/api/timeintervals/)."""
        return self._get_paginado("/att/api/timeintervals/")

    def obtener_detalles_turnos(self) -> List[Dict[str, Any]]:
        """Lee la relación entre turnos e intervalos (/att/api/shift_details/)."""
        return self._get_paginado("/att/api/shift_details/")

    def obtener_empleados(self) -> List[Dict[str, Any]]:
        """Lee los empleados registrados en BioTime (/personnel/api/employees/)."""
        return self._get_paginado("/personnel/api/employees/")

    def obtener_transacciones(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        page_size: Optional[int] = None,
        max_paginas: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lee transacciones crudas desde BioTime (/iclock/api/transactions/).
        Soporta filtrado por start_time y end_time ('YYYY-MM-DD HH:MM:SS').
        """
        params: Dict[str, Any] = {}
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if page_size:
            params["page_size"] = page_size

        return self._get_paginado("/iclock/api/transactions/", params=params, max_paginas=max_paginas)


    def crear_empleado(self, emp_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea un nuevo empleado en BioTime 8.5 mediante POST a /personnel/api/employees/.
        Cumple con la decisión D17.
        """
        if not self.token:
            self.autenticar()

        url = f"{self.base_url}/personnel/api/employees/"
        resp = self.session.post(url, json=emp_data, timeout=self.timeout, verify=self.verify)
        resp.raise_for_status()
        return resp.json()

    def dar_baja_empleado(self, biotime_emp_id: int, motivo: str = "Retiro / Renuncia") -> Dict[str, Any]:
        """
        Actualiza el estado de un empleado en BioTime a baja/inactivo (D17).
        Usa PATCH nativo en /personnel/api/employees/{id}/.
        """
        if not self.token:
            self.autenticar()

        url = f"{self.base_url}/personnel/api/employees/{biotime_emp_id}/"
        payload = {
            "is_active": False,
            "status": "3",  # En BioTime 3 suele ser 'Resigned' / 'Baja'
        }
        resp = self.session.patch(url, json=payload, timeout=self.timeout, verify=self.verify)
        # Si el status code es 200 o 204, fue exitoso
        if resp.status_code in (200, 204):
            return resp.json() if resp.text else {"status": "ok", "id": biotime_emp_id}
        resp.raise_for_status()
        return resp.json()

