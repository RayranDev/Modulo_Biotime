# SIRH Plastitec — Módulo de Tiempos
## Fase 1: Documento de Diseño Arquitectónico (Carril A · Desbloqueado)
### Versión 1.0 · Septiembre 2026

---

## 1. ADR 001: Arquitectura Base y Stack Tecnológico

### Contexto
Plastitec SAS procesa ~1.000 empleados y ~2.200 marcaciones biométricas al día (~15.300 semanales) a través de 10 terminales BioTime 8.5. El sistema se despliega on-premise y es mantenido por un equipo interno de 2 desarrolladores.

### Decisión
Se adopta una arquitectura de **Monolito Modular** estructurado bajo principios de Clean/Hexagonal Architecture:
* **Lenguaje & Runtime:** Python 3.11+ (aprovechando tipado estricto con Pydantic v2 y rendimiento async).
* **Framework Web & API:** FastAPI (servidor HTTP ligero, documentación OpenAPI nativa, compatible con OIDC).
* **Persistencia:** PostgreSQL 16 (on-premise, soporte nativo de transacciones ACID, tipos `tstzrange` para intervalos temporales, y campos `JSONB` para snapshots de reglas).
* **ORM & Migraciones:** SQLAlchemy 2.0 (Core + ORM) y Alembic para versionado determinista de base de datos.
* **Scheduler de Ingesta:** APScheduler / BackgroundTasks internos en el proceso del servidor.
* **Frontend:** Servido desde FastAPI con plantillas Jinja2 y Vanilla JavaScript modular (sin frameworks SPA que añadan complejidad de empaquetado, facilitando el mantenimiento a 2 personas).

### Por qué NO Microservicios ni Colas Distribuidas (RabbitMQ / Redis / Celery)
1. **Volumen:** 2.200 transacciones/día representan menos de 0.03 transacciones por segundo en promedio. El histórico total de años (315.794 filas) cabe en menos de 100 MB de disco.
2. **Complejidad operativa:** Introducir brokers de mensajería, workers asíncronos y múltiples servicios distribuidos aumentaría exponencialmente la superficie de fallas en un despliegue on-premise mantenido por 2 personas.
3. **Consistencia Transaccional:** La auditoría y el pipeline de 6 etapas requieren transacciones atómicas estrictas que una base relacional unificada resuelve sin la complejidad de dos fases (2PC) ni transacciones compensatorias (Sagas).

---

## 2. Modelo de Identidad Multi-Sistema

Para evitar heurísticas frágiles de formateo de códigos (ceros a la izquierda), se establece una tabla de correspondencia explícita y auditable:

```sql
CREATE TABLE sys_identidad_empleado (
    id SERIAL PRIMARY KEY,
    sirh_emp_id VARCHAR(50) NOT NULL UNIQUE,          -- ID único en SIRH central
    biotime_emp_id INTEGER NOT NULL UNIQUE,          -- ID numérico interno de BioTime (ej. 1281)
    biotime_emp_code VARCHAR(50) NOT NULL UNIQUE,    -- Código de marcación en reloj (ej. "7334")
    sinergy_emp_code VARCHAR(50) NOT NULL UNIQUE,    -- Código de nómina en Sinergy (ej. "8639")
    tipo_vinculacion VARCHAR(30) NOT NULL,          -- 'DIRECTO', 'GRANSERVICIOS', 'SENA'
    es_activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_el TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_identidad_biotime_code ON sys_identidad_empleado (biotime_emp_code);
CREATE INDEX idx_identidad_sinergy_code ON sys_identidad_empleado (sinergy_emp_code);
```

---

## 3. Esquema de Datos del Pipeline de 6 Etapas (Inmutable y Persistido)

Cada etapa almacena su estado sin sobreescribir la anterior, garantizando reproducibilidad y trazabilidad completa.

```
┌────────────────────────────────────────────────────────┐
│ Etapa 1: marcacion_cruda                               │
│ (Inmutable, PK natural = biotime_trans_id)             │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Etapa 2: marcacion_normalizada                         │
│ (Emparejamiento IN/OUT, filtros, corrección humana)   │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Etapa 3: jornada_resuelta                              │
│ (Cruce vs Turno SIRH, imputación a día inicio, almuerzo)│
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Etapa 4: segmento_temporal                             │
│ (Partición atómica por fronteras: 19:00, 00:00, etc.)   │
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Etapa 5: clasificacion_segmento                        │
│ (Pasada 1: diaria · Pasada 2: 42h · Pasada 3: descansos)│
└────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Etapa 6: agregacion_diaria / resultado_periodo         │
│ (Conceptos consolidados para aprobación y exportación) │
└────────────────────────────────────────────────────────┘
```

