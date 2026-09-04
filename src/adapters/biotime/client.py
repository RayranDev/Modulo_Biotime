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

    def _get_paginado(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Descarga todas las páginas de un endpoint en BioTime."""
        if not self.token:
            self.autenticar()

        url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else f"{self.base_url}/{endpoint}"
        p = dict(params or {})
        p.setdefault("page_size", settings.BIOTIME_PAGE_SIZE)
        p["page"] = 1

        resultados = []
        while True:
            resp = self.session.get(url, params=p, timeout=self.timeout, verify=self.verify)
            resp.raise_for_status()
            data = resp.json()
            filas = data.get("data") or data.get("results") or []
            resultados.extend(filas)
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
