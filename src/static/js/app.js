/**
 * SIRH Plastitec — Módulo de Tiempos y Asistencia
 * Frontend Application Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

const App = {
  state: {
    userRole: 'SUPERVISOR',
    userId: 'SUP_PLANTA_01',
    userName: 'Carlos Ruiz',
    periodo: null,
    bandejaItems: [],
    selectedIds: new Set(),
    activeTab: 'tab-supervisor',
    filtroEstado: 'PENDIENTE',
    filtroBusqueda: '',
    soloExcepciones: false,
  },

  init() {
    this.bindEvents();
    this.parseUserContext();
    this.cargarDashboard();
    this.cargarBandeja();
    this.cargarAuditoria();
  },

  bindEvents() {
    // Role Switcher
    const selectUser = document.getElementById('selectUserContext');
    if (selectUser) {
      selectUser.addEventListener('change', (e) => {
        const [rol, id, nombre] = e.target.value.split(':');
        this.state.userRole = rol;
        this.state.userId = id;
        this.state.userName = nombre;
        this.showToast(`Cambiado a rol: ${rol} (${nombre})`, 'info');
        this.cargarBandeja();
      });
    }

    // Tab Navigation
    document.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const targetTab = btn.getAttribute('data-tab');
        this.switchTab(targetTab);
      });
    });

    // BioTime Sync Button
    const btnSync = document.getElementById('btnSyncBioTime');
    if (btnSync) {
      btnSync.addEventListener('click', () => this.ejecutarSincronizacionBioTime());
    }

    // Open Calculation Modal
    const btnOpenCalc = document.getElementById('btnOpenCalculoModal');
    if (btnOpenCalc) {
      btnOpenCalc.addEventListener('click', () => {
        document.getElementById('modalCalculo').style.display = 'flex';
      });
    }

    // Modal Calculation Handlers
    const btnCloseCalc = document.getElementById('btnCloseModalCalculo');
    const btnCancelCalc = document.getElementById('btnCancelarCalculo');
    if (btnCloseCalc) btnCloseCalc.addEventListener('click', () => this.cerrarModalCalculo());
    if (btnCancelCalc) btnCancelCalc.addEventListener('click', () => this.cerrarModalCalculo());

    const btnRunCalc = document.getElementById('btnEjecutarCalculoMotor');
    if (btnRunCalc) {
      btnRunCalc.addEventListener('click', () => this.ejecutarCalculoMotor());
    }

    // Table Filters
    const inputSearch = document.getElementById('inputSearchEmpleado');
    if (inputSearch) {
      inputSearch.addEventListener('input', (e) => {
        this.state.filtroBusqueda = e.target.value.trim().toLowerCase();
        this.renderBandeja();
      });
    }

    const selectEstado = document.getElementById('selectFiltroEstado');
    if (selectEstado) {
      selectEstado.addEventListener('change', (e) => {
        this.state.filtroEstado = e.target.value;
        this.cargarBandeja();
      });
    }

    const chkExcep = document.getElementById('chkSoloExcepciones');
    if (chkExcep) {
      chkExcep.addEventListener('change', (e) => {
        this.state.soloExcepciones = e.target.checked;
        this.cargarBandeja();
      });
    }

    // Table Selection Checkbox (Select All)
    const chkAll = document.getElementById('chkSelectAll');
    if (chkAll) {
      chkAll.addEventListener('change', (e) => {
        const isChecked = e.target.checked;
        const visibleItems = this.getVisibleBandejaItems();
        if (isChecked) {
          visibleItems.forEach((item) => this.state.selectedIds.add(item.resultado_id));
        } else {
          this.state.selectedIds.clear();
        }
        this.renderBandeja();
        this.updateActionButtons();
      });
    }

    // Batch Actions
    const btnAprobarSel = document.getElementById('btnAprobarSeleccionados');
    if (btnAprobarSel) {
      btnAprobarSel.addEventListener('click', () => this.aprobarSeleccionados());
    }

    const btnAprobarTodoSinExc = document.getElementById('btnAprobarTodoSinExcepcion');
    if (btnAprobarTodoSinExc) {
      btnAprobarTodoSinExc.addEventListener('click', () => this.aprobarTodoSinExcepcion());
    }

    // Modal Adjustment Handlers
    const btnCloseModalAjuste = document.getElementById('btnCloseModalAjuste');
    const btnCancelarAjuste = document.getElementById('btnCancelarAjuste');
    if (btnCloseModalAjuste) btnCloseModalAjuste.addEventListener('click', () => this.cerrarModalAjuste());
    if (btnCancelarAjuste) btnCancelarAjuste.addEventListener('click', () => this.cerrarModalAjuste());

    const btnConfirmAjuste = document.getElementById('btnConfirmarAjuste');
    if (btnConfirmAjuste) {
      btnConfirmAjuste.addEventListener('click', () => this.confirmarAjuste());
    }

    // RRHH Period Management Handlers
    const btnBloquear = document.getElementById('btnBloquearRRHH');
    if (btnBloquear) {
      btnBloquear.addEventListener('click', () => this.bloquearSupervisoresRRHH());
    }

    const btnExportar = document.getElementById('btnExportarSinergy');
    if (btnExportar) {
      btnExportar.addEventListener('click', () => this.exportarSinergy());
    }

    const btnReabrir = document.getElementById('btnReabrirPeriodo');
    if (btnReabrir) {
      btnReabrir.addEventListener('click', () => this.reabrirPeriodoEmergencia());
    }

    // Parallel Comparator Handlers
    const btnConciliar = document.getElementById('btnEjecutarConciliacion');
    if (btnConciliar) {
      btnConciliar.addEventListener('click', () => this.ejecutarConciliacionParalelo());
    }

    // Audit Refresh Button
    const btnRefreshAud = document.getElementById('btnRefreshAuditoria');
    if (btnRefreshAud) {
      btnRefreshAud.addEventListener('click', () => {
        this.cargarAuditoria();
        this.showToast('Bitácora de auditoría actualizada', 'info');
      });
    }

    // Click Hash to Copy
    const lblHash = document.getElementById('lblHashSha256');
    if (lblHash) {
      lblHash.addEventListener('click', () => {
        const text = lblHash.innerText;
        if (text && text !== '--') {
          navigator.clipboard.writeText(text);
          this.showToast('Hash SHA-256 copiado al portapapeles', 'success');
        }
      });
    }
  },

  parseUserContext() {
    const select = document.getElementById('selectUserContext');
    if (select) {
      const [rol, id, nombre] = select.value.split(':');
      this.state.userRole = rol;
      this.state.userId = id;
      this.state.userName = nombre;
    }
  },

  switchTab(targetTabId) {
    this.state.activeTab = targetTabId;
    document.querySelectorAll('.tab-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === targetTabId);
    });
    document.querySelectorAll('.tab-panel').forEach((panel) => {
      panel.classList.toggle('active', panel.id === targetTabId);
    });
  },

  // -------------------------------------------------------------
  // Data Loading & API Integrations
  // -------------------------------------------------------------

  async cargarDashboard() {
    try {
      const res = await fetch('/api/v1/dashboard/resumen');
      if (!res.ok) throw new Error('Error al cargar KPIs de resumen');
      const data = await res.json();

      // Top Navbar Period Pill
      const navPeriodName = document.getElementById('navPeriodName');
      const navPeriodBadge = document.getElementById('navPeriodBadge');
      if (navPeriodName) navPeriodName.innerText = `Período: ${data.periodo_codigo}`;
      if (navPeriodBadge) {
        navPeriodBadge.innerText = data.periodo_estado;
        navPeriodBadge.className = `period-status-badge ${data.periodo_estado === 'ABIERTO' ? 'badge-success' : data.periodo_estado === 'EN_PROCESAMIENTO' ? 'badge-warning' : 'badge-neutral'}`;
      }

      // KPI Card 1: Período
      const kpiCodigo = document.getElementById('kpiPeriodoCodigo');
      const kpiRango = document.getElementById('kpiPeriodoRango');
      if (kpiCodigo) kpiCodigo.innerText = data.periodo_codigo;
      if (kpiRango) kpiRango.innerText = `${data.periodo_inicio} a ${data.periodo_fin}`;

      // KPI Card 2: Pendientes
      const kpiPend = document.getElementById('kpiPendientes');
      if (kpiPend) kpiPend.innerText = data.pendientes_aprobacion.toLocaleString();

      // KPI Card 3: Aprobadas & Progress
      const kpiApr = document.getElementById('kpiAprobadas');
      const kpiProgress = document.getElementById('kpiProgressBar');
      const kpiProgText = document.getElementById('kpiProgresoText');
      if (kpiApr) kpiApr.innerText = data.jornadas_aprobadas.toLocaleString();

      const total = data.total_conceptos_periodo || 0;
      const pct = total > 0 ? Math.round((data.jornadas_aprobadas / total) * 100) : 0;
      if (kpiProgress) kpiProgress.style.width = `${pct}%`;
      if (kpiProgText) kpiProgText.innerText = `${pct}% aprobado (${data.jornadas_aprobadas} de ${total})`;

      // KPI Card 4: Excepciones
      const kpiExc = document.getElementById('kpiExcepciones');
      if (kpiExc) kpiExc.innerText = data.excepciones_horas_extras.toLocaleString();

      this.state.periodo = data;
      this.actualizarPeriodoPanel(data);

    } catch (err) {
      console.error('Dashboard resumen error:', err);
    }
  },

  async cargarBandeja() {
    const tbody = document.getElementById('tbodyBandeja');
    if (tbody) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="loading-state">
            <div class="spinner"></div>
            <p>Consultando conceptos de liquidación en el motor...</p>
          </td>
        </tr>`;
    }

    try {
      const params = new URLSearchParams({
        supervisor_id: this.state.userId,
        rol: this.state.userRole,
        solo_excepciones: this.state.soloExcepciones ? 'true' : 'false',
        estado: this.state.filtroEstado,
      });

      const res = await fetch(`/api/v1/aprobacion/bandeja?${params.toString()}`);
      if (!res.ok) throw new Error('Error al cargar bandeja');
      const data = await res.json();
      this.state.bandejaItems = data;
      this.state.selectedIds.clear();
      this.renderBandeja();
      this.updateActionButtons();
    } catch (err) {
      console.error('Bandeja error:', err);
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="9" class="text-center text-muted" style="padding: 2rem;">
              No se pudieron cargar los registros. Ejecute "Calcular Tiempos" para generar jornadas liquidables.
            </td>
          </tr>`;
      }
    }
  },

  getVisibleBandejaItems() {
    let items = this.state.bandejaItems;
    if (this.state.filtroBusqueda) {
      const q = this.state.filtroBusqueda;
      items = items.filter(
        (i) =>
          i.empleado_nombre.toLowerCase().includes(q) ||
          i.emp_code.toLowerCase().includes(q) ||
          i.departamento.toLowerCase().includes(q)
      );
    }
    return items;
  },

  renderBandeja() {
    const tbody = document.getElementById('tbodyBandeja');
    if (!tbody) return;

    const visibleItems = this.getVisibleBandejaItems();

    if (visibleItems.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center text-muted" style="padding: 3rem 1rem;">
            <p style="font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem;">No hay conceptos pendientes para este filtro.</p>
            <p style="font-size: 0.82rem;">Si acaba de sincronizar marcaciones con BioTime, presione <strong>"Calcular Tiempos"</strong> en la barra superior para procesar las jornadas.</p>
          </td>
        </tr>`;
      document.getElementById('footerInfoText').innerText = '0 registros encontrados';
      return;
    }

    let html = '';
    visibleItems.forEach((item) => {
      const isChecked = this.state.selectedIds.has(item.resultado_id);
      const badgeClass = this.getConceptBadgeClass(item.concepto);
      const statusBadge =
        item.estado === 'APROBADO'
          ? '<span class="badge badge-success">APROBADO</span>'
          : item.estado === 'AJUSTADO'
          ? '<span class="badge badge-purple">AJUSTADO</span>'
          : '<span class="badge badge-warning">PENDIENTE</span>';

      html += `
        <tr data-id="${item.resultado_id}">
          <td>
            <input type="checkbox" class="row-checkbox" data-id="${item.resultado_id}" ${isChecked ? 'checked' : ''} ${item.estado !== 'PENDIENTE' ? 'disabled' : ''}>
          </td>
          <td><span class="font-mono" style="font-weight: 600; color: #38bdf8;">${item.emp_code}</span></td>
          <td>
            <div class="col-emp-name">${this.escapeHtml(item.empleado_nombre)}</div>
            <div class="col-emp-dept">${this.escapeHtml(item.departamento)}</div>
          </td>
          <td><span class="font-mono">${item.fecha_imputacion}</span></td>
          <td>
            <span class="concept-pill ${badgeClass}">
              <strong>${item.concepto}</strong> ${item.concepto_descripcion || ''}
            </span>
          </td>
          <td style="text-align: right;">
            <span class="hours-display">${item.horas.toFixed(2)}h</span>
            ${item.ajuste_horas ? `<br><small class="text-muted">Ajustado: ${item.ajuste_horas.toFixed(2)}h</small>` : ''}
          </td>
          <td style="text-align: center;">${statusBadge}</td>
          <td style="text-align: center;">
            <div style="display: inline-flex; gap: 0.4rem;">
              ${
                item.estado === 'PENDIENTE'
                  ? `
                <button class="btn-icon approve" title="Aprobar de inmediato" onclick="App.aprobarIndividual(${item.resultado_id})">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
                </button>
                <button class="btn-icon adjust" title="Ajustar horas con justificación" onclick="App.abrirModalAjuste(${item.resultado_id})">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                </button>
              `
                  : `
                <button class="btn-icon" title="Ver detalle auditado" onclick="App.verDetalleAuditado(${item.resultado_id})">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                </button>
              `
              }
            </div>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;

    // Attach row checkbox handlers
    tbody.querySelectorAll('.row-checkbox').forEach((chk) => {
      chk.addEventListener('change', (e) => {
        const id = parseInt(e.target.getAttribute('data-id'), 10);
        if (e.target.checked) {
          this.state.selectedIds.add(id);
        } else {
          this.state.selectedIds.delete(id);
        }
        this.updateActionButtons();
      });
    });

    document.getElementById('footerInfoText').innerText = `Mostrando ${visibleItems.length} de ${this.state.bandejaItems.length} conceptos`;
  },

  getConceptBadgeClass(concepto) {
    if (concepto === '0200') return 'concept-hed';
    if (concepto === '0210') return 'concept-hen';
    if (concepto === '0250') return 'concept-hedf';
    if (concepto === '0260') return 'concept-henf';
    if (concepto.startsWith('022') || concepto.startsWith('025')) return 'concept-recargo';
    return 'concept-ord';
  },

  updateActionButtons() {
    const count = this.state.selectedIds.size;
    const btnAprobarSel = document.getElementById('btnAprobarSeleccionados');
    const lblCount = document.getElementById('countSeleccionados');
    if (btnAprobarSel) {
      btnAprobarSel.disabled = count === 0;
    }
    if (lblCount) {
      lblCount.innerText = count.toString();
    }
  },

  // -------------------------------------------------------------
  // Approval Actions (Phase 5 / Continuous Daily Approval)
  // -------------------------------------------------------------

  async aprobarIndividual(resultadoId) {
    await this.enviarAprobacion([resultadoId], false, null);
  },

  async aprobarSeleccionados() {
    const ids = Array.from(this.state.selectedIds);
    if (ids.length === 0) return;
    await this.enviarAprobacion(ids, false, null);
  },

  async aprobarTodoSinExcepcion() {
    const pendingItems = this.state.bandejaItems.filter(
      (item) => item.estado === 'PENDIENTE' && !item.es_extra
    );
    if (pendingItems.length === 0) {
      this.showToast('No hay conceptos ordinarios pendientes sin horas extras', 'info');
      return;
    }

    const ids = pendingItems.map((i) => i.resultado_id);
    await this.enviarAprobacion(ids, false, 'Aprobación masiva 1-click de jornadas regulares');
  },

  async enviarAprobacion(resultadoIds, esSustitucion = false, anotacion = null) {
    try {
      const payload = {
        resultado_ids: resultadoIds,
        usuario_id: this.state.userId,
        usuario_nombre: this.state.userName,
        rol: this.state.userRole,
        es_sustitucion_rrhh: this.state.userRole === 'RRHH' || esSustitucion,
        anotacion: anotacion || (this.state.userRole === 'RRHH' ? 'Aprobación autorizada por RRHH en cierre de ciclo' : null),
      };

      const res = await fetch('/api/v1/aprobacion/aprobar-bloque', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Error en la aprobación');
      }

      const data = await res.json();
      this.showToast(data.mensaje || 'Conceptos aprobados con éxito', 'success');
      this.state.selectedIds.clear();
      await this.cargarBandeja();
      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  abrirModalAjuste(resultadoId) {
    const item = this.state.bandejaItems.find((i) => i.resultado_id === resultadoId);
    if (!item) return;

    document.getElementById('modalResultadoId').value = item.resultado_id;
    document.getElementById('modalEmpNombre').value = `${item.emp_code} - ${item.empleado_nombre}`;
    document.getElementById('modalFecha').value = item.fecha_imputacion;
    document.getElementById('modalConcepto').value = `${item.concepto} - ${item.concepto_descripcion || ''}`;
    document.getElementById('modalHorasOriginales').value = `${item.horas.toFixed(2)} horas`;
    document.getElementById('modalNuevasHoras').value = item.horas;
    document.getElementById('modalJustificacion').value = item.motivo_ajuste || '';

    document.getElementById('modalAjuste').style.display = 'flex';
  },

  cerrarModalAjuste() {
    document.getElementById('modalAjuste').style.display = 'none';
  },

  async confirmarAjuste() {
    const resultadoId = parseInt(document.getElementById('modalResultadoId').value, 10);
    const nuevasHoras = parseFloat(document.getElementById('modalNuevasHoras').value);
    const justificacion = document.getElementById('modalJustificacion').value.trim();

    if (isNaN(nuevasHoras) || nuevasHoras < 0) {
      this.showToast('Debe ingresar una cantidad válida de horas.', 'error');
      return;
    }

    if (!justificacion || justificacion.length < 10) {
      this.showToast('La justificación es obligatoria y debe contener mínimo 10 caracteres para auditoría.', 'error');
      return;
    }

    try {
      const payload = {
        resultado_id: resultadoId,
        nuevas_horas: nuevasHoras,
        motivo_justificacion: justificacion,
        usuario_id: this.state.userId,
        usuario_nombre: this.state.userName,
        rol: this.state.userRole,
      };

      const res = await fetch('/api/v1/aprobacion/ajustar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Error al guardar el ajuste');
      }

      this.showToast('Ajuste de horas registrado y sellado con hash inmutable.', 'success');
      this.cerrarModalAjuste();
      await this.cargarBandeja();
      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  verDetalleAuditado(resultadoId) {
    const item = this.state.bandejaItems.find((i) => i.resultado_id === resultadoId);
    if (!item) return;

    let msg = `Concepto ${item.concepto} (${item.horas}h) - Estado: ${item.estado}`;
    if (item.motivo_ajuste) {
      msg += `\nMotivo de Ajuste: "${item.motivo_ajuste}"`;
    }
    if (item.supervisor_id) {
      msg += `\nValidado por: ${item.supervisor_id}`;
    }
    alert(msg);
  },

  // -------------------------------------------------------------
  // RRHH Payroll Closure & Sinergy Flat File (Phase 6)
  // -------------------------------------------------------------

  actualizarPeriodoPanel(periodoData) {
    const stepBloqueo = document.getElementById('stepBloqueo');
    const stepExport = document.getElementById('stepExportacion');
    const alertTitle = document.getElementById('alertPeriodTitle');
    const alertDesc = document.getElementById('alertPeriodDesc');

    if (periodoData.periodo_estado === 'ABIERTO') {
      if (stepBloqueo) stepBloqueo.className = 'step-item active';
      if (stepExport) stepExport.className = 'step-item';
      if (alertTitle) alertTitle.innerText = `Período ${periodoData.periodo_codigo} en Curso (Abierto)`;
      if (alertDesc) alertDesc.innerText = `Los supervisores tienen plazo hasta el día 10 a las 23:59. Hay ${periodoData.pendientes_aprobacion} conceptos pendientes.`;
    } else if (periodoData.periodo_estado === 'EN_PROCESAMIENTO') {
      if (stepBloqueo) stepBloqueo.className = 'step-item completed';
      if (stepExport) stepExport.className = 'step-item active';
      if (alertTitle) alertTitle.innerText = `Período ${periodoData.periodo_codigo} Bloqueado para Supervisores`;
      if (alertDesc) alertDesc.innerText = `Edición exclusiva para RRHH. Puede generar la exportación para Sinergy Nómina.`;
    } else if (periodoData.periodo_estado === 'CERRADO') {
      if (stepBloqueo) stepBloqueo.className = 'step-item completed';
      if (stepExport) stepExport.className = 'step-item completed';
      if (alertTitle) alertTitle.innerText = `Período ${periodoData.periodo_codigo} Cerrado Definitivamente`;
      if (alertDesc) alertDesc.innerText = `El archivo plano oficial fue generado con firma de integridad.`;
    }
  },

  async bloquearSupervisoresRRHH() {
    if (!this.state.periodo) return;
    if (!confirm('¿Desea bloquear la edición para supervisores del día 11? Solo RRHH podrá hacer modificaciones a partir de ahora.')) {
      return;
    }

    try {
      const res = await fetch(`/api/v1/periodos/${this.state.periodo.periodo_id}/bloquear-rrhh`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'No se pudo bloquear el período');
      }
      this.showToast('Período bloqueado. Supervisores no pueden realizar más cambios.', 'warning');
      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  async exportarSinergy() {
    if (!this.state.periodo) return;

    if (this.state.periodo.pendientes_aprobacion > 0) {
      if (!confirm(`Aún existen ${this.state.periodo.pendientes_aprobacion} conceptos pendientes por aprobar. ¿Desea forzar el cierre y exportar el plano Sinergy de todas formas?`)) {
        return;
      }
    }

    try {
      const res = await fetch(`/api/v1/periodos/${this.state.periodo.periodo_id}/exportar-sinergy?forzar=true`, {
        method: 'POST',
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Error al generar plano Sinergy');
      }

      const data = await res.json();
      this.showToast(`Archivo ${data.archivo} generado exitosamente.`, 'success');

      // Update Export Box
      document.getElementById('exportMetaBox').style.display = 'flex';
      document.getElementById('lblArchivoNombre').innerText = data.archivo;
      document.getElementById('lblTotalLineas').innerText = `${data.total_lineas} conceptos tabulados`;
      document.getElementById('lblTotalHoras').innerText = `${data.total_horas.toFixed(2)} horas`;
      document.getElementById('lblHashSha256').innerText = data.hash_sha256;
      document.getElementById('preSinergyContent').innerText = data.preview_contenido;

      // Update Download Link
      const btnDesc = document.getElementById('btnDescargarPlano');
      if (btnDesc) {
        btnDesc.href = `/api/v1/exportaciones/${this.state.periodo.periodo_id}/descargar`;
      }

      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  async reabrirPeriodoEmergencia() {
    if (!this.state.periodo) return;
    const motivo = prompt('Reapertura Excepcional de Período:\nIngrese la justificación tipificada requerida para auditoría:');
    if (!motivo || motivo.trim().length < 10) {
      this.showToast('La justificación es obligatoria (mínimo 10 caracteres).', 'error');
      return;
    }

    try {
      const payload = {
        motivo_justificacion: motivo.trim(),
        usuario_id: this.state.userId,
        usuario_nombre: this.state.userName,
        rol: 'ADMIN',
      };

      const res = await fetch(`/api/v1/periodos/${this.state.periodo.periodo_id}/reabrir`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'No se pudo reabrir el período');
      }

      this.showToast('Período reabierto excepcionalmente y registrado en auditoría.', 'warning');
      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    }
  },

  // -------------------------------------------------------------
  // Parallel Comparator (Phase 7 / BioTime vs SIRH Engine)
  // -------------------------------------------------------------

  async ejecutarConciliacionParalelo() {
    const desde = document.getElementById('compFechaDesde').value;
    const hasta = document.getElementById('compFechaHasta').value;
    const empCode = document.getElementById('compEmpCode').value.trim();

    if (!desde || !hasta) {
      this.showToast('Debe ingresar fechas desde y hasta válidas.', 'error');
      return;
    }

    const tbody = document.getElementById('tbodyConciliacion');
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="loading-state">
          <div class="spinner"></div>
          <p>Conciliando jornadas contra reporte dailyHourReport de BioTime...</p>
        </td>
      </tr>`;

    try {
      const params = new URLSearchParams({ desde, hasta });
      if (empCode) params.append('emp_code', empCode);

      const res = await fetch(`/api/v1/paralelo/conciliar?${params.toString()}`);
      if (!res.ok) throw new Error('Error al ejecutar conciliación');
      const data = await res.json();

      // Update Diagnostic Chips
      document.getElementById('diagTotalEvaluadas').innerText = data.total_evaluadas || 0;
      document.getElementById('diagCoincidencias').innerText = data.coincidencias || 0;
      document.getElementById('diagP1P4').innerText = data.desvios_explicables_p1_p4 || 0;
      document.getElementById('diagAnomalias').innerText = data.anomalias || 0;

      const items = data.detalle || [];
      if (items.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" class="text-center text-muted" style="padding: 2rem;">
              No se encontraron registros en el rango seleccionado.
            </td>
          </tr>`;
        return;
      }

      let html = '';
      items.forEach((item) => {
        const diagBadge =
          item.diagnostico === 'COINCIDENCIA_EXACTA'
            ? '<span class="badge badge-success">Coincidencia Exacta</span>'
            : item.diagnostico === 'DESVIO_EXPLICABLE_P1_P4'
            ? '<span class="badge badge-cyan">Reglas Plastitec (42h / :25-:50)</span>'
            : '<span class="badge badge-warning">Anomalía</span>';

        html += `
          <tr>
            <td><span class="font-mono">${item.emp_code}</span></td>
            <td><span class="font-mono">${item.fecha}</span></td>
            <td>${item.horas_biotime.toFixed(2)}h</td>
            <td><strong>${item.horas_sirh.toFixed(2)}h</strong></td>
            <td><span class="font-mono">${(item.horas_sirh - item.horas_biotime).toFixed(2)}h</span></td>
            <td>${diagBadge}</td>
          </tr>
        `;
      });
      tbody.innerHTML = html;

    } catch (err) {
      this.showToast(err.message, 'error');
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Error al procesar la conciliación.</td></tr>`;
    }
  },

  // -------------------------------------------------------------
  // Audit Trail (SHA-256 Immutability)
  // -------------------------------------------------------------

  async cargarAuditoria() {
    const tbody = document.getElementById('tbodyAuditoria');
    if (!tbody) return;

    try {
      const res = await fetch('/api/v1/auditoria/recientes');
      if (!res.ok) throw new Error('Error al cargar bitácora de auditoría');
      const items = await res.json();

      if (items.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">No hay eventos de auditoría registrados.</td></tr>`;
        return;
      }

      let html = '';
      items.forEach((item) => {
        const shortHash = item.hash_sha256 ? `${item.hash_sha256.substring(0, 16)}...` : '--';
        html += `
          <tr>
            <td><span class="font-mono">#${item.id}</span></td>
            <td><span class="font-mono" style="font-size: 0.78rem;">${item.timestamp.replace('T', ' ').substring(0, 19)}</span></td>
            <td><strong>${this.escapeHtml(item.usuario)}</strong> <span class="badge badge-neutral">${item.rol}</span></td>
            <td><span class="badge badge-info">${item.accion}</span></td>
            <td><span class="font-mono">${item.entidad}</span></td>
            <td style="max-width: 280px; font-size: 0.8rem;">${this.escapeHtml(item.motivo || 'N/A')}</td>
            <td>
              <span class="font-mono hash-tag" title="Hash SHA-256 completo: ${item.hash_sha256}">
                ${shortHash}
              </span>
            </td>
          </tr>
        `;
      });
      tbody.innerHTML = html;
    } catch (err) {
      console.error('Audit load error:', err);
    }
  },

  // -------------------------------------------------------------
  // Calculation Engine Batch Trigger
  // -------------------------------------------------------------

  cerrarModalCalculo() {
    document.getElementById('modalCalculo').style.display = 'none';
    document.getElementById('calcFeedbackBox').style.display = 'none';
  },

  async ejecutarCalculoMotor() {
    const fIni = document.getElementById('calcFechaInicio').value;
    const fFin = document.getElementById('calcFechaFin').value;

    if (!fIni || !fFin) {
      this.showToast('Seleccione fechas válidas de inicio y fin.', 'error');
      return;
    }

    const box = document.getElementById('calcFeedbackBox');
    const txt = document.getElementById('calcFeedbackText');
    box.style.display = 'flex';
    txt.innerText = 'Ejecutando pipeline de cálculo (Etapas 3 a 6 y umbral 42h)...';

    try {
      const payload = {
        fecha_inicio: fIni,
        fecha_fin: fFin,
        usuario_id: this.state.userId,
      };

      const res = await fetch('/api/v1/calculo/procesar-rango', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Error en el cálculo');
      }

      const data = await res.json();
      this.showToast(`Cálculo exitoso: ${data.conceptos_generados} conceptos calculados (${data.total_horas} hrs).`, 'success');
      this.cerrarModalCalculo();
      await this.cargarDashboard();
      await this.cargarBandeja();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
      box.style.display = 'none';
    }
  },

  // -------------------------------------------------------------
  // BioTime Ingestion Sync
  // -------------------------------------------------------------

  async ejecutarSincronizacionBioTime() {
    const btnText = document.getElementById('syncBtnText');
    const prevText = btnText.innerText;
    btnText.innerText = 'Sincronizando...';

    try {
      const res = await fetch('/api/v1/ingesta/sincronizar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario_id: this.state.userId }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Error al sincronizar BioTime');
      }

      const data = await res.json();
      this.showToast(
        `BioTime sincronizado: ${data.nuevas_marcaciones} nuevas marcaciones, ${data.duplicados_descartados} duplicados ignorados.`,
        'success'
      );
      await this.cargarDashboard();
      await this.cargarAuditoria();
    } catch (err) {
      this.showToast(err.message, 'error');
    } finally {
      btnText.innerText = prevText;
    }
  },

  // -------------------------------------------------------------
  // Toast Notifications & Helpers
  // -------------------------------------------------------------

  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    if (type === 'error') icon = '❌';
    if (type === 'warning') icon = '⚠️';

    toast.innerHTML = `<span>${icon}</span><span>${this.escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  },
};