### Definición DDL de las Etapas

```sql
-- ETAPA 1: Transacción cruda de BioTime
CREATE TABLE rrhh_marcacion_cruda (
    biotime_trans_id BIGINT PRIMARY KEY,              -- ID único nativo de BioTime (ej. 423969)
    emp_code VARCHAR(50) NOT NULL,
    punch_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,  -- Fecha/hora reportada por el dispositivo
    upload_time TIMESTAMP WITHOUT TIME ZONE NOT NULL, -- Fecha/hora de sincronización al servidor
    punch_state VARCHAR(10) NOT NULL,                -- '0' (In), '1' (Out), '255' (Auto)
    verify_type INTEGER,
    terminal_sn VARCHAR(50) NOT NULL,
    terminal_alias VARCHAR(100),
    area_alias VARCHAR(100),
    raw_payload JSONB NOT NULL,                       -- Snapshot del JSON exacto recibido de la API
    ingestado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cruda_emp_punch ON rrhh_marcacion_cruda (emp_code, punch_time);
CREATE INDEX idx_cruda_upload ON rrhh_marcacion_cruda (upload_time);

-- ETAPA 2: Marcación Normalizada
CREATE TABLE rrhh_marcacion_normalizada (
    id BIGSERIAL PRIMARY KEY,
    biotime_trans_id BIGINT REFERENCES rrhh_marcacion_cruda(biotime_trans_id),
    empleado_id INTEGER NOT NULL REFERENCES sys_identidad_empleado(id),
    timestamp_efectivo TIMESTAMPTZ NOT NULL,
    tipo_evento VARCHAR(20) NOT NULL,                -- 'ENTRADA', 'SALIDA', 'INDETERMINADO'
    es_duplicada BOOLEAN NOT NULL DEFAULT FALSE,
    es_manual BOOLEAN NOT NULL DEFAULT FALSE,
    justificacion_id INTEGER,                        -- FK a tabla de justificaciones si fue creada/editada
    procesado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ETAPA 3: Jornada Resuelta (Asignada a Programación)
CREATE TABLE rrhh_jornada_resuelta (
    id BIGSERIAL PRIMARY KEY,
    empleado_id INTEGER NOT NULL REFERENCES sys_identidad_empleado(id),
    fecha_imputacion DATE NOT NULL,                  -- DÍA DE INICIO DEL TURNO (Regla D3 / §3)
    turno_programado_id INTEGER,                     -- FK a rrhh_turno (nullable si no tenía turno)
    inicio_programado TIMESTAMPTZ,
    fin_programado TIMESTAMPTZ,
    inicio_real TIMESTAMPTZ,                         -- Entrada efectiva emparejada
    fin_real TIMESTAMPTZ,                            -- Salida efectiva emparejada
    minutos_trabajados_brutos INTEGER NOT NULL,
    minutos_descuento_almuerzo INTEGER NOT NULL DEFAULT 0,
    minutos_trabajados_netos INTEGER NOT NULL,
    estado_comcomitancia VARCHAR(30) NOT NULL,       -- 'COMPLETO', 'SIN_ENTRADA', 'SIN_SALIDA', 'NOVEDAD'
    calculado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ETAPA 4: Segmentación Temporal Atómica
CREATE TABLE rrhh_segmento_temporal (
    id BIGSERIAL PRIMARY KEY,
    jornada_id BIGINT NOT NULL REFERENCES rrhh_jornada_resuelta(id) ON DELETE CASCADE,
    inicio TIMESTAMPTZ NOT NULL,
    fin TIMESTAMPTZ NOT NULL,
    duracion_minutos INTEGER NOT NULL,
    tipo_franja VARCHAR(20) NOT NULL,               -- 'DIURNO', 'NOCTURNO' (según frontera vigente)
    tipo_dia VARCHAR(30) NOT NULL,                  -- 'ORDINARIO', 'DOMINICAL', 'FESTIVO', 'DESCANSO'
    es_dentro_jornada BOOLEAN NOT NULL,             -- True si cae dentro del horario programado
    novedad_id INTEGER                              -- Si cruza con lactancia o permiso
);

-- ETAPA 5: Clasificación de Segmentos
CREATE TABLE rrhh_clasificacion_segmento (
    id BIGSERIAL PRIMARY KEY,
    segmento_id BIGINT NOT NULL REFERENCES rrhh_segmento_temporal(id) ON DELETE CASCADE,
    calculo_id UUID NOT NULL,                        -- ID del lote de cálculo para reproducibilidad
    concepto_dominio VARCHAR(50) NOT NULL,          -- Ej. 'EXTRA_DIURNA_ORD', 'RECARGO_NOCTURNO'
    horas_clasificadas NUMERIC(6, 2) NOT NULL,
    regla_version_id INTEGER NOT NULL,               -- Snapshot de la versión de regla legal/política aplicada
    pasada_clasificacion SMALLINT NOT NULL           -- 1 (Diaria), 2 (Semanal 42h), 3 (Mensual Habitual)
);

-- ETAPA 6: Agregación por Jornada y Período
CREATE TABLE rrhh_resultado_diario_aprobacion (
    id BIGSERIAL PRIMARY KEY,
    empleado_id INTEGER NOT NULL REFERENCES sys_identidad_empleado(id),
    fecha_imputacion DATE NOT NULL,
    periodo_id INTEGER NOT NULL,
    concepto_dominio VARCHAR(50) NOT NULL,
    cantidad_horas NUMERIC(6, 2) NOT NULL,
    estado_aprobacion VARCHAR(20) NOT NULL,         -- 'PENDIENTE', 'APROBADO', 'AJUSTADO', 'RECHAZADO'
    supervisor_aprobador_id INTEGER,
    ajuste_horas NUMERIC(6, 2),
    justificacion_ajuste TEXT,
    aprobado_el TIMESTAMPTZ,
    UNIQUE (empleado_id, fecha_imputacion, concepto_dominio, periodo_id)
);
```

