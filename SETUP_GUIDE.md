# 🛡️ AdSentinel AI — Complete Setup, Clone & Run Guide

> **AI-powered campaign anomaly detection for smarter alerts, reduced noise, and faster incident response.**

---

## 🌐 Quick Access & Repository Links
- **Live Deployed App**: [https://aisentinel-seven.vercel.app/](https://aisentinel-seven.vercel.app/)
- **GitHub Repository**: [https://github.com/MR-Naveen-S/DEVSPRINT_TEAM_INFINITY](https://github.com/MR-Naveen-S/DEVSPRINT_TEAM_INFINITY)

---

## 📋 Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Option A: Clone & Run Web App Locally (Recommended)](#2-option-a-clone--run-web-app-locally-recommended)
3. [Option B: Run with Node / VS Code Live Server](#3-option-b-run-with-node--vs-code-live-server)
4. [Option C: Run Full Python Anomaly Detection Pipeline](#4-option-c-run-full-python-anomaly-detection-pipeline)
5. [Deploy to Vercel (Your Own Instance)](#5-deploy-to-vercel-your-own-instance)
6. [Architecture & Project Structure](#6-architecture--project-structure)
7. [Troubleshooting & FAQs](#7-troubleshooting--faqs)

---

## 1. Prerequisites

Make sure you have installed:
- **Git** ([Download](https://git-scm.com/downloads))
- **Python 3.8+** ([Download](https://www.python.org/downloads/)) — *Optional, needed for local server or ML pipeline*
- *(Optional)* **Node.js 18+** & **npm** / **Vercel CLI** if deploying yourself.

---

## 2. Option A: Clone & Run Web App Locally (Recommended)

### Step 1: Clone the GitHub Repository
Open your terminal (PowerShell, Command Prompt, or Bash) and run:
```bash
git clone https://github.com/MR-Naveen-S/DEVSPRINT_TEAM_INFINITY.git
cd DEVSPRINT_TEAM_INFINITY
```

### Step 2: Start a Local Web Server
Since modern browsers enforce CORS restrictions when fetching CSV data and modules over the `file://` protocol, start a simple HTTP server from the repository root:

#### Using Python (Built-in, No install required):
```bash
# Python 3
python -m http.server 8080
```

### Step 3: Open in Browser
Visit in your browser:
👉 **[http://localhost:8080/](http://localhost:8080/)**  
*(It will automatically load the interactive dashboard at `http://localhost:8080/M4/web_ui/index.html`)*

---

## 3. Option B: Run with Node / VS Code Live Server

### Using `npx serve` (Node.js):
```bash
npx serve .
```
Open the URL shown in terminal (usually `http://localhost:3000`).

### Using VS Code Live Server Extension:
1. Open the project folder `DEVSPRINT_TEAM_INFINITY` in **VS Code**.
2. Right click on `index.html` or `M4/web_ui/index.html`.
3. Click **"Open with Live Server"**.

---

## 4. Option C: Run Full Python Anomaly Detection Pipeline

If you want to re-run the anomaly detection, baseline calculation, and incident generation models:

### Step 1: Install Python Dependencies
```bash
pip install pandas numpy scikit-learn matplotlib
```

### Step 2: Run Module Pipeline
```bash
# Navigate to M4
cd M4

# 1. Run Anomaly Detection & Baseline Evaluation
python detect.py

# 2. Run Isolation Forest ML Model
python ml_isolation_forest.py

# 3. Run Alert Routing & Explanation Engine
python route_explain.py

# 4. Run Comprehensive Evaluation & Metrics
python evaluate.py

# 5. Run Unit & Regression Tests
python test_evaluate_unit.py
```

All generated alerts, digests, and summary metrics will automatically update in `M4/alerts_all.csv`, `M4/alerts_immediate.csv`, `M4/digest.csv`, and sync with the web UI.

---

## 5. Deploy to Vercel (Your Own Instance)

### Method 1: Deploy via Vercel CLI
```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
vercel --prod
```

### Method 2: Deploy via Vercel Web Dashboard (One-Click)
1. Fork or push this repository to your GitHub account.
2. Go to [https://vercel.com/new](https://vercel.com/new).
3. Import `DEVSPRINT_TEAM_INFINITY`.
4. Keep the default settings:
   - **Framework Preset**: *Other*
   - **Root Directory**: `./`
5. Click **Deploy**. The `vercel.json` in the root automatically routes all assets and pages correctly.

---

## 6. Architecture & Project Structure

```text
DEVSPRINT_TEAM_INFINITY/
├── index.html                   # Root entry point with instant redirect
├── vercel.json                  # Vercel deployment routing & asset config
├── SETUP_GUIDE.md               # Setup and running guide
│
├── M4/                          # Milestone 4 - Core Engine & Web UI
│   ├── web_ui/                  # Production Web Application
│   │   ├── index.html           # 4-in-1 Dashboard Interface
│   │   ├── styles.css           # Modern Cyber Dark Glassmorphic Design System
│   │   └── app.js               # Reactive Analytics Engine, Chart rendering & Modals
│   ├── detect.py                # Core multi-metric anomaly detection engine
│   ├── baseline.py              # 35-day & 180-day baseline computation logic
│   ├── ml_isolation_forest.py   # Machine Learning Isolation Forest detector
│   ├── route_explain.py         # Root cause analysis & Alert routing
│   ├── evaluate.py              # Performance evaluation (Precision/Recall/F1)
│   ├── test_evaluate_unit.py    # Automated test suite
│   ├── alerts_all.csv           # Detected anomaly records
│   ├── alerts_immediate.csv     # High-priority routed alert stream
│   └── digest.csv               # Batched periodic alert digest
│
├── PS-04_campaign_anomaly_alerting/  # Campaign datasets (35d & 180d timeseries)
│   ├── data_35d.csv
│   └── data_180d.csv
└── integration/                 # Integration tests & multi-module orchestrators
```

---

## 7. Troubleshooting & FAQs

| Issue | Cause | Solution |
|---|---|---|
| **CORS error loading CSV files** | Opening `index.html` directly via `file:///` | Run a local server with `python -m http.server 8080` or `npx serve`. |
| **Charts not rendering** | CDN blocked or offline | Ensure internet access is available for Chart.js / FontAwesome CDNs. |
| **Port 8080 in use** | Another app is using port 8080 | Run `python -m http.server 8000` or any other available port. |
