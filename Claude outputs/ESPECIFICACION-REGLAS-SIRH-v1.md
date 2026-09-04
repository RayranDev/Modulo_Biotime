# ESPECIFICACIÓN DE REGLAS · SIRH Plastitec
### v1.0 · Septiembre 2026 · Derivada de las respuestas de RRHH y TI
### Documento para firma de RRHH y Jurídico antes de construir el motor

> Cada regla lleva su clasificación: `LEGAL` obligación de norma · `POLITICA` decisión de Plastitec · `CONVENCION` pacto sindical · `CONFIG` parámetro operativo · `PENDIENTE` sin resolver.
> Las marcadas ⚠️ tienen una observación que debe resolverse antes de codificar.

---

## 1. PERFILES LABORALES

| Perfil | Criterio | Regla de extras |
|---|---|---|
| **Operativo rotativo** | Personal de producción y planta con turnos rotativos. **Se determina por CARGO** | Umbral semanal de 42 h |
| **Administrativo** | El resto | Jornada administrativa estándar, cálculo diario |

`POLITICA` · La asignación de perfil se resuelve por **cargo**, no por empleado. Un cambio de cargo cambia el perfil automáticamente y debe quedar versionado con fecha.

**Grupos adicionales a modelar** — `PENDIENTE`:
- Temporales de **Granservicios** (EST). Marcan en las terminales. Definir si entran al archivo de Sinergy o solo al control de asistencia.
- **Practicantes SENA**. Definir jornada y reglas aplicables.

---

## 2. UMBRAL SEMANAL DE 42 HORAS — LA REGLA CENTRAL

**Enunciado confirmado:** para el personal operativo rotativo, toda hora trabajada por encima de **42 horas semanales** se considera extra, hasta el tope legal de **12 horas semanales**. La semana corre de **lunes a domingo**.

`POLITICA` sustentada en acuerdo contractual + otrosí.

### ⚠️ 2.1 Corrección de la fuente normativa

La jornada máxima de 42 horas semanales proviene de la **Ley 2101 de 2021**, no de la Ley 2466 de 2025. La Ley 2466 de 2025 modificó otras cosas —franja nocturna a las 19:00 y escalonamiento del recargo dominical— que también aplican, pero no es la fuente del umbral de 42 horas.

Debe corregirse en la documentación de la regla: **fuente = Ley 2101 de 2021, art. 3 · vigencia desde 15-jul-2026.**

### ⚠️ 2.2 Punto a validar con Jurídico — el mayor riesgo abierto del proyecto

Calcular las extras contra el acumulado semanal, y no contra la jornada diaria, significa que un día de exceso puede compensarse contra un día de déficit dentro de la misma semana. Eso solo es viable bajo figuras específicas del CST —jornada flexible del art. 161 lit. d, o turnos sucesivos— y **un acuerdo contractual no puede por sí solo renunciar a derechos mínimos legales**.

Existe además una tensión concreta que hay que resolver: **la jornada flexible del CST admite hasta 9 horas diarias sin recargo**, y los turnos rotativos de Plastitec son de **12 horas**. Un turno de 12 horas no encaja en esa figura.

**Preguntas exactas para Jurídico:**
1. ¿Qué figura del CST invoca el otrosí: jornada flexible, turnos sucesivos, u otra?
2. ¿Cómo se sustenta un turno de 12 horas bajo esa figura?
3. ¿El otrosí está firmado por todos los empleados del perfil rotativo, o solo por algunos?
4. ¿La convención colectiva vigente (§9) dice algo distinto? Si lo dice, **prevalece**.

Hasta tener esas respuestas, la regla queda `PENDIENTE DE VALIDACIÓN JURÍDICA` y se parametriza de forma que pueda cambiarse sin tocar código.

### 2.3 Comportamiento

| Situación | Resultado |
|---|---|
| Semana < 42 h | Sin extras. Se paga lo efectivamente trabajado |
| Semana > 42 h | El excedente es extra, hasta 12 h/semana |
| Excedente > 12 h/semana | Se calcula igual, **pero genera alerta con justificación obligatoria** |
| Turno incompleto por marcación faltante | Debe poder calcularse igualmente (§6) |

`POLITICA` · No hay umbral intermedio: todo lo que exceda 42 h entra como extra, sujeto a aprobación del jefe inmediato.

---

## 3. DÍA DE IMPUTACIÓN

`CONFIG` · **Un turno se imputa siempre al día en que INICIA**, sin importar cuántas horas caigan en el día siguiente.

