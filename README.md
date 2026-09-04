# SIRH Plastitec — Módulo de Tiempos y Asistencia
### Versión 3.0 · Integración BioTime 8.5 & Sinergy Nómina

Sistema de gestión de tiempos, control de turnos rotativos, cálculo de horas extras bajo umbral de 42h semanales, aprobación continua por supervisores y exportador oficial a Sinergy Nómina.

---

## 📌 Visión General

El proyecto reemplaza el circuito de planillas físicas en papel de ~1.000 empleados en Plastitec SAS, reduciendo el ciclo mensual de liquidación de variables de **10 días a 1 o 2 días**.

### Arquitectura de Integración
```
┌────────────────────────────────────────────────────────┐
│  BIOTIME 8.5 · Pasarela de Dispositivos y Captura      │
│  Terminales biométricas · Enrolamiento · Marcaciones   │
│  (Se conserva intacto, sin tocar su motor)             │
└────────────────────────────────────────────────────────┘
                           │
                           ▼ API REST (Marcaciones crudas)
┌────────────────────────────────────────────────────────┐
│  MÓDULO DE TIEMPOS SIRH (`src/`) · Lo que se construye │
│  - Pipeline persistido de 6 etapas                     │
│  - Dueño de turnos, ciclos (4x3) y calendarios         │
│  - Motor de cálculo: umbral semanal 42h y redondeos    │
│  - Bandeja de aprobación continua por supervisor       │
│  - Auditoría inmutable con firmas SHA-256              │
│  - Ciclo de períodos 11 al 10 con bloqueo de RRHH      │
└────────────────────────────────────────────────────────┘
                           │
                           ▼ Archivo plano (FINAL_SINER_*.txt)
┌────────────────────────────────────────────────────────┐
│  SINERGY · Nómina                                      │
│  (Calcula el dinero y liquida conceptos)               │
└────────────────────────────────────────────────────────┘
```

---

## 🏗️ Estructura del Proyecto

El sistema nuevo vive de forma completamente aislada en el paquete **`src/`**, manteniendo los scripts raíz (`server.py`, `biotime_api.py`) como visor exploratorio previo:

```text
MODULO_BIOTIME/
├── src/                               # NUEVO MÓDULO SIRH (Clean Architecture)
│   ├── core/                          # Configuración, DB y auditoría inmutable
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── audit.py                   # Registro append-only con SHA-256
│   │   └── init_db.py
│   ├── domain/models/                 # Modelos de Dominio SQLAlchemy
│   │   ├── identidad.py               # Identidad multi-sistema (SIRH/BioTime/Sinergy)
│   │   ├── turno.py                   # Turnos, Ciclos (4x3) y Programación
│   │   ├── regla.py                   # Reglas laborales versionadas por fecha
│   │   ├── asistencia.py              # Etapas 1 (Cruda) y 2 (Normalizada)
│   │   ├── calculo.py                 # Etapas 3, 4, 5 y 6 (Pipeline y 42h)
│   │   ├── novedad.py                 # Condiciones especiales (Lactancia)
│   │   ├── periodo.py                 # Ciclo 11→10 y exportaciones
│   │   └── auditoria.py               # Tabla sys_auditoria_trazabilidad
│   ├── adapters/                      # Adaptadores externos aislados
│   │   ├── biotime/client.py          # Cliente REST BioTime 8.5 (Ingesta/Altas/Bajas)
│   │   └── sinergy/exporter.py        # Generador de archivo plano con mapeo por fecha
│   ├── services/                      # Lógica de Negocio y Casos de Uso
│   │   ├── catalogo_service.py        # Importación de turnos e inicialización de reglas
│   │   ├── ingesta_service.py         # Sincronización idempotente de marcaciones
│   │   ├── motor_calculo.py           # Pipeline de 6 etapas y umbral de 42h
│   │   ├── aprobacion_service.py      # Bandeja de supervisores y aprobación por excepción
│   │   ├── periodo_service.py         # Máquina de estados 11→10 y exportación
│   │   └── comparador_service.py      # Conciliador de ejecución en paralelo vs BioTime
│   └── main.py                        # API FastAPI con documentación Swagger/OpenAPI
├── tests/                             # Suite de Pruebas Unitarias e Integración (Pytest)
│   ├── conftest.py                    # Fixture DB SQLite en memoria
│   ├── test_fase2_nucleo.py           # Pruebas de identidad, turnos y auditoría
│   ├── test_fase3_contrato_biotime.py # Pruebas de contrato contra BioTime 8.5
│   ├── test_fase3_ingesta.py          # Pruebas de idempotencia y rebote
│   ├── test_fase4_calculo.py          # Pruebas de redondeo, segmentación y 42h
│   ├── test_fase5_aprobacion.py       # Pruebas de aprobación y lactancia
│   ├── test_fase6_periodos_exportacion.py # Pruebas de exportador Sinergy y bloqueo RRHH
│   └── test_fase7_api_paralelo.py     # Pruebas de API y comparador paralelo
├── docs/
│   └── FASE-1-DISENO-CARRIL-A.md      # Especificación arquitectónica base
├── requirements.txt                   # Dependencias del proyecto
└── pytest.ini                         # Configuración de pytest
```

---

## ⚙️ Puesta en Marcha

### 1. Activar Entorno Virtual
```powershell
.\venv\Scripts\Activate.ps1
```

### 2. Ejecutar la Suite de Pruebas Automatizadas
Para correr los 26 tests unitarios y de integración:
```powershell
pytest tests/ -v
```

### 3. Inicializar la Base de Datos y Catálogo
```powershell
python -m src.core.init_db
```

### 4. Iniciar el Servidor API FastAPI
```powershell
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Acceso:
- **Swagger UI**: `http://localhost:8000/docs`
- **Redoc**: `http://localhost:8000/redoc`

---

## 🎯 Reglas Clave Implementadas

1. **Umbral Semanal de 42 Horas (Ley 2101 de 2021 / P1):**
   Para personal rotativo, las primeras 42 horas acumuladas de lunes a domingo son ordinarias; a partir de la hora 42.0 se reclasifican a horas extras.
2. **Redondeo de Extras (P4 / §4):**
   Cortes en los minutos `:25` y `:50` con incrementos de media hora.
3. **Condición Especial de Lactancia (P2 / Caso 19):**
   Jornada de 8 horas con 7 horas trabajadas computa las 8 horas completas.
4. **Ciclo de Variables 11 al 10 y Bloqueo de RRHH:**
   El día 11 RRHH inicia el procesamiento y bloquea modificaciones de supervisores para emitir el archivo plano oficial de Sinergy.
5. **Mapeo de Conceptos Versionado por Fecha (Caso 25):**
   A partir del 15 de julio de 2026, los recargos festivos se exportan con códigos `0252` y `0258` (y `0253`/`0259` para fechas anteriores).
6. **Auditoría Inmutable:**
   Toda acción de ajuste, aprobación o exportación exige justificación y genera un hash SHA-256 inalterable.