---

## 4. Modelo de Turnos, Ciclos y Programación en SIRH

Dado que BioTime solo contiene asignaciones estáticas por rango sin ciclos automáticos, SIRH implementa el motor de ciclos:

```sql
-- Catálogo de Turnos
CREATE TABLE rrhh_turno (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) NOT NULL UNIQUE,             -- Ej. 'T_12H_NOCHE', 'T_0730_1700'
    alias VARCHAR(100) NOT NULL,
    hora_inicio TIME NOT NULL,
    duracion_minutos INTEGER NOT NULL,              -- Se modela como duración para resolver salida con fecha completa
    descuenta_almuerzo BOOLEAN NOT NULL DEFAULT FALSE,
    minutos_almuerzo INTEGER NOT NULL DEFAULT 60,
    tolerancia_entrada_minutos INTEGER NOT NULL DEFAULT 15,
    tolerancia_salida_minutos INTEGER NOT NULL DEFAULT 15,
    es_rotativo BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- Definición de Ciclos Rotativos (Ej. Ciclo 4x3 de 7 días: Día 1 T1, Día 2 T1, Día 3 T2, Día 4 T2, Días 5-7 Descanso)
CREATE TABLE rrhh_ciclo_rotativo (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    duracion_dias INTEGER NOT NULL DEFAULT 7
);

CREATE TABLE rrhh_ciclo_detalle_dia (
    id SERIAL PRIMARY KEY,
    ciclo_id INTEGER NOT NULL REFERENCES rrhh_ciclo_rotativo(id) ON DELETE CASCADE,
    dia_indice INTEGER NOT NULL,                    -- 1 a N
    turno_id INTEGER REFERENCES rrhh_turno(id),      -- NULL indica Día de Descanso Obligatorio
    es_descanso BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (ciclo_id, dia_indice)
);

-- Asignación de Programación a Empleados
CREATE TABLE rrhh_programacion_empleado (
    id BIGSERIAL PRIMARY KEY,
    empleado_id INTEGER NOT NULL REFERENCES sys_identidad_empleado(id),
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    ciclo_id INTEGER REFERENCES rrhh_ciclo_rotativo(id),
    turno_fijo_id INTEGER REFERENCES rrhh_turno(id), -- Para administrativos que no rotan
    dia_inicio_ciclo INTEGER DEFAULT 1,              -- En qué día del ciclo arranca el fecha_inicio
    creado_por INTEGER NOT NULL,
    creado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 5. Ciclo de Vida del Período y Aprobación Continua

### Máquina de Estados del Período Mensual (11 → 10)
```
  [ ABIERTO ]  (Día 11 al 10)
       │       · Motor calcula a diario
       │       · Supervisores aprueban continuamente por excepción
       ▼
  [ EN_PROCESAMIENTO_RRHH ]  (Día 11)
       │       · Bloqueo total de modificaciones para supervisores
       │       · RRHH revisa pendientes, inconsistencias o aprueba por sustitución
       ▼
  [ CERRADO ]  (Día 11 o 12)
       │       · Se genera el archivo plano FINAL_SINER_*.txt
       │       · Hash criptográfico del archivo guardado en base de datos
       ▼ (Excepción controlada: rol Admin + motivo + traza)
  [ REABIERTO_AUDITADO ]