Esto define la agregación. **No afecta la segmentación**: un turno 18:00–06:00 se sigue partiendo en segmentos por medianoche, por la frontera nocturna de las 19:00 y por el tipo de día, porque cada segmento puede tener un recargo distinto. Lo que se imputa al día de inicio es el *resultado*, no el cálculo.

---

## 4. REDONDEO DE HORAS EXTRAS

`CONFIG` global · Aplica **únicamente al tiempo posterior al fin del turno programado**.

**Puntos de corte: minutos `:25` y `:50` de cada hora de reloj.**

Ejemplo con turno que termina a las 17:00:

| Marcación de salida | Extra reconocida |
|---|---|
| 17:00 – 17:24 | 0 h |
| 17:25 – 17:49 | 0,5 h |
| 17:50 – 18:24 | 1,0 h |
| 18:25 – 18:49 | 1,5 h |
| 18:50 – 19:24 | 2,0 h |

El incremento es siempre de 0,5 h. En la práctica equivale a redondear al medio hora más cercano con 5 minutos de gracia a favor del trabajador.

### ⚠️ 4.1 Ambigüedad a resolver

¿Los cortes están anclados **al reloj** (siempre `:25` y `:50`) o **al fin del turno** (+25 y +50 minutos desde la hora de salida programada)?

Para un turno que termina en punto, ambas lecturas coinciden. Para uno que termina a las **14:30**, no:

| Interpretación | Primer corte | Segundo corte |
|---|---|---|
| Anclado al reloj | 14:50 | 15:25 |
| Anclado al fin de turno | 14:55 | 15:20 |

La secuencia que describió RRHH (25, 50, 85, 110 minutos) es **regular en el reloj e irregular en tiempo transcurrido**, lo que sugiere anclaje al reloj. **Confirmar con RRHH antes de codificar.**

### 4.2 Reglas asociadas

- `CONFIG` · El tiempo cuenta **desde el inicio del turno programado**, aunque el empleado marque mucho antes. Regla global.
- `CONFIG` · El redondeo se calcula **sobre la marcación real**, no sobre valores declarados.
- `CONFIG` · Las **tolerancias** sí son parametrizables y **no globales** — a diferencia del redondeo, que sí es global. `PENDIENTE`: ¿la parametrización es por cargo, por turno o por perfil?

---

## 5. DESCANSOS DENTRO DEL TURNO

| Concepto | Duración | Trato | Clasificación |
|---|---|---|---|
| **Almuerzo** | 60 min | **Se descuenta** de la jornada | `CONFIG` |
| **Café** | 20 min | **NO se descuenta.** La empresa lo paga | `POLITICA` |

`CONFIG` · El descuento de almuerzo **se habilita o deshabilita por turno**: algunos turnos rotativos no lo aplican. Debe ser un atributo de la definición del turno, no una regla global.

El café aplica principalmente a rotativos. `PENDIENTE`: ¿aplica también a administrativos? ¿Se marca o es implícito?

---

## 6. MARCACIÓN FALTANTE

`CONFIG` · El sistema debe hacer **dos cosas a la vez**:

1. **Señalarla como excepción visible** — no puede pasar en silencio.
2. **Permitir el cálculo automático** basándose en el turno programado, cuando se requiera.

Toda corrección exige **justificación tipificada**:

| Tipo de justificación |
|---|
| Permiso remunerado |
| Permiso no remunerado |
| Incapacidad |
| Otro (con texto obligatorio) |

Cada corrección queda trazada: autor, fecha, valor anterior, valor nuevo, justificación.

---

## 7. FESTIVOS Y DÍAS DE DESCANSO

**Principio confirmado:** `LEGAL` · **Para generar extras o recargos hay que trabajar.** Si el empleado no trabaja su día de descanso o el festivo, no se calcula nada — ese día ya está remunerado dentro del salario y lo liquida Sinergy.

### ⚠️ 7.1 Punto que debe precisarse antes de codificar

RRHH indicó que si el festivo cae sobre el día de descanso del empleado **y lo trabaja, "se toman como extras"**.

Hace falta precisión, porque la planilla actual tiene columnas separadas para *extra festiva* y para *recargo dominical o festivo*, y son conceptos distintos con códigos distintos en Sinergy. Trabajar en día de descanso obligatorio o festivo causa **recargo** por el art. 179 del CST, independientemente de que además haya extras.

**Hay que llenar esta matriz, celda por celda, con RRHH y Jurídico:**

