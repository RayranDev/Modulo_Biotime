# BioTime Integration & Attendance Management Module

Comprehensive integration module and web dashboard for ZKTeco BioTime API. Built with Python (FastAPI), Pandas, OpenPyXL, and a vanilla JS/CSS web interface.

---

## 📌 Overview

This project provides a robust API client, matrix attendance engine, reporting toolkit, and interactive explorer for BioTime servers. It is designed to audit attendance records, resolve punch-to-shift assignments, visualize daily/weekly matrices, and export styled audit reports to Excel.

### Key Capabilities

- **BioTime API Client (`biotime_api.py`)**:
  - JWT authentication with token caching and refresh.
  - Automatic pagination (`PAGE_SIZE`), timeout handling, and SSL configuration.
  - Unified queries across core endpoints: employees, punches/transactions, shifts (`attshifts`), timetables/intervals (`timeintervals`), schedules (`attschedules`), departments, areas, terminals, leaves, and calculations.

- **FastAPI Web Server (`server.py`)**:
  - Attendance Matrix calculation: maps theoretical shift intervals against real biometric transactions.
  - Color-coded classification of punches (ontime, late, early departure, overtime, absences).
  - Excel Report Generator: produces styled `.xlsx` reports using OpenPyXL with matrix formatting and summary sheets.
  - Management API endpoints: employee sync, shift discovery, and transaction audits.

- **Interactive Web Interface (`static/`)**:
  - Modern dashboard for viewing employee lists, shifts, punch logs, and real-time matrix attendance.
  - Export controls and date-range filtering.

- **Specifications & Reference Documents (`Claude outputs/`)**:
  - `ESPECIFICACION-REGLAS-SIRH-v1.md`: SIRH business rules and shift logic specification.
  - `PROMPT-MAESTRO-SIRH-PLASTITEC-v2.md`: Master architecture context and reference rules.

---

## 🏗️ Project Structure

```text
MODULO_BIOTIME/
├── Claude outputs/                 # Business rules and reference specifications
│   ├── ESPECIFICACION-REGLAS-SIRH-v1.md
│   └── PROMPT-MAESTRO-SIRH-PLASTITEC-v2.md
├── static/                         # Web frontend assets
│   ├── app.js                      # UI logic and API communication
│   ├── index.html                  # Dashboard layout
│   └── style.css                   # Interface styling
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore configuration (protects credentials and cache)
├── biotime_api.py                  # BioTime REST API client implementation
├── config.py                       # Centralized configuration loader (from .env)
├── probe_v1_v2.py                  # Endpoint probing and diagnostic script
├── requirements.txt                # Python dependencies
├── server.py                       # FastAPI application & matrix generation engine
└── README.md                       # Project documentation
```

---

## ⚙️ Requirements & Installation

### Prerequisites

- Python 3.9+
- Access to a BioTime server instance (URL, username, and password)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/RayranDev/Modulo_Biotime.git
   cd Modulo_Biotime
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Copy `.env.example` to `.env` and fill in your BioTime server details:
   ```bash
   copy .env.example .env
   ```
   Edit `.env` with your credentials:
   ```ini
   BIOTIME_BASE_URL=http://your-biotime-server:8000
   BIOTIME_USER=your_username
   BIOTIME_PASS=your_password
   BIOTIME_TIMEOUT=60
   BIOTIME_PAGE_SIZE=500
   BIOTIME_VERIFY_SSL=False
   ```

---

## 🚀 Running the Application

Start the FastAPI application:

```bash
python server.py
```
Or directly with Uvicorn:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Once started, access:
- **Web Dashboard**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **Redoc**: `http://localhost:8000/redoc`

---

## 🏷️ Versioning & Restoration Point

- **Tag `v1.0.0-baseline`**: Marks the fully working baseline of the attendance matrix, Excel export, and BioTime API integration prior to major architectural refactorings.