```

### Modelo de Alcance de Supervisores
Un supervisor solo puede visualizar y aprobar empleados que pertenezcan a su alcance organizacional (Área o Departamento):

```sql
CREATE TABLE rrhh_supervisor_alcance (
    id SERIAL PRIMARY KEY,
    supervisor_usuario_id INTEGER NOT NULL,          -- Usuario autenticado en SIRH
    departamento_id VARCHAR(50),
    area_id VARCHAR(50),
    cargo_id VARCHAR(50),
    es_activo BOOLEAN NOT NULL DEFAULT TRUE,
    asignado_el TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 6. Contratos de Adaptadores (Puertos e Interfaces)

### Puerto de Ingesta BioTime (`BioTimePort`)
* `extraer_marcaciones_incrementales(desde_upload_time: datetime) -> List[RawTransactionDTO]`
  - Filtra por `upload_time` >= última marca de agua.
  - Inserta con `ON CONFLICT (biotime_trans_id) DO NOTHING` para garantizar estricta idempotencia.
* `crear_empleado_biotime(emp: EmpleadoDTO) -> bool`
  - Ejecuta `POST /personnel/api/employees/`.
* `dar_baja_empleado_biotime(biotime_emp_id: int, motivo: str) -> bool`
  - Ejecuta `PATCH /personnel/api/employees/{id}/` marcando estado inactivo/retiro.

### Puerto de Nómina Sinergy (`PayrollExportPort`)
* `generar_archivo_plano(periodo_id: int) -> ExportResultDTO`
  - Resuelve códigos según la fecha del período (ej. `0253` vs `0252` a partir del 15-jul-2026).
  - Estructura: 12 columnas delimitadas por TAB, UTF-8, LF.
  - Genera archivo con nomenclatura `FINAL_SINER_<YYYY-MM-DD>_<YYYY-MM-DD>.txt`.

---

## 7. Arquitectura de Auditoría y Seguridad

Para satisfacer normativas de calidad ISO 9001 y estar preparados para estándares farmacéuticos:

```sql
CREATE TABLE sys_auditoria_trazabilidad (
    id BIGSERIAL PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usuario_id VARCHAR(50) NOT NULL,                 -- Cuenta nominal individual
    usuario_nombre VARCHAR(100) NOT NULL,
    rol VARCHAR(50) NOT NULL,
    ip_origen VARCHAR(45) NOT NULL,
    accion VARCHAR(50) NOT NULL,                     -- 'APROBAR', 'AJUSTAR', 'RECHAZAR', 'CERRAR_PERIODO'
    entidad VARCHAR(50) NOT NULL,                    -- 'jornada_resuelta', 'periodo', etc.
    entidad_id VARCHAR(50) NOT NULL,
    valor_anterior JSONB,
    valor_nuevo JSONB,
    motivo_justificacion TEXT NOT NULL,              -- OBLIGATORIO en todo ajuste
    signature_hash VARCHAR(64)                       -- SHA-256 (timestamp + usuario + accion + valores)
);

-- Regla de base de datos para impedir UPDATE o DELETE en auditoría
CREATE RULE regla_no_update_auditoria AS ON UPDATE TO sys_auditoria_trazabilidad DO INSTEAD NOTHING;
CREATE RULE regla_no_delete_auditoria AS ON DELETE TO sys_auditoria_trazabilidad DO INSTEAD NOTHING;
```

---

## 8. Estado del Carril A y Próximo Hito

* **Carril A:** El diseño estructural, persistencia de 6 etapas, contratos de interfaz, modelos de turnos/ciclos y seguridad quedan formalizados sin requerir supuestos no verificados.
* **Carril B (En espera):** Permanece congelado hasta recibir los casos dorados y las definiciones de RRHH/Jurídico (Semana partida, Matriz Festivo x Descanso, Sustento de 12 horas).