| Situación | ¿Qué conceptos se generan y por cuántas horas? |
|---|---|
| Trabaja su día de descanso, dentro de la jornada | ? |
| Trabaja su día de descanso, excediendo la jornada | ? |
| Trabaja un festivo que NO es su día de descanso | ? |
| Trabaja un festivo que SÍ es su día de descanso | ? |
| Cualquiera de las anteriores, en franja nocturna | ? |

También queda `PENDIENTE` el **contador mensual de días de descanso obligatorio trabajados**, que determina si el trabajo es ocasional (≤2 al mes) o habitual (≥3 al mes) — la ley da tratamientos distintos.

---

## 8. RECARGO NOCTURNO

`LEGAL` · Se reporta como **cantidad de horas efectivamente trabajadas en franja nocturna**, no como un factor.

Ejemplo confirmado: 8 horas trabajadas en horario nocturno → se reportan **8 horas** bajo el concepto de recargo nocturno. Sinergy aplica el porcentaje.

Franja nocturna vigente: **19:00 – 06:00** desde diciembre de 2025 (Ley 2466 de 2025). Antes: 21:00 – 06:00. **La franja es versionada por fecha.**

---

## 9. CONVENCIÓN COLECTIVA — BLOQUEANTE

`CONVENCION` · **La empresa tiene sindicato.** Es indispensable obtener la convención colectiva vigente y revisar toda cláusula sobre jornada, turnos, descansos, recargos, permisos y aprobaciones.

**Una convención prevalece sobre la política interna y puede otorgar condiciones más favorables que la ley.** Ninguna regla de este documento puede considerarse cerrada hasta contrastarla contra la convención.

---

## 10. LACTANCIA

`LEGAL` + `POLITICA` · **El tiempo de lactancia se paga como tiempo trabajado.**

Comportamiento confirmado: si la trabajadora tiene un turno de 8 horas y sale antes por lactancia trabajando 7, **el sistema le calcula 8 horas**. El uso del beneficio es flexible, a criterio de la trabajadora, y queda cubierto dentro de su turno.

`PENDIENTE` para Jurídico: duración del beneficio, desde cuándo se cuenta, y si se fracciona. **No codificar una duración fija sin validación.**

Modelo: **condición especial con vigencia** asociada a la empleada, con fecha de inicio y fin, que modifica el cálculo de su jornada mientras esté activa.

---

## 11. PERÍODOS Y CIERRE

| Ciclo | Alcance | Corte |
|---|---|---|
| Nómina | Salario | Mensual |
| **Conceptos variables** | Extras y recargos | **Del 11 al 10**, para todos los perfiles |
| Cómputo de extras | Umbral de 42 h | **Semana lunes a domingo** |

**Ventana de entrega: el archivo debe estar listo el 11 o el 12.** Uno o dos días después del cierre del ciclo.

### ⚠️ 11.1 Consecuencia de diseño crítica

Con ~1.000 empleados, 20–25 supervisores y una ventana de uno a dos días, **la aprobación no puede ser un lote al cierre del período**. Es aritméticamente imposible.

**La aprobación debe ser continua**: el sistema calcula a diario y empuja a la bandeja del jefe lo que va apareciendo, con notificación por correo. Al llegar el día 10, lo que queda pendiente debe ser marginal. El cierre del período confirma, no inicia, el trabajo de aprobación.

### 11.2 Flujo de estados

```
Calculado
   ↓  notificación por correo al jefe inmediato
Pendiente de aprobación
   ↓  jefe: aprobar · rechazar · ajustar (con justificación obligatoria)
Aprobado
   ↓  RRHH inicia el procesamiento  →  BLOQUEO: no se admiten más modificaciones
Procesado
   ↓
Reporte final generado  →  archivo plano  →  Sinergy
```

`POLITICA` · **RRHH puede aprobar en lugar del jefe**, dejando anotación obligatoria. Es la vía de escape cuando un jefe no responde a tiempo.

`POLITICA` · Reapertura tras el cierre: **posible pero deliberadamente difícil** — rol elevado, justificación obligatoria, traza completa. No es una acción de uso corriente.

---

## 12. APROBACIÓN Y ALCANCE

`CONFIG` · La facultad de aprobar **se asocia a un perfil con alcance, no a un usuario nominal** — mismo modelo que BioTime: el alcance se define por departamento, área o cargo.

