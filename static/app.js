/**
 * BioTime Manager & Explorer · Client Application
 * - Theme Switcher (Dark / Light) with LocalStorage persistence
 * - Attendance Matrix (Malla de Asistencia con cálculo de turnos y marcaciones)
 * - Endpoint Explorer & Excel Export
 */

document.addEventListener("DOMContentLoaded", () => {
  // ───────────────────────────────────────────────────────────────────────────
  // 1. SIDEBAR VIEW NAVIGATION
  // ───────────────────────────────────────────────────────────────────────────
  const navMalla = document.getElementById("navMalla");
  const navReportes = document.getElementById("navReportes");
  const navNuevoEmpleado = document.getElementById("navNuevoEmpleado");
  const navEndpoints = document.getElementById("navEndpoints");
  const navDispositivos = document.getElementById("navDispositivos");

  const viewMallaSection = document.getElementById("viewMallaSection");
  const viewReportesSection = document.getElementById("viewReportesSection");
  const viewNuevoEmpleadoSection = document.getElementById("viewNuevoEmpleadoSection");
  const viewEndpointsSection = document.getElementById("viewEndpointsSection");

  function switchView(target) {
    document.querySelectorAll(".sidebar-nav .nav-item").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".app-view-container").forEach((el) => el.classList.remove("active"));

    if (target === "malla") {
      navMalla.classList.add("active");
      viewMallaSection.classList.add("active");
    } else if (target === "reportes") {
      if (navReportes) navReportes.classList.add("active");
      if (viewReportesSection) viewReportesSection.classList.add("active");
      initReportView();
    } else if (target === "nuevo-empleado") {
      if (navNuevoEmpleado) navNuevoEmpleado.classList.add("active");
      if (viewNuevoEmpleadoSection) viewNuevoEmpleadoSection.classList.add("active");
      loadEmployeeFormCatalogs();
    } else if (target === "endpoints") {
      navEndpoints.classList.add("active");
      viewEndpointsSection.classList.add("active");
    }
  }

  navMalla.addEventListener("click", (e) => {
    e.preventDefault();
    switchView("malla");
  });

  if (navReportes) {
    navReportes.addEventListener("click", (e) => {
      e.preventDefault();
      switchView("reportes");
    });
  }

  if (navNuevoEmpleado) {
    navNuevoEmpleado.addEventListener("click", (e) => {
      e.preventDefault();
      switchView("nuevo-empleado");
    });
  }

  navEndpoints.addEventListener("click", (e) => {
    e.preventDefault();
    switchView("endpoints");
  });

  navDispositivos.addEventListener("click", (e) => {
    e.preventDefault();
    switchView("endpoints");
    navDispositivos.classList.add("active");
    endpointInput.value = "/iclock/api/terminals/";
    presetSelect.value = "/iclock/api/terminals/";
    executeExplorerQuery(1);
  });

  // ───────────────────────────────────────────────────────────────────────────
  // 3. SERVER STATUS & INITIALIZATION
  // ───────────────────────────────────────────────────────────────────────────
  const serverStatusBadge = document.getElementById("serverStatusBadge");
  const serverStatusText = document.getElementById("serverStatusText");
  const baseUrlLabel = document.getElementById("baseUrlLabel");

  initApp();

  async function initApp() {
    await checkServerStatus();
    await initMatrixFilters();
    await initExplorerPresets();
    // Solo se cargan departamentos y personal al inicio para no saturar BioTime.
    // La malla se calcula únicamente cuando el usuario hace clic en 'Generar Malla'.
  }

  async function checkServerStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      if (data.configured) {
        serverStatusText.textContent = `Conectado: ${data.base_url} (${data.usuario})`;
        if (baseUrlLabel) baseUrlLabel.textContent = data.base_url;
      } else {
        serverStatusText.textContent = "Faltan credenciales en .env";
      }
    } catch (e) {
      serverStatusText.textContent = "Error al conectar con servidor local";
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 4. MALLA DE ASISTENCIA (MATRIZ DIARIA)
  // ───────────────────────────────────────────────────────────────────────────
  const matrixDeptSelect = document.getElementById("matrixDeptSelect");
  const matrixEmpSelect = document.getElementById("matrixEmpSelect");
  const matrixStartDate = document.getElementById("matrixStartDate");
  const matrixEndDate = document.getElementById("matrixEndDate");

  const btnGenerateMatrix = document.getElementById("btnGenerateMatrix");
  const btnGenerateMatrixText = document.getElementById("btnGenerateMatrixText");
  const btnExportMatrixExcel = document.getElementById("btnExportMatrixExcel");
  const matrixSearchInput = document.getElementById("matrixSearchInput");

  const matrixMetricCards = document.getElementById("matrixMetricCards");
  const metricTotalEmp = document.getElementById("metricTotalEmp");
  const metricComplete = document.getElementById("metricComplete");
  const metricIncomplete = document.getElementById("metricIncomplete");
  const metricEarly = document.getElementById("metricEarly");
  const metricLate = document.getElementById("metricLate");
  const metricAbsent = document.getElementById("metricAbsent");
  const metricNoShift = document.getElementById("metricNoShift");

  const matrixPeriodLabel = document.getElementById("matrixPeriodLabel");
  const matrixShowingLabel = document.getElementById("matrixShowingLabel");
  const matrixLoader = document.getElementById("matrixLoader");
  const matrixTableWrapper = document.getElementById("matrixTableWrapper");
  const matrixThead = document.getElementById("matrixThead");
  const matrixTbody = document.getElementById("matrixTbody");

  // Modal
  const cellModal = document.getElementById("cellModal");
  const modalCloseBtn = document.getElementById("modalCloseBtn");
  const modalEmpName = document.getElementById("modalEmpName");
  const modalDateInfo = document.getElementById("modalDateInfo");
  const modalShiftName = document.getElementById("modalShiftName");
  const modalShiftHours = document.getElementById("modalShiftHours");
  const modalStatusBadge = document.getElementById("modalStatusBadge");
  const modalPunchesTbody = document.getElementById("modalPunchesTbody");

  // Quick date buttons
  const btnQuickCurrentMonth = document.getElementById("btnQuickCurrentMonth");
  const btnQuickPrevMonth = document.getElementById("btnQuickPrevMonth");
  const btnQuick15Days = document.getElementById("btnQuick15Days");

  // Matrix State
  let currentMatrixDates = [];
  let currentMatrixEmployees = [];

  // Default dates: First to last day of current month (or recent month 2026-02)
  setDefaultDates();

  function setDefaultDates() {
    const today = new Date();
    // Default to current year & month
    const y = today.getFullYear();
    const m = today.getMonth();
    const firstDay = new Date(y, m, 1);
    const lastDay = new Date(y, m + 1, 0);

    matrixStartDate.value = formatDateISO(firstDay);
    matrixEndDate.value = formatDateISO(lastDay);
  }

  btnQuickCurrentMonth.addEventListener("click", () => {
    setDefaultDates();
    generateMatrix();
  });

  btnQuickPrevMonth.addEventListener("click", () => {
    const today = new Date();
    const firstPrev = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const lastPrev = new Date(today.getFullYear(), today.getMonth(), 0);
    matrixStartDate.value = formatDateISO(firstPrev);
    matrixEndDate.value = formatDateISO(lastPrev);
    generateMatrix();
  });

  btnQuick15Days.addEventListener("click", () => {
    const today = new Date();
    const prev15 = new Date();
    prev15.setDate(today.getDate() - 15);
    matrixStartDate.value = formatDateISO(prev15);
    matrixEndDate.value = formatDateISO(today);
    generateMatrix();
  });

  function formatDateISO(d) {
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
  }

  async function initMatrixFilters() {
    // Load departments
    try {
      matrixDeptSelect.innerHTML = '<option value="">Cargando departamentos...</option>';
      const res = await fetch("/api/departments");
      const data = await res.json();
      matrixDeptSelect.innerHTML = '<option value="">Todos los Departamentos</option>';
      (data.departments || []).forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.name;
        matrixDeptSelect.appendChild(opt);
      });
    } catch (e) {
      console.error("Error loading departments", e);
      matrixDeptSelect.innerHTML = '<option value="">Error al cargar departamentos</option>';
    }

    // Load employees
    await loadMatrixEmployees();

    matrixDeptSelect.addEventListener("change", async () => {
      await loadMatrixEmployees(matrixDeptSelect.value);
    });
  }

  async function loadMatrixEmployees(deptId = "") {
    try {
      matrixEmpSelect.innerHTML = '<option value="">Cargando personal...</option>';
      const url = deptId ? `/api/employees?department_id=${encodeURIComponent(deptId)}` : "/api/employees";
      const res = await fetch(url);
      const data = await res.json();
      const emps = data.employees || [];
      matrixEmpSelect.innerHTML = '<option value="">Todos los Empleados</option>';
      emps.forEach((emp) => {
        const opt = document.createElement("option");
        opt.value = emp.emp_code;
        opt.textContent = `${emp.name} (${emp.emp_code})`;
        matrixEmpSelect.appendChild(opt);
      });

      // Indicadores iniciales livianos sin consultar turnos ni marcaciones
      if (metricTotalEmp && currentMatrixEmployees.length === 0) {
        metricTotalEmp.textContent = emps.length.toLocaleString();
      }
      if (matrixShowingLabel && currentMatrixEmployees.length === 0) {
        matrixShowingLabel.textContent = `${emps.length} empleados registrados`;
      }
    } catch (e) {
      console.error("Error loading employees", e);
      matrixEmpSelect.innerHTML = '<option value="">Error al cargar empleados</option>';
    }
  }

  btnGenerateMatrix.addEventListener("click", generateMatrix);

  async function generateMatrix() {
    const sDate = matrixStartDate.value;
    const eDate = matrixEndDate.value;
    if (!sDate || !eDate) {
      alert("Por favor selecciona un rango de fechas válido");
      return;
    }

    const deptId = matrixDeptSelect.value;
    const empId = matrixEmpSelect.value;

    const params = new URLSearchParams({
      start_date: sDate,
      end_date: eDate,
    });
    if (deptId) params.append("department_id", deptId);
    if (empId) params.append("employee_id", empId);

    showMatrixLoading(true);

    try {
      const res = await fetch(`/api/attendance-matrix?${params.toString()}`);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Error al procesar la asistencia");
      }

      const data = await res.json();
      currentMatrixDates = data.dates || [];
      currentMatrixEmployees = data.employees || [];

      // Update Summary Cards
      const sum = data.summary || {};
      metricTotalEmp.textContent = (sum.total_employees || 0).toLocaleString();
      metricComplete.textContent = (sum.complete || 0).toLocaleString();
      metricIncomplete.textContent = (sum.incomplete || 0).toLocaleString();
      metricEarly.textContent = (sum.early_leave || 0).toLocaleString();
      if (metricLate) metricLate.textContent = (sum.late_leave || 0).toLocaleString();
      metricAbsent.textContent = (sum.absent || 0).toLocaleString();
      metricNoShift.textContent = (sum.no_shift || 0).toLocaleString();

      matrixPeriodLabel.textContent = `${sDate} al ${eDate}`;
      matrixShowingLabel.textContent = `${currentMatrixEmployees.length} empleados`;

      renderMatrixTable(currentMatrixDates, currentMatrixEmployees);
    } catch (err) {
      alert(`Error generando malla: ${err.message}`);
    } finally {
      showMatrixLoading(false);
    }
  }

  function renderMatrixTable(dates, employees) {
    if (!dates || dates.length === 0 || !employees || employees.length === 0) {
      matrixThead.innerHTML = `<tr><th class="col-sticky-emp">Empleado</th><th class="col-dept">Departamento</th><th class="col-shift">Turno Programado</th></tr>`;
      matrixTbody.innerHTML = `<tr><td colspan="10" class="empty-placeholder">No se encontraron datos para los filtros seleccionados</td></tr>`;
      return;
    }

    // Build Header
    let theadHtml = `<tr>
      <th class="col-sticky-emp">Empleado</th>
      <th class="col-dept">Departamento</th>
      <th class="col-shift">Turno Programado</th>`;

    dates.forEach((d) => {
      theadHtml += `
        <th>
          <div class="day-header-box">
            <span class="day-num">${d.day_str}</span>
            <span class="day-name">${d.weekday}</span>
          </div>
        </th>`;
    });
    theadHtml += `</tr>`;
    matrixThead.innerHTML = theadHtml;

    // Build Rows
    renderMatrixRows(dates, employees);
  }

  function renderMatrixRows(dates, employees) {
    let tbodyHtml = "";

    employees.forEach((emp) => {
      const shiftInfo = emp.assigned_shift || {};
      const shiftDisplay = shiftInfo.name
        ? `<div class="matrix-shift-tag">
             <span class="matrix-shift-title">${escapeHtml(shiftInfo.name)}</span>
             <span class="matrix-shift-hours">${escapeHtml(shiftInfo.hours || '')}</span>
           </div>`
        : `<span style="color: var(--text-muted); font-size: 11px;">Sin Turno</span>`;

      tbodyHtml += `<tr>
        <td class="col-sticky-emp">
          <div class="matrix-emp-info">
            <span class="matrix-emp-name">${escapeHtml(emp.name)}</span>
            <span class="matrix-emp-meta">ID: ${escapeHtml(emp.emp_code)} · ${escapeHtml(emp.position)}</span>
          </div>
        </td>
        <td class="col-dept">${escapeHtml(emp.department)}</td>
        <td class="col-shift">${shiftDisplay}</td>`;

      dates.forEach((d) => {
        const dayData = emp.days[d.iso] || {};
        const status = dayData.status || "LIBRE";
        const inT = dayData.in_time ? dayData.in_time.substring(0, 5) : null;
        const outT = dayData.out_time ? dayData.out_time.substring(0, 5) : null;

        const shiftCode = dayData.shift_code || (dayData.shift_name ? dayData.shift_name.split(" ")[0] : "");
        const shiftTagHtml = shiftCode ? `<span class="cell-shift-tag">${escapeHtml(shiftCode)}</span>` : "";

        let cellContent = "";
        let statusClass = "status-off";

        if (status === "COMPLETO") {
          statusClass = "status-complete";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="punch-in">E: ${inT}</span>
              <span class="punch-out">S: ${outT}</span>
              ${shiftTagHtml}
            </div>`;
        } else if (status === "INCOMPLETO") {
          statusClass = "status-incomplete";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="${inT ? 'punch-in' : 'punch-missing'}">${inT ? 'E: ' + inT : 'FALTA ENT'}</span>
              <span class="${outT ? 'punch-out' : 'punch-missing'}">${outT ? 'S: ' + outT : 'FALTA SAL'}</span>
              ${shiftTagHtml}
            </div>`;
        } else if (status === "SALIDA_ANTICIPADA") {
          statusClass = "status-early-leave";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="punch-in">E: ${inT || '--'}</span>
              <span class="punch-out">S: ${outT || '--'} ⚠</span>
              ${shiftTagHtml}
            </div>`;
        } else if (status === "SALIDA_TARDIA") {
          statusClass = "status-late-leave";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="punch-in">E: ${inT || '--'}</span>
              <span class="punch-out" style="color: var(--cell-late-text)">S: ${outT || '--'} ⏱</span>
              ${shiftTagHtml}
            </div>`;
        } else if (status === "AUSENTE") {
          statusClass = "status-absent";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="punch-label-single">AUSENTE</span>
              ${shiftTagHtml}
            </div>`;
        } else if (status === "SIN_TURNO") {
          statusClass = "status-no-shift";
          cellContent = `
            <div class="cell-punch-stack">
              <span class="punch-in">E: ${inT || '--'}</span>
              <span class="punch-label-single">SIN TURNO</span>
            </div>`;
        } else {
          statusClass = "status-off";
          cellContent = `<span class="punch-label-single">LIBRE</span>`;
        }

        const jsonPayload = escapeAttr(JSON.stringify({ emp, dayData, dateMeta: d }));
        tbodyHtml += `
          <td class="matrix-cell ${statusClass}" data-cell-info="${jsonPayload}" title="${escapeHtml(dayData.status_text || '')}">
            ${cellContent}
          </td>`;
      });

      tbodyHtml += `</tr>`;
    });

    matrixTbody.innerHTML = tbodyHtml;

    // Attach click event for detail modal
    matrixTbody.querySelectorAll(".matrix-cell").forEach((cell) => {
      cell.addEventListener("click", () => {
        const infoAttr = cell.getAttribute("data-cell-info");
        if (infoAttr) {
          try {
            const parsed = JSON.parse(infoAttr);
            openCellDetailModal(parsed.emp, parsed.dayData, parsed.dateMeta);
          } catch (e) {
            console.error("Error opening modal", e);
          }
        }
      });
    });
  }

  // Real-time matrix filter
  matrixSearchInput.addEventListener("input", () => {
    const term = matrixSearchInput.value.toLowerCase().trim();
    if (!term) {
      renderMatrixRows(currentMatrixDates, currentMatrixEmployees);
      matrixShowingLabel.textContent = `${currentMatrixEmployees.length} empleados`;
      return;
    }

    const filtered = currentMatrixEmployees.filter(
      (e) =>
        e.name.toLowerCase().includes(term) ||
        e.emp_code.toLowerCase().includes(term) ||
        e.department.toLowerCase().includes(term) ||
        e.position.toLowerCase().includes(term)
    );
    matrixShowingLabel.textContent = `${filtered.length} empleados (filtrado)`;
    renderMatrixRows(currentMatrixDates, filtered);
  });

  // Export Matrix to Excel
  btnExportMatrixExcel.addEventListener("click", () => {
    const sDate = matrixStartDate.value;
    const eDate = matrixEndDate.value;
    if (!sDate || !eDate) {
      alert("Por favor selecciona un rango de fechas");
      return;
    }

    const params = new URLSearchParams({
      start_date: sDate,
      end_date: eDate,
    });
    if (matrixDeptSelect.value) params.append("department_id", matrixDeptSelect.value);
    if (matrixEmpSelect.value) params.append("employee_id", matrixEmpSelect.value);

    window.location.href = `/api/attendance-matrix/export-excel?${params.toString()}`;
  });

  // Modal Open/Close
  function openCellDetailModal(emp, dayData, dateMeta) {
    modalEmpName.textContent = `${emp.name} (ID: ${emp.emp_code})`;
    modalDateInfo.textContent = `Fecha: ${dateMeta.iso} (${dateMeta.weekday}) · Depto: ${emp.department}`;
    
    let shiftDisplay = dayData.shift_name || "Sin turno asignado";
    if (dayData.cross_day) {
      shiftDisplay += " (Turno Nocturno / Cruza Medianoche 🌙)";
    }
    modalShiftName.textContent = shiftDisplay;
    modalShiftHours.textContent = dayData.shift_in && dayData.shift_out ? `${dayData.shift_in} a ${dayData.shift_out}` : "N/A";
    modalStatusBadge.textContent = dayData.status_text || dayData.status;

    const punches = dayData.punches || [];
    if (punches.length === 0) {
      modalPunchesTbody.innerHTML = `<tr><td colspan="3" style="text-align:center; color: var(--text-muted); padding: 16px;">No se registraron marcaciones este día</td></tr>`;
    } else {
      modalPunchesTbody.innerHTML = punches
        .map(
          (p) => `<tr>
            <td style="color: var(--green-neon); font-weight: 600;">${p.time}</td>
            <td>${p.state === "0" ? "Entrada" : p.state === "1" ? "Salida" : "Marcación (" + p.state + ")"}</td>
            <td>${escapeHtml(p.device)}</td>
          </tr>`
        )
        .join("");
    }

    cellModal.classList.remove("hidden");
  }

  modalCloseBtn.addEventListener("click", () => cellModal.classList.add("hidden"));
  cellModal.addEventListener("click", (e) => {
    if (e.target === cellModal) cellModal.classList.add("hidden");
  });

  function showMatrixLoading(show) {
    if (show) {
      matrixLoader.classList.remove("hidden");
      btnGenerateMatrix.disabled = true;
      btnGenerateMatrixText.textContent = "Procesando...";
    } else {
      matrixLoader.classList.add("hidden");
      btnGenerateMatrix.disabled = false;
      btnGenerateMatrixText.textContent = "Generar Malla";
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 5. CONSULTA DE ENDPOINTS (EXPLORADOR)
  // ───────────────────────────────────────────────────────────────────────────
  const presetSelect = document.getElementById("presetSelect");
  const endpointInput = document.getElementById("endpointInput");
  const pageSizeInput = document.getElementById("pageSizeInput");
  const pageInput = document.getElementById("pageInput");
  const startDateInput = document.getElementById("startDateInput");
  const endDateInput = document.getElementById("endDateInput");
  const fetchAllCheckbox = document.getElementById("fetchAllCheckbox");

  const btnQuery = document.getElementById("btnQuery");
  const btnQueryText = document.getElementById("btnQueryText");
  const btnExportExcel = document.getElementById("btnExportExcel");
  const tableFilterInput = document.getElementById("tableFilterInput");

  const statTotalCount = document.getElementById("statTotalCount");
  const statReturnedCount = document.getElementById("statReturnedCount");
  const statCurrentPage = document.getElementById("statCurrentPage");

  const btnViewTable = document.getElementById("btnViewTable");
  const btnViewJson = document.getElementById("btnViewJson");
  const tableView = document.getElementById("tableView");
  const jsonView = document.getElementById("jsonView");

  const tableHeaderRow = document.getElementById("tableHeaderRow");
  const tableBody = document.getElementById("tableBody");
  const jsonCodeBlock = document.getElementById("jsonCodeBlock");
  const btnCopyJson = document.getElementById("btnCopyJson");
  const loadingOverlay = document.getElementById("loadingOverlay");
  const loadingMessage = document.getElementById("loadingMessage");
  const alertBox = document.getElementById("alertBox");

  const btnPrevPage = document.getElementById("btnPrevPage");
  const btnNextPage = document.getElementById("btnNextPage");
  const pageIndicator = document.getElementById("pageIndicator");

  let explorerRows = [];
  let explorerColumns = [];
  let explorerTotal = 0;
  let explorerCurrentPage = 1;

  async function initExplorerPresets() {
    try {
      const res = await fetch("/api/endpoints");
      const data = await res.json();
      presetSelect.innerHTML = "";
      data.endpoints.forEach((ep) => {
        const opt = document.createElement("option");
        opt.value = ep.endpoint;
        opt.textContent = `${ep.nombre} (${ep.endpoint})`;
        presetSelect.appendChild(opt);
      });
      if (presetSelect.options.length > 0) {
        endpointInput.value = presetSelect.value;
      }
    } catch (e) {
      console.error("Error loading endpoints presets", e);
    }
  }

  presetSelect.addEventListener("change", () => {
    if (presetSelect.value) endpointInput.value = presetSelect.value;
  });

  btnQuery.addEventListener("click", () => executeExplorerQuery(1));

  async function executeExplorerQuery(targetPage = 1) {
    const ep = endpointInput.value.trim();
    if (!ep) return;

    explorerCurrentPage = targetPage;
    const pageSize = parseInt(pageSizeInput.value, 10) || 50;
    pageInput.value = explorerCurrentPage;

    const params = new URLSearchParams({
      endpoint: ep,
      page: explorerCurrentPage,
      page_size: pageSize,
      fetch_all: fetchAllCheckbox.checked,
    });
    if (startDateInput.value) params.append("start_time", `${startDateInput.value} 00:00:00`);
    if (endDateInput.value) params.append("end_time", `${endDateInput.value} 23:59:59`);

    showExplorerLoading(true);
    hideAlert();

    try {
      const res = await fetch(`/api/query?${params.toString()}`);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Error al consultar endpoint");
      }

      const data = await res.json();
      explorerRows = data.rows || [];
      explorerColumns = data.columns || [];
      explorerTotal = data.total_count || 0;

      statTotalCount.textContent = explorerTotal.toLocaleString();
      statReturnedCount.textContent = explorerRows.length.toLocaleString();
      statCurrentPage.textContent = explorerCurrentPage;

      renderExplorerTable(explorerColumns, explorerRows);
      jsonCodeBlock.textContent = JSON.stringify(data.raw || explorerRows.slice(0, 10), null, 2);
      updateExplorerPagination();
    } catch (err) {
      showAlert("error", err.message);
    } finally {
      showExplorerLoading(false);
    }
  }

  function renderExplorerTable(columns, rows) {
    if (!columns || columns.length === 0) {
      tableHeaderRow.innerHTML = "<th>Sin columnas</th>";
      tableBody.innerHTML = '<tr><td colspan="11" class="empty-placeholder">No se encontraron registros</td></tr>';
      return;
    }

    tableHeaderRow.innerHTML = columns.map((c) => `<th>${escapeHtml(c.toUpperCase())}</th>`).join("");

    if (!rows || rows.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="${columns.length}" class="empty-placeholder">Sin filas devueltas</td></tr>`;
      return;
    }

    tableBody.innerHTML = rows
      .map((r) => {
        const cells = columns.map((col) => {
          const val = r[col];
          const text = val !== undefined && val !== null ? String(val) : "";
          const isState = (col.toLowerCase() === "state" || col.toLowerCase() === "status") && (text === "1" || text.toLowerCase() === "true");
          return `<td class="${isState ? 'cell-state-active' : ''}">${escapeHtml(text)}</td>`;
        });
        return `<tr>${cells.join("")}</tr>`;
      })
      .join("");
  }

  btnExportExcel.addEventListener("click", () => {
    const ep = endpointInput.value.trim();
    if (!ep) return;
    const params = new URLSearchParams({
      endpoint: ep,
      page_size: pageSizeInput.value || 500,
      fetch_all: fetchAllCheckbox.checked,
    });
    if (startDateInput.value) params.append("start_time", `${startDateInput.value} 00:00:00`);
    if (endDateInput.value) params.append("end_time", `${endDateInput.value} 23:59:59`);
    window.location.href = `/api/export-excel?${params.toString()}`;
  });

  tableFilterInput.addEventListener("input", () => {
    const term = tableFilterInput.value.toLowerCase().trim();
    if (!term) {
      renderExplorerTable(explorerColumns, explorerRows);
      statReturnedCount.textContent = explorerRows.length.toLocaleString();
      return;
    }
    const filtered = explorerRows.filter((row) =>
      Object.values(row).some((v) => String(v).toLowerCase().includes(term))
    );
    statReturnedCount.textContent = `${filtered.length.toLocaleString()} (filtrado)`;
    renderExplorerTable(explorerColumns, filtered);
  });

  btnViewTable.addEventListener("click", () => {
    btnViewTable.classList.add("active");
    btnViewJson.classList.remove("active");
    tableView.classList.add("active");
    jsonView.classList.remove("active");
  });

  btnViewJson.addEventListener("click", () => {
    btnViewJson.classList.add("active");
    btnViewTable.classList.remove("active");
    jsonView.classList.add("active");
    tableView.classList.remove("active");
  });

  btnCopyJson.addEventListener("click", () => {
    navigator.clipboard.writeText(jsonCodeBlock.textContent).then(() => {
      btnCopyJson.textContent = "¡Copiado!";
      setTimeout(() => (btnCopyJson.textContent = "Copiar JSON"), 1800);
    });
  });

  btnPrevPage.addEventListener("click", () => {
    if (explorerCurrentPage > 1) executeExplorerQuery(explorerCurrentPage - 1);
  });

  btnNextPage.addEventListener("click", () => {
    executeExplorerQuery(explorerCurrentPage + 1);
  });

  function updateExplorerPagination() {
    btnPrevPage.disabled = explorerCurrentPage <= 1;
    pageIndicator.textContent = `Página ${explorerCurrentPage}`;
    const maxPage = Math.ceil(explorerTotal / (parseInt(pageSizeInput.value, 10) || 50));
    btnNextPage.disabled = explorerTotal > 0 && explorerCurrentPage >= maxPage;
  }

  function showExplorerLoading(show) {
    if (show) {
      loadingOverlay.classList.remove("hidden");
      btnQuery.disabled = true;
    } else {
      loadingOverlay.classList.add("hidden");
      btnQuery.disabled = false;
    }
  }

  function showAlert(type, text) {
    alertBox.className = `feedback-alert ${type}`;
    alertBox.textContent = text;
    alertBox.classList.remove("hidden");
  }

  function hideAlert() {
    alertBox.classList.add("hidden");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function escapeAttr(str) {
    return escapeHtml(str).replace(/"/g, "&quot;");
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 6. CREAR NUEVO EMPLEADO (ALTA CON CATÁLOGOS EXISTENTES)
  // ───────────────────────────────────────────────────────────────────────────
  const formNuevoEmpleado = document.getElementById("formNuevoEmpleado");
  const newEmpCode = document.getElementById("newEmpCode");
  const newFirstName = document.getElementById("newFirstName");
  const newLastName = document.getElementById("newLastName");
  const newNational = document.getElementById("newNational");
  const newGender = document.getElementById("newGender");
  const newHireDate = document.getElementById("newHireDate");

  const newEmpCompany = document.getElementById("newEmpCompany");
  const newEmpBranch = document.getElementById("newEmpBranch");
  const newEmpCostCenter = document.getElementById("newEmpCostCenter");
  const newEmpType = document.getElementById("newEmpType");
  const newEmpDept = document.getElementById("newEmpDept");
  const newEmpPosition = document.getElementById("newEmpPosition");
  const newEmpVerifyMode = document.getElementById("newEmpVerifyMode");
  const newEmpAreasContainer = document.getElementById("newEmpAreasContainer");

  const newEmpMobile = document.getElementById("newEmpMobile");
  const newEmpEmail = document.getElementById("newEmpEmail");
  const newEmpAlert = document.getElementById("newEmpAlert");

  const btnResetNewEmp = document.getElementById("btnResetNewEmp");
  const btnSubmitNewEmp = document.getElementById("btnSubmitNewEmp");
  const btnSubmitNewEmpText = document.getElementById("btnSubmitNewEmpText");

  const btnSelectAllAreas = document.getElementById("btnSelectAllAreas");
  const btnClearAllAreas = document.getElementById("btnClearAllAreas");

  // Live Badge Preview Elements
  const badgePreviewCompany = document.getElementById("badgePreviewCompany");
  const badgePreviewType = document.getElementById("badgePreviewType");
  const badgePreviewAvatar = document.getElementById("badgePreviewAvatar");
  const badgePreviewName = document.getElementById("badgePreviewName");
  const badgePreviewCode = document.getElementById("badgePreviewCode");
  const badgePreviewPosition = document.getElementById("badgePreviewPosition");
  const badgePreviewDept = document.getElementById("badgePreviewDept");
  const badgePreviewCC = document.getElementById("badgePreviewCC");
  const badgePreviewVerify = document.getElementById("badgePreviewVerify");

  // ── Enrolamiento Facial: Foto de Archivo & Cámara Web ──
  const tabUploadPhoto = document.getElementById("tabUploadPhoto");
  const tabWebcamPhoto = document.getElementById("tabWebcamPhoto");
  const paneUploadPhoto = document.getElementById("paneUploadPhoto");
  const paneWebcamPhoto = document.getElementById("paneWebcamPhoto");

  const photoDropZone = document.getElementById("photoDropZone");
  const empPhotoInput = document.getElementById("empPhotoInput");
  const btnBrowsePhoto = document.getElementById("btnBrowsePhoto");

  const webcamVideo = document.getElementById("webcamVideo");
  const webcamCanvas = document.getElementById("webcamCanvas");
  const btnSnapPhoto = document.getElementById("btnSnapPhoto");
  const btnCloseCamera = document.getElementById("btnCloseCamera");
  const cameraSelectWrap = document.getElementById("cameraSelectWrap");
  const cameraSelect = document.getElementById("cameraSelect");

  const photoPreviewContainer = document.getElementById("photoPreviewContainer");
  const photoPreviewImg = document.getElementById("photoPreviewImg");
  const photoPreviewName = document.getElementById("photoPreviewName");
  const btnChangePhoto = document.getElementById("btnChangePhoto");
  const btnRemovePhoto = document.getElementById("btnRemovePhoto");

  let currentPhotoBase64 = null;
  let webcamStream = null;

  let employeeCatalogsLoaded = false;

  function updateEmployeeBadgePreview() {
    const fn = (newFirstName ? newFirstName.value.trim() : "");
    const ln = (newLastName ? newLastName.value.trim() : "");
    const fullName = (fn || ln) ? `${fn} ${ln}`.trim() : "Nombre del Empleado";
    if (badgePreviewName) badgePreviewName.textContent = fullName;

    if (badgePreviewAvatar) {
      if (currentPhotoBase64) {
        badgePreviewAvatar.innerHTML = `<img src="${currentPhotoBase64}" style="width:100%;height:100%;object-fit:cover;border-radius:50%;border:2px solid var(--green-neon);" alt="Rostro">`;
        badgePreviewAvatar.classList.add("active-init");
      } else {
        const initials = ((fn ? fn[0] : "") + (ln ? ln[0] : "")).toUpperCase();
        if (initials) {
          badgePreviewAvatar.textContent = initials;
          badgePreviewAvatar.classList.add("active-init");
        } else {
          badgePreviewAvatar.innerHTML = `
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          `;
          badgePreviewAvatar.classList.remove("active-init");
        }
      }
    }

    if (badgePreviewCode) {
      badgePreviewCode.textContent = (newEmpCode && newEmpCode.value.trim()) ? newEmpCode.value.trim() : "----";
    }

    if (badgePreviewPosition && newEmpPosition) {
      const posOpt = newEmpPosition.options[newEmpPosition.selectedIndex];
      badgePreviewPosition.textContent = (posOpt && posOpt.value) ? posOpt.text : "Sin cargo seleccionado";
    }

    if (badgePreviewDept && newEmpDept) {
      const deptOpt = newEmpDept.options[newEmpDept.selectedIndex];
      badgePreviewDept.textContent = (deptOpt && deptOpt.value) ? deptOpt.text : "Sin departamento";
    }

    if (badgePreviewCC && newEmpCostCenter) {
      const ccOpt = newEmpCostCenter.options[newEmpCostCenter.selectedIndex];
      badgePreviewCC.textContent = (ccOpt && ccOpt.value) ? ccOpt.text : "--";
    }

    if (badgePreviewCompany && newEmpCompany) {
      const compOpt = newEmpCompany.options[newEmpCompany.selectedIndex];
      badgePreviewCompany.textContent = (compOpt && compOpt.value) ? compOpt.text.split(" ")[0] : "PLASTITEC";
    }

    if (badgePreviewType && newEmpType) {
      const typeOpt = newEmpType.options[newEmpType.selectedIndex];
      badgePreviewType.textContent = (typeOpt && typeOpt.value === "3") ? "Temporal (3)" : "Fijo (1)";
    }

    if (badgePreviewVerify && newEmpVerifyMode) {
      const vMode = newEmpVerifyMode.value;
      if (vMode === "15") {
        badgePreviewVerify.innerHTML = '<span class="verify-icon">👤</span> Solo Rostro (15)';
      } else if (vMode === "1") {
        badgePreviewVerify.innerHTML = '<span class="verify-icon">👆</span> Solo Huella (1)';
      } else {
        badgePreviewVerify.innerHTML = '<span class="verify-icon">⚙️</span> Cualquier Método';
      }
    }
  }

  // Bind live updates
  [newEmpCode, newFirstName, newLastName].forEach((input) => {
    if (input) input.addEventListener("input", updateEmployeeBadgePreview);
  });
  [newEmpCompany, newEmpCostCenter, newEmpDept, newEmpPosition, newEmpType, newEmpVerifyMode].forEach((sel) => {
    if (sel) sel.addEventListener("change", updateEmployeeBadgePreview);
  });

  // Quick areas select/clear
  if (btnSelectAllAreas) {
    btnSelectAllAreas.addEventListener("click", () => {
      if (!newEmpAreasContainer) return;
      newEmpAreasContainer.querySelectorAll("input[name='emp_area']").forEach((cb) => {
        cb.checked = true;
        const item = cb.closest(".area-check-item");
        if (item) item.classList.add("selected");
      });
    });
  }

  if (btnClearAllAreas) {
    btnClearAllAreas.addEventListener("click", () => {
      if (!newEmpAreasContainer) return;
      newEmpAreasContainer.querySelectorAll("input[name='emp_area']").forEach((cb) => {
        cb.checked = false;
        const item = cb.closest(".area-check-item");
        if (item) item.classList.remove("selected");
      });
    });
  }

  // ── Funciones de Enrolamiento Facial (Foto & Webcam) ──
  function setEmployeePhoto(base64Data, filename) {
    currentPhotoBase64 = base64Data;
    if (photoPreviewImg) photoPreviewImg.src = base64Data;
    if (photoPreviewName) photoPreviewName.textContent = filename || "foto_enrolamiento.jpg";
    if (photoPreviewContainer) photoPreviewContainer.style.display = "block";
    updateEmployeeBadgePreview();
  }

  function clearEmployeePhoto() {
    currentPhotoBase64 = null;
    if (photoPreviewImg) photoPreviewImg.src = "";
    if (empPhotoInput) empPhotoInput.value = "";
    if (photoPreviewContainer) photoPreviewContainer.style.display = "none";
    updateEmployeeBadgePreview();
  }

  function switchPhotoTab(tab) {
    if (tab === "upload") {
      if (tabUploadPhoto) tabUploadPhoto.classList.add("active");
      if (tabWebcamPhoto) tabWebcamPhoto.classList.remove("active");
      if (paneUploadPhoto) paneUploadPhoto.style.display = "block";
      if (paneWebcamPhoto) paneWebcamPhoto.style.display = "none";
      stopWebcam();
    } else {
      if (tabWebcamPhoto) tabWebcamPhoto.classList.add("active");
      if (tabUploadPhoto) tabUploadPhoto.classList.remove("active");
      if (paneWebcamPhoto) paneWebcamPhoto.style.display = "block";
      if (paneUploadPhoto) paneUploadPhoto.style.display = "none";
      startWebcam();
    }
  }

  async function startWebcam(deviceId = null) {
    stopWebcam();
    try {
      const constraints = {
        video: deviceId ? { deviceId: { exact: deviceId } } : {
          width: { ideal: 640 },
          height: { ideal: 480 },
          facingMode: "user"
        },
        audio: false
      };
      webcamStream = await navigator.mediaDevices.getUserMedia(constraints);
      if (webcamVideo) {
        webcamVideo.srcObject = webcamStream;
        await webcamVideo.play();
      }

      // Enumerar cámaras disponibles
      if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter((d) => d.kind === "videoinput");
        if (videoDevices.length > 1 && cameraSelect && cameraSelectWrap) {
          cameraSelect.innerHTML = "";
          videoDevices.forEach((dev, idx) => {
            const opt = document.createElement("option");
            opt.value = dev.deviceId;
            opt.textContent = dev.label || `Cámara ${idx + 1}`;
            if (deviceId && dev.deviceId === deviceId) opt.selected = true;
            cameraSelect.appendChild(opt);
          });
          cameraSelectWrap.style.display = "flex";
        }
      }
    } catch (err) {
      alert("No se pudo iniciar la cámara web: " + (err.message || err.name) + "\nPuedes adjuntar un archivo de foto directamente.");
      switchPhotoTab("upload");
    }
  }

  function stopWebcam() {
    if (webcamStream) {
      webcamStream.getTracks().forEach((t) => t.stop());
      webcamStream = null;
    }
    if (webcamVideo) {
      webcamVideo.srcObject = null;
    }
  }

  function snapWebcamPhoto() {
    if (!webcamVideo || !webcamCanvas || !webcamStream) return;
    const w = webcamVideo.videoWidth || 640;
    const h = webcamVideo.videoHeight || 480;
    webcamCanvas.width = w;
    webcamCanvas.height = h;
    const ctx = webcamCanvas.getContext("2d");
    // Voltear imagen para efecto espejo natural
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(webcamVideo, 0, 0, w, h);

    const b64 = webcamCanvas.toDataURL("image/jpeg", 0.92);
    setEmployeePhoto(b64, "captura_camara_" + Date.now() + ".jpg");
    stopWebcam();
    switchPhotoTab("upload");
  }

  function handlePhotoFile(file) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      alert("Por favor selecciona un archivo de imagen válido (JPG, PNG, WEBP).");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      setEmployeePhoto(e.target.result, file.name);
    };
    reader.readAsDataURL(file);
  }

  // Listeners de pestañas y botones de foto
  if (tabUploadPhoto) tabUploadPhoto.addEventListener("click", () => switchPhotoTab("upload"));
  if (tabWebcamPhoto) tabWebcamPhoto.addEventListener("click", () => switchPhotoTab("webcam"));
  if (btnSnapPhoto) btnSnapPhoto.addEventListener("click", snapWebcamPhoto);
  if (btnCloseCamera) btnCloseCamera.addEventListener("click", () => switchPhotoTab("upload"));
  if (cameraSelect) cameraSelect.addEventListener("change", (e) => startWebcam(e.target.value));

  if (btnBrowsePhoto && empPhotoInput) {
    btnBrowsePhoto.addEventListener("click", () => empPhotoInput.click());
  }
  if (empPhotoInput) {
    empPhotoInput.addEventListener("change", (e) => {
      if (e.target.files && e.target.files[0]) {
        handlePhotoFile(e.target.files[0]);
      }
    });
  }

  if (photoDropZone) {
    photoDropZone.addEventListener("click", (e) => {
      if (e.target !== btnBrowsePhoto && empPhotoInput) {
        empPhotoInput.click();
      }
    });
    photoDropZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      photoDropZone.classList.add("dragover");
    });
    photoDropZone.addEventListener("dragleave", () => {
      photoDropZone.classList.remove("dragover");
    });
    photoDropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      photoDropZone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
        handlePhotoFile(e.dataTransfer.files[0]);
      }
    });
  }

  if (btnChangePhoto) {
    btnChangePhoto.addEventListener("click", () => {
      if (empPhotoInput) empPhotoInput.click();
    });
  }
  if (btnRemovePhoto) {
    btnRemovePhoto.addEventListener("click", clearEmployeePhoto);
  }

  async function loadEmployeeFormCatalogs() {
    if (newHireDate && !newHireDate.value) {
      newHireDate.value = formatDateISO(new Date());
    }

    if (employeeCatalogsLoaded) return;

    // 1. Cargar Empresas
    try {
      const res = await fetch("/api/companies");
      const data = await res.json();
      newEmpCompany.innerHTML = "";
      (data.companies || []).forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = `${c.name} (${c.code})`;
        newEmpCompany.appendChild(opt);
      });
    } catch (e) {
      newEmpCompany.innerHTML = '<option value="1">PLASTITEC (01)</option>';
    }

    // 1.1 Cargar Compañías dependientes (PLASTITECSA / GRANSERVICIOS)
    try {
      const res = await fetch("/api/subcompanies");
      const data = await res.json();
      if (newEmpBranch) {
        newEmpBranch.innerHTML = "";
        (data.subcompanies || []).forEach((b) => {
          const opt = document.createElement("option");
          opt.value = b.id;
          opt.textContent = b.name;
          newEmpBranch.appendChild(opt);
        });
      }
    } catch (e) {
      if (newEmpBranch) {
        newEmpBranch.innerHTML = '<option value="1">PLASTITECSA</option><option value="2">GRANSERVICIOS</option>';
      }
    }

    // 2. Cargar Centros de Costos
    try {
      const res = await fetch("/api/costcenters");
      const data = await res.json();
      newEmpCostCenter.innerHTML = '<option value="">-- Sin Centro de Costos --</option>';
      (data.costcenters || []).forEach((cc) => {
        const opt = document.createElement("option");
        opt.value = cc.id;
        opt.textContent = `${cc.name} (${cc.code})`;
        newEmpCostCenter.appendChild(opt);
      });
    } catch (e) {
      newEmpCostCenter.innerHTML = '<option value="">Error cargando centros de costos</option>';
    }

    // 3. Cargar Departamentos
    try {
      const res = await fetch("/api/departments");
      const data = await res.json();
      newEmpDept.innerHTML = '<option value="">-- Seleccione Departamento --</option>';
      (data.departments || []).forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = `${d.name} (${d.code})`;
        newEmpDept.appendChild(opt);
      });
    } catch (e) {
      newEmpDept.innerHTML = '<option value="">Error cargando departamentos</option>';
    }

    // 4. Cargar Cargos / Posiciones
    try {
      const res = await fetch("/api/positions");
      const data = await res.json();
      newEmpPosition.innerHTML = '<option value="">-- Seleccione Cargo --</option>';
      (data.positions || []).forEach((p) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.textContent = `${p.name} (${p.code})`;
        newEmpPosition.appendChild(opt);
      });
    } catch (e) {
      newEmpPosition.innerHTML = '<option value="">Error cargando cargos</option>';
    }

    // 5. Cargar Áreas
    try {
      const res = await fetch("/api/areas");
      const data = await res.json();
      const areas = data.areas || [];
      if (areas.length === 0) {
        newEmpAreasContainer.innerHTML = '<span class="loading-inline-text">No se encontraron áreas</span>';
      } else {
        newEmpAreasContainer.innerHTML = areas.map((a) => `
          <label class="area-check-item">
            <input type="checkbox" name="emp_area" value="${a.id}" />
            <span>${escapeHtml(a.name)} (${escapeHtml(a.code)})</span>
          </label>
        `).join("");

        // Agregar listener para marcar clase visual
        newEmpAreasContainer.querySelectorAll(".area-check-item").forEach((label) => {
          const chk = label.querySelector("input[type='checkbox']");
          chk.addEventListener("change", () => {
            label.classList.toggle("selected", chk.checked);
          });
        });
      }
    } catch (e) {
      newEmpAreasContainer.innerHTML = '<span class="loading-inline-text">Error cargando áreas</span>';
    }

    employeeCatalogsLoaded = true;
    updateEmployeeBadgePreview();
  }

  if (formNuevoEmpleado) {
    formNuevoEmpleado.addEventListener("submit", async (e) => {
      e.preventDefault();
      hideNewEmpAlert();

      const codeVal = newEmpCode.value.trim();
      const firstVal = newFirstName.value.trim();
      const lastVal = newLastName.value.trim();
      const deptVal = parseInt(newEmpDept.value, 10);
      const posVal = parseInt(newEmpPosition.value, 10) || null;
      const compVal = parseInt(newEmpCompany.value, 10) || 1;
      const branchVal = newEmpBranch ? (parseInt(newEmpBranch.value, 10) || null) : null;
      const costCenterVal = parseInt(newEmpCostCenter.value, 10) || null;
      const empTypeVal = parseInt(newEmpType.value, 10) || 1;
      const verifyModeVal = parseInt(newEmpVerifyMode.value, 10);
      const genderVal = newGender.value || "M";
      const hireVal = newHireDate.value || null;
      const nationalVal = newNational.value.trim() || null;
      const mobileVal = newEmpMobile.value.trim() || null;
      const emailVal = newEmpEmail.value.trim() || null;

      // Obtener áreas seleccionadas
      const selectedAreaCheckboxes = newEmpAreasContainer.querySelectorAll("input[name='emp_area']:checked");
      const areaIds = Array.from(selectedAreaCheckboxes).map((cb) => parseInt(cb.value, 10));

      if (!codeVal) {
        showNewEmpAlert("error", "Debes ingresar el código de empleado.");
        newEmpCode.focus();
        return;
      }
      if (!firstVal || !lastVal) {
        showNewEmpAlert("error", "Nombres y apellidos son obligatorios.");
        return;
      }
      if (!deptVal) {
        showNewEmpAlert("error", "Debes seleccionar un departamento existente de la lista.");
        newEmpDept.focus();
        return;
      }
      if (areaIds.length === 0) {
        showNewEmpAlert("error", "Debes marcar al menos un área de marcación autorizada.");
        return;
      }

      const payload = {
        emp_code: codeVal,
        first_name: firstVal,
        last_name: lastVal,
        department_id: deptVal,
        area_ids: areaIds,
        position_id: posVal,
        company_id: compVal,
        branch_id: branchVal,
        cost_center_id: costCenterVal,
        emp_type: empTypeVal,
        verify_mode: isNaN(verifyModeVal) ? 15 : verifyModeVal,
        hire_date: hireVal,
        gender: genderVal,
        national: nationalVal,
        mobile: mobileVal,
        email: emailVal,
        photo_b64: currentPhotoBase64 || null,
      };

      setNewEmpSubmitting(true);

      try {
        const res = await fetch("/api/employees", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || "Error al crear el empleado en BioTime");
        }

        showNewEmpAlert("success", `✓ ${data.message || 'Empleado creado con éxito.'}`);
        
        // Reset inputs y foto
        newEmpCode.value = "";
        newFirstName.value = "";
        newLastName.value = "";
        newNational.value = "";
        newEmpMobile.value = "";
        newEmpEmail.value = "";
        clearEmployeePhoto();
        stopWebcam();
        newEmpAreasContainer.querySelectorAll("input[name='emp_area']").forEach((cb) => {
          cb.checked = false;
          cb.closest(".area-check-item").classList.remove("selected");
        });

        updateEmployeeBadgePreview();

        // Actualizar select de empleados de la Malla sin bloquear
        loadMatrixEmployees(matrixDeptSelect.value);

      } catch (err) {
        showNewEmpAlert("error", `✗ ${err.message}`);
      } finally {
        setNewEmpSubmitting(false);
      }
    });
  }

  if (btnResetNewEmp) {
    btnResetNewEmp.addEventListener("click", () => {
      formNuevoEmpleado.reset();
      clearEmployeePhoto();
      stopWebcam();
      hideNewEmpAlert();
      newEmpAreasContainer.querySelectorAll(".area-check-item").forEach((lbl) => {
        lbl.classList.remove("selected");
      });
      if (newHireDate) newHireDate.value = formatDateISO(new Date());
      if (newEmpVerifyMode) newEmpVerifyMode.value = "15";
      if (newEmpType) newEmpType.value = "1";
      updateEmployeeBadgePreview();
    });
  }

  function setNewEmpSubmitting(isSubmitting) {
    if (!btnSubmitNewEmp) return;
    btnSubmitNewEmp.disabled = isSubmitting;
    btnSubmitNewEmpText.textContent = isSubmitting ? "Guardando en BioTime..." : "Guardar Empleado en BioTime";
  }

  function showNewEmpAlert(type, message) {
    if (!newEmpAlert) return;
    newEmpAlert.className = `alert-feedback-box ${type}`;
    newEmpAlert.textContent = message;
    newEmpAlert.classList.remove("hidden");
    newEmpAlert.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function hideNewEmpAlert() {
    if (!newEmpAlert) return;
    newEmpAlert.classList.add("hidden");
  }

  // ───────────────────────────────────────────────────────────────────────────
  // 12. CENTRO DE REPORTES DE ASISTENCIA & BIOMETRÍA
  // ───────────────────────────────────────────────────────────────────────────
  let reportTypesList = [];
  let currentReportId = "first_last";
  let reportCurrentPage = 1;
  const reportLimit = 50;
  let reportTotalRecords = 0;
  let reportInitialized = false;

  const reportTypesGrid = document.getElementById("reportTypesGrid");
  const activeReportTitle = document.getElementById("activeReportTitle");
  const reportTableTitle = document.getElementById("reportTableTitle");
  const reportCompanySelect = document.getElementById("reportCompanySelect");
  const reportDeptSelect = document.getElementById("reportDeptSelect");
  const reportStartDate = document.getElementById("reportStartDate");
  const reportEndDate = document.getElementById("reportEndDate");
  const reportEmpSearch = document.getElementById("reportEmpSearch");
  const btnGenerateReport = document.getElementById("btnGenerateReport");
  const btnGenerateReportText = document.getElementById("btnGenerateReportText");
  const btnCalcularBioTime = document.getElementById("btnCalcularBioTime");
  const btnCalcularBioTimeText = document.getElementById("btnCalcularBioTimeText");
  const btnExportReportExcel = document.getElementById("btnExportReportExcel");

  const reportMetricsRow = document.getElementById("reportMetricsRow");
  const metricTotalRecords = document.getElementById("metricTotalRecords");
  const metricUniqueEmps = document.getElementById("metricUniqueEmps");
  const metricDateRange = document.getElementById("metricDateRange");
  const metricCardTotalHours = document.getElementById("metricCardTotalHours");
  const metricTotalHours = document.getElementById("metricTotalHours");
  const metricCardOvertime = document.getElementById("metricCardOvertime");
  const metricTotalOvertime = document.getElementById("metricTotalOvertime");
  const metricCardSurcharges = document.getElementById("metricCardSurcharges");
  const metricTotalSurcharges = document.getElementById("metricTotalSurcharges");

  const reportTableHead = document.getElementById("reportTableHead");
  const reportTableBody = document.getElementById("reportTableBody");
  const reportRecordCount = document.getElementById("reportRecordCount");
  const btnReportPrevPage = document.getElementById("btnReportPrevPage");
  const btnReportNextPage = document.getElementById("btnReportNextPage");
  const reportPageInfo = document.getElementById("reportPageInfo");

  const btnReportQuickCurrentMonth = document.getElementById("btnReportQuickCurrentMonth");
  const btnReportQuickPrevMonth = document.getElementById("btnReportQuickPrevMonth");
  const btnReportQuick15Days = document.getElementById("btnReportQuick15Days");

  async function initReportView() {
    if (reportInitialized) return;
    reportInitialized = true;

    // 1. Fechas por defecto (inicio de mes actual a hoy)
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    if (reportStartDate) reportStartDate.value = formatDateISO(firstDay);
    if (reportEndDate) reportEndDate.value = formatDateISO(now);

    // 2. Cargar catálogo de tipos de reportes
    try {
      const res = await fetch("/api/reports/types");
      const data = await res.json();
      reportTypesList = data.reports || [];
      renderReportTypeCards();
    } catch (e) {
      console.error("Error cargando tipos de reporte:", e);
    }

    // 3. Cargar empresas y departamentos en los filtros de reporte
    try {
      const resDepts = await fetch("/api/departments");
      const dataDepts = await resDepts.json();
      if (reportDeptSelect) {
        reportDeptSelect.innerHTML = '<option value="">Todos los Departamentos</option>';
        (dataDepts.departments || []).forEach((d) => {
          const opt = document.createElement("option");
          opt.value = d.id;
          opt.textContent = d.name;
          reportDeptSelect.appendChild(opt);
        });
      }
    } catch (e) {
      console.error("Error cargando departamentos en reportes:", e);
    }

    try {
      const resSubs = await fetch("/api/subcompanies");
      const dataSubs = await resSubs.json();
      if (reportCompanySelect) {
        reportCompanySelect.innerHTML = '<option value="">Todas las Compañías</option>';
        (dataSubs.subcompanies || []).forEach((c) => {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = `${c.name} (${c.code})`;
          reportCompanySelect.appendChild(opt);
        });
      }
    } catch (e) {
      if (reportCompanySelect) {
        reportCompanySelect.innerHTML = `
          <option value="">Todas las Compañías</option>
          <option value="1">PLASTITECSA</option>
          <option value="2">GRANSERVICIOS</option>
        `;
      }
    }
  }

  function renderReportTypeCards() {
    if (!reportTypesGrid) return;
    reportTypesGrid.innerHTML = "";

    reportTypesList.forEach((rep) => {
      const card = document.createElement("div");
      card.className = `report-type-card ${rep.id === currentReportId ? 'active' : ''}`;
      card.innerHTML = `
        <div class="report-card-top">
          <span class="report-card-icon">${rep.icon || '📄'}</span>
          <span class="report-card-badge">${rep.id}</span>
        </div>
        <h4 class="report-card-title">${rep.name}</h4>
        <p class="report-card-desc">${rep.description}</p>
      `;

      card.addEventListener("click", () => {
        currentReportId = rep.id;
        document.querySelectorAll(".report-type-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        if (activeReportTitle) activeReportTitle.textContent = `Filtros: ${rep.name}`;
        if (reportTableTitle) reportTableTitle.textContent = rep.name;
        reportCurrentPage = 1;
        loadReportData(1);
      });

      reportTypesGrid.appendChild(card);
    });

    const activeRep = reportTypesList.find((r) => r.id === currentReportId) || reportTypesList[0];
    if (activeRep) {
      if (activeReportTitle) activeReportTitle.textContent = `Filtros: ${activeRep.name}`;
      if (reportTableTitle) reportTableTitle.textContent = activeRep.name;
    }
  }

  async function loadReportData(page = 1) {
    if (!reportStartDate || !reportEndDate) return;
    const start = reportStartDate.value;
    const end = reportEndDate.value;
    if (!start || !end) {
      alert("Debes seleccionar Fecha Inicio y Fecha Fin.");
      return;
    }

    reportCurrentPage = page;
    setReportLoading(true);

    const compVal = reportCompanySelect ? reportCompanySelect.value : "";
    const deptVal = reportDeptSelect ? reportDeptSelect.value : "";
    const empVal = reportEmpSearch ? reportEmpSearch.value.trim() : "";

    const params = new URLSearchParams({
      report_type: currentReportId,
      start_date: start,
      end_date: end,
      page: page,
      limit: reportLimit,
    });
    if (compVal) params.append("company_id", compVal);
    if (deptVal) params.append("department_id", deptVal);
    if (empVal) params.append("emp_code", empVal);

    try {
      const res = await fetch(`/api/reports/data?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Error al obtener datos del reporte");
      }

      reportTotalRecords = data.total || 0;
      renderReportTable(data.columns || [], data.data || []);
      renderReportMetrics(data.metrics || {});
      updateReportPagination(page, reportTotalRecords);

    } catch (err) {
      alert(`Error al generar reporte: ${err.message}`);
      if (reportTableBody) {
        reportTableBody.innerHTML = `
          <tr>
            <td colspan="10" class="empty-state-cell" style="color: #f87171;">
              Error: ${err.message}
            </td>
          </tr>
        `;
      }
    } finally {
      setReportLoading(false);
    }
  }

  function renderReportTable(columns, rows) {
    if (!reportTableHead || !reportTableBody) return;

    // Encabezados
    reportTableHead.innerHTML = "";
    const trHead = document.createElement("tr");
    columns.forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col.label;
      trHead.appendChild(th);
    });
    reportTableHead.appendChild(trHead);

    // Filas
    reportTableBody.innerHTML = "";
    if (!rows || rows.length === 0) {
      reportTableBody.innerHTML = `
        <tr>
          <td colspan="${columns.length || 8}" class="empty-state-cell">
            <div class="empty-state-box">
              <p>No se encontraron registros para los filtros seleccionados en este período.</p>
            </div>
          </td>
        </tr>
      `;
      if (reportRecordCount) reportRecordCount.textContent = "0 registros";
      return;
    }

    if (reportRecordCount) reportRecordCount.textContent = `${reportTotalRecords} registros`;

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((col) => {
        const td = document.createElement("td");
        const val = row[col.key];

        if (col.key === "punch_state_str") {
          const lower = String(val || "").toLowerCase();
          let cls = "entrada";
          if (lower.includes("salida")) cls = "salida";
          if (lower.includes("refrigerio") || lower.includes("almuerzo")) cls = "refrigerio";
          td.innerHTML = `<span class="chip-punch ${cls}">${val}</span>`;
        } else if (col.key === "severity") {
          const lower = String(val || "").toLowerCase();
          let cls = "leve";
          if (lower.includes("moderada")) cls = "moderada";
          if (lower.includes("crítica") || lower.includes("critica")) cls = "critica";
          td.innerHTML = `<span class="chip-status ${cls}">${val}</span>`;
        } else if (col.key === "status" && String(val).toLowerCase().includes("inasistencia")) {
          td.innerHTML = `<span class="chip-status critica">Inasistencia</span>`;
        } else if (col.key === "attendance_rate") {
          const num = parseFloat(String(val).replace("%", "")) || 0;
          const colColor = num >= 90 ? "#4ade80" : (num >= 75 ? "#fbbf24" : "#f87171");
          td.innerHTML = `<strong style="color: ${colColor}; font-family: var(--font-mono);">${val}</strong>`;
        } else if (["dayOT", "ntOT", "daySundayOT", "ntSundayOT"].includes(col.key)) {
          const n = parseFloat(val) || 0;
          td.innerHTML = n > 0 ? `<span class="badge-ot">${n.toFixed(2)}h</span>` : `<span class="val-zero">0.00</span>`;
        } else if (["pc_5", "pc_7", "pc_8"].includes(col.key)) {
          const n = parseFloat(val) || 0;
          td.innerHTML = n > 0 ? `<span class="badge-surcharge">${n.toFixed(2)}h</span>` : `<span class="val-zero">0.00</span>`;
        } else if (col.key === "total_time") {
          const n = parseFloat(val) || 0;
          td.innerHTML = n > 0 ? `<span class="badge-hours-total">${n.toFixed(2)}h</span>` : `<span class="val-zero">0.00</span>`;
        } else if (["dayWT", "ntWT"].includes(col.key)) {
          const n = parseFloat(val) || 0;
          td.innerHTML = n > 0 ? `<span style="font-family: var(--font-mono); font-weight: 500;">${n.toFixed(2)}h</span>` : `<span class="val-zero">0.00</span>`;
        } else if (col.key === "emp_code" || col.key === "att_date" || col.key === "first_punch" || col.key === "last_punch" || col.key === "check_in" || col.key === "check_out") {
          td.innerHTML = `<span style="font-family: var(--font-mono); font-weight: 500;">${val !== undefined && val !== null ? val : '--'}</span>`;
        } else {
          td.textContent = (val !== undefined && val !== null && val !== "") ? val : "--";
        }

        tr.appendChild(td);
      });
      reportTableBody.appendChild(tr);
    });
  }

  function renderReportMetrics(metrics) {
    if (!reportMetricsRow) return;
    reportMetricsRow.style.display = "flex";
    if (metricTotalRecords) metricTotalRecords.textContent = metrics.total_records || 0;
    if (metricUniqueEmps) metricUniqueEmps.textContent = metrics.unique_employees || 0;
    if (metricDateRange) metricDateRange.textContent = metrics.date_range || "--";

    if (metrics.total_hours !== undefined) {
      if (metricCardTotalHours) { metricCardTotalHours.style.display = "block"; if (metricTotalHours) metricTotalHours.textContent = `${metrics.total_hours}h`; }
      if (metricCardOvertime) { metricCardOvertime.style.display = "block"; if (metricTotalOvertime) metricTotalOvertime.textContent = `${metrics.total_overtime}h`; }
      if (metricCardSurcharges) { metricCardSurcharges.style.display = "block"; if (metricTotalSurcharges) metricTotalSurcharges.textContent = `${metrics.total_surcharges}h`; }
    } else {
      if (metricCardTotalHours) metricCardTotalHours.style.display = "none";
      if (metricCardOvertime) metricCardOvertime.style.display = "none";
      if (metricCardSurcharges) metricCardSurcharges.style.display = "none";
    }
  }

  function updateReportPagination(page, total) {
    const totalPages = Math.max(1, Math.ceil(total / reportLimit));
    if (reportPageInfo) reportPageInfo.textContent = `Página ${page} de ${totalPages}`;
    if (btnReportPrevPage) btnReportPrevPage.disabled = (page <= 1);
    if (btnReportNextPage) btnReportNextPage.disabled = (page >= totalPages);
  }

  function setReportLoading(isLoading) {
    if (!btnGenerateReport) return;
    btnGenerateReport.disabled = isLoading;
    if (btnGenerateReportText) {
      btnGenerateReportText.textContent = isLoading ? "Consultando BioTime..." : "Generar Reporte";
    }
    if (isLoading && reportTableBody) {
      reportTableBody.innerHTML = `
        <tr>
          <td colspan="10" class="empty-state-cell">
            <div class="empty-state-box">
              <span class="loading-inline-text">Procesando registros de BioTime en tiempo real...</span>
            </div>
          </td>
        </tr>
      `;
    }
  }

  function exportReportExcel() {
    if (!reportStartDate || !reportEndDate) return;
    const start = reportStartDate.value;
    const end = reportEndDate.value;
    if (!start || !end) {
      alert("Debes seleccionar Fecha Inicio y Fecha Fin para exportar.");
      return;
    }

    const compVal = reportCompanySelect ? reportCompanySelect.value : "";
    const deptVal = reportDeptSelect ? reportDeptSelect.value : "";
    const empVal = reportEmpSearch ? reportEmpSearch.value.trim() : "";

    const params = new URLSearchParams({
      report_type: currentReportId,
      start_date: start,
      end_date: end,
    });
    if (compVal) params.append("company_id", compVal);
    if (deptVal) params.append("department_id", deptVal);
    if (empVal) params.append("emp_code", empVal);

    window.location.href = `/api/reports/export?${params.toString()}`;
  }

  // Event Listeners del Módulo de Reportes
  if (btnGenerateReport) {
    btnGenerateReport.addEventListener("click", () => {
      reportCurrentPage = 1;
      loadReportData(1);
    });
  }

  if (btnCalcularBioTime) {
    btnCalcularBioTime.addEventListener("click", async () => {
      if (!reportStartDate || !reportEndDate) return;
      const start = reportStartDate.value;
      const end = reportEndDate.value;
      if (!start || !end) {
        alert("Debes seleccionar Fecha Inicio y Fecha Fin para calcular en BioTime.");
        return;
      }

      btnCalcularBioTime.disabled = true;
      if (btnCalcularBioTimeText) btnCalcularBioTimeText.textContent = "Calculando en BioTime...";

      try {
        const empVal = reportEmpSearch ? reportEmpSearch.value.trim() : "";
        const payload = {
          start_date: start,
          end_date: end,
          emp_codes: empVal ? [empVal] : null
        };
        const res = await fetch("/api/reports/calculate_biotime", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error en el cálculo de BioTime");

        alert(`✓ ${data.message || 'Cálculo terminado en BioTime'}\nEmpleados procesados: ${data.target_employees || 'Lote principal'}\nPeríodo: ${start} al ${end}`);
        loadReportData(1);
      } catch (err) {
        alert(`Error al calcular en BioTime: ${err.message}`);
      } finally {
        btnCalcularBioTime.disabled = false;
        if (btnCalcularBioTimeText) btnCalcularBioTimeText.textContent = "Calcular en BioTime";
      }
    });
  }

  if (btnExportReportExcel) {
    btnExportReportExcel.addEventListener("click", exportReportExcel);
  }

  if (btnReportPrevPage) {
    btnReportPrevPage.addEventListener("click", () => {
      if (reportCurrentPage > 1) {
        loadReportData(reportCurrentPage - 1);
      }
    });
  }

  if (btnReportNextPage) {
    btnReportNextPage.addEventListener("click", () => {
      const totalPages = Math.ceil(reportTotalRecords / reportLimit);
      if (reportCurrentPage < totalPages) {
        loadReportData(reportCurrentPage + 1);
      }
    });
  }

  // Botones Rápidos de Fechas para Reportes
  if (btnReportQuickCurrentMonth) {
    btnReportQuickCurrentMonth.addEventListener("click", () => {
      const now = new Date();
      const first = new Date(now.getFullYear(), now.getMonth(), 1);
      reportStartDate.value = formatDateISO(first);
      reportEndDate.value = formatDateISO(now);
    });
  }

  if (btnReportQuickPrevMonth) {
    btnReportQuickPrevMonth.addEventListener("click", () => {
      const now = new Date();
      const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const last = new Date(now.getFullYear(), now.getMonth(), 0);
      reportStartDate.value = formatDateISO(first);
      reportEndDate.value = formatDateISO(last);
    });
  }

  if (btnReportQuick15Days) {
    btnReportQuick15Days.addEventListener("click", () => {
      const now = new Date();
      const prev15 = new Date();
      prev15.setDate(now.getDate() - 15);
      reportStartDate.value = formatDateISO(prev15);
      reportEndDate.value = formatDateISO(now);
    });
  }
});