⚠️ **Compatibilidad con los requisitos de registro electrónico:** el *permiso* viene del perfil, pero la *acción* debe quedar atribuida a la persona identificada que la ejecutó. Ambas cosas conviven y las dos son obligatorias. Cuentas nominales; prohibidas las genéricas o compartidas.

- Las extras requieren **autorización previa del jefe inmediato** — así funciona hoy y se conserva.
- Los **ausentismos exigen soporte adjunto** obligatorio.
- Notificación por correo en cada paso del flujo.
- ~20–25 supervisores como usuarios, correspondientes a los departamentos o áreas definidos. Todos tienen computador y red.

---

## 13. MAPEO DE CONCEPTOS HACIA SINERGY

**SIRH envía cantidades; Sinergy calcula el dinero.** El archivo plano es informativo en cuanto a tarifas: Sinergy aplica el porcentaje que corresponde a cada código según la norma vigente.

### 13.1 Requisito derivado: el código de concepto depende de la fecha

Existen pares de códigos que representan el mismo concepto bajo tarifas distintas según la fecha:

| Concepto | Código antes del 15-jul-2026 | Código desde el 15-jul-2026 |
|---|---|---|
| Recargo dominical / festivo | `0253` | `0252` |
| Recargo nocturno festivo | `0259` | `0258` |

**Por lo tanto el mapeo `concepto → código de Sinergy` es una regla versionada por fecha**, exactamente igual que las franjas y los porcentajes. El motor calcula un concepto de dominio; el adaptador de Sinergy elige el código según la fecha del período.

`PENDIENTE` de verificación operativa: dado que `0252` y `0258` **no están activos en BioTime**, confirmar que los períodos posteriores al 15 de julio de 2026 están saliendo con el código correcto en el archivo que se carga hoy. Es una verificación de una sola consulta, no una alarma.

### 13.2 Catálogo

| Código | Concepto |
|---|---|
| `0200` | Hora extra diurna ordinaria |
| `0210` | Hora extra nocturna ordinaria |
| `0250` | Hora extra festiva diurna |
| `0260` | Hora extra festiva nocturna |
| `0220` | Recargo nocturno |
| `0252` / `0253` | Recargo dominical o festivo — según fecha |
| `0258` / `0259` | Recargo nocturno festivo — según fecha |

---

## 14. ALCANCE DE LA FASE 1

**Confirmado por RRHH: la prioridad es el reporte de extras y recargos.** Los ausentismos entran después.

| En fase 1 | Fuera de fase 1 |
|---|---|
| Ingesta de marcaciones desde BioTime | Ausentismos hacia Sinergy (vía distinta, aún sin especificar) |
| Turnos, ciclos y programación en SIRH | Kiosco o terminal en planta |
| Motor de cálculo: 42 h, redondeos, recargos | Autoservicio del empleado |
| Aprobación continua por jefe inmediato | SSO con IdP corporativo |
| Períodos 11→10 y archivo plano | Migración de histórico |
| Alta y baja de empleados hacia BioTime | |

**Migración: no hay migración histórica de programación.** Se arranca desde el día de implementación. Esto elimina el riesgo que era RP-012.

**Sincronización de turnos hacia BioTime: no se requiere.** Quienes consultan turnos hoy en BioTime son jefes y RRHH, y ambos serán usuarios de SIRH. Consultarán ahí. Esto elimina un módulo completo.

---

## 15. RESTRICCIONES DEL PROYECTO

| Restricción | Valor | Implicación |
|---|---|---|
| Equipo de desarrollo | **2 personas** | El alcance de fase 1 debe protegerse con firmeza |
| Infraestructura | **On-premise** | Despliegue, backup y monitoreo son trabajo propio, no del proveedor |
| Empleados | ~1.000 | ~1.000 planillas por período hoy |
| Supervisores usuarios | 20–25 | |
| Terminales | ~10 | |
| Línea base actual | **10 días** por período | Es la métrica de éxito. Objetivo: 1–2 días |
| Sponsor | RRHH | |
| Presupuesto y fecha | Sin definir, pero es necesidad reconocida | |

⚠️ **Dos personas para este alcance es ajustado.** Es viable si la fase 1 se protege de agregados y si los tres activos de descubrimiento se consiguen antes de escribir código. No es viable si se intenta abarcar ausentismos, kiosco y SSO en la misma entrega.

---

## 16. SIRH ACTUAL — ALCANCE REAL

El SIRH existente administra: datos personales, formación, **ausencias e incapacidades**, accidentes de trabajo y enfermedades profesionales, eventos disciplinarios, evaluación de competencias, capacitaciones y dotaciones.

**Es un sistema de RRHH completo, mucho más amplio de lo supuesto.** Esto confirma que reconstruirlo entero habría sido desproporcionado, y valida la arquitectura en capa.

⚠️ **Ausencias e incapacidades ya viven en el SIRH actual.** Antes de construir el módulo de ausentismos hay que decidir si el nuevo lo absorbe, lo reemplaza o convive con él. `PENDIENTE` — no bloquea la fase 1, pero sí condiciona la fase 2.

---

## 17. CALIDAD Y DATOS PERSONALES

- ✅ **Existe autorización de los trabajadores** para el tratamiento de datos biométricos.
- `PENDIENTE` **Alcance de los requisitos de calidad** — ¿solo control documental ISO 9001, o exigencia de registro electrónico de cliente farmacéutico? Es lo que decide si hay o no un frente de validación del sistema. Debe responderlo Calidad **antes de dimensionar**.
- `PENDIENTE` **Reemplazo del reconocimiento del empleado**, que hoy es su firma en la planilla. Hay que evaluar opciones, no omitirlo.

Independientemente del alcance: traza inmutable, atribución individual, justificación obligatoria en ajustes y versionado del formato se diseñan desde el primer día.

---

## 18. PENDIENTES ABIERTOS

| # | Pendiente | Responsable | Bloquea |
|---|---|---|---|
| 1 | Figura legal del otrosí y turnos de 12 h | Jurídico | Motor de cálculo |
| 2 | Convención colectiva vigente | RRHH + Jurídico | Toda la matriz de reglas |
| 3 | Matriz de festivo × día de descanso (§7.1) | RRHH + Jurídico | Motor de cálculo |
| 4 | Anclaje del redondeo: reloj o fin de turno (§4.1) | RRHH | Motor de cálculo |
| 5 | Dimensión de parametrización de tolerancias (§4.2) | RRHH | Motor de cálculo |
| 6 | Contador mensual ocasional / habitual (§7.1) | RRHH + Jurídico | Motor de cálculo |
| 7 | Duración y fraccionamiento de lactancia | Jurídico | Fase 2 |
| 8 | Reglas para temporales Granservicios y SENA | RRHH | Alcance del archivo |
| 9 | Vía y catálogo de ausentismos hacia Sinergy | RRHH + Sinergy | Fase 2 |
| 10 | Alcance de requisitos de calidad | Calidad | Dimensionamiento |
| 11 | Reemplazo del reconocimiento del empleado | RRHH + Calidad | Diseño de fase 1 |
| 12 | Comportamiento de Sinergy ante recarga del mismo período | Sinergy | Diseño de exportación |
| 13 | Validaciones de Sinergy al cargar el archivo | Sinergy | Diseño de exportación |
| 14 | Coexistencia con el módulo de ausencias del SIRH actual | RRHH + TI | Fase 2 |
| 15 | Café: ¿aplica a administrativos? ¿se marca? | RRHH | Motor de cálculo |

---

## 19. CONFIRMADO Y CERRADO

Reglas que ya no requieren más consulta:

- Perfiles determinados por **cargo**.
- Semana laboral **lunes a domingo**.
- Turno se imputa al **día de inicio**.
- El tiempo cuenta **desde el inicio del turno programado**, sin importar marcación anticipada.
- Redondeo de extras en incrementos de **0,5 h** con cortes en `:25` y `:50`, **global**.
- Almuerzo **60 min descontables, habilitables por turno**.
- Café **20 min pagados**, no descontables.
- **Para generar extras o recargos hay que trabajar.**
- Recargo nocturno se reporta como **horas efectivamente trabajadas**.
- Lactancia **se paga como tiempo trabajado**.
- Ciclo de conceptos variables **11 → 10**, para todos los perfiles.
- **Aprobación continua**, no por lote al cierre.
- Aprobación por **perfil con alcance**, no por usuario nominal.
- **RRHH puede aprobar** en lugar del jefe, con anotación.
- **Bloqueo al iniciar el procesamiento** de RRHH.
- Reapertura posible pero **deliberadamente difícil**.
- **Sin migración histórica** de programación.
- **Sin sincronización de turnos** hacia BioTime.
- SIRH **crea y da de baja** empleados en BioTime; baja = renuncia.
- Entrega del archivo a Sinergy: **carga manual**.
- Vacaciones: **días hábiles**.
- Fase 1 = **extras y recargos**. Ausentismos después.
