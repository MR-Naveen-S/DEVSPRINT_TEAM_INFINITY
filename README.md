# 🛡️ AdSentinel AI

> **AI-powered campaign anomaly detection for smarter alerts, reduced noise, and faster incident response.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel%20Deployed-10b981?style=for-the-badge&logo=vercel)](https://aisentinel-seven.vercel.app/)
[![GitHub Repo](https://img.shields.io/badge/GitHub-Repository-6366f1?style=for-the-badge&logo=github)](https://github.com/MR-Naveen-S/DEVSPRINT_TEAM_INFINITY)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3b82f6?style=for-the-badge&logo=python)](https://www.python.org/)

---

## 🚀 Quick Links
- 🌐 **Live Web Application:** [https://aisentinel-seven.vercel.app/](https://aisentinel-seven.vercel.app/)
- 📖 **Detailed Setup & Clone Guide:** [`SETUP_GUIDE.md`](./SETUP_GUIDE.md)
- 📊 **Dataset & Benchmark:** [`PS-04_campaign_anomaly_alerting/`](./PS-04_campaign_anomaly_alerting/)
- 💻 **Milestone 4 Source & Web UI:** [`M4/`](./M4/)

---

## 📌 Overview

**AdSentinel AI** is an intelligent monitoring and anomaly detection platform designed for modern advertising campaigns. It continuously analyzes high-dimensional performance metrics (Impressions, Clicks, Spend, Conversions, CTR, CPC, CPA, ROAS), dynamically estimates rolling baselines (35-day & 180-day), and flags critical incidents while suppressing false alarms through root-cause routing and automated digest aggregation.

### 🌟 Key Features
- **4-in-1 Glassmorphic Web Dashboard**:
  1. 📊 **Executive Dashboard**: High-level KPIs, campaign health scores, active anomalies & spend-at-risk analysis.
  2. 🔍 **Baseline Inspector**: Multi-metric timeseries visualizer comparing actuals vs. rolling baseline confidence bands (35d / 180d).
  3. 🔔 **Alert Manager**: Incident triage center with severity filtering, root-cause tags, and immediate vs. digest routing.
  4. 📈 **Evaluation Analytics**: Precision, Recall, F1 score metrics, confusion matrix, and detection speed benchmarks.
- **Dynamic Baseline Estimation**: Adaptive statistical thresholds accounting for seasonality and trend shifts.
- **ML Anomaly Detection**: Unsupervised Isolation Forest model alongside statistical Z-score/IQR bounds.
- **Intelligent Alert Routing**: Classifies anomalies into **Immediate Pager Alerts** (High Severity/ROAS collapse) and **Digest Reports** to eliminate alert fatigue.

---

## ⚡ Quick Start (Run Locally)

### 1. Clone the repository
```bash
git clone https://github.com/MR-Naveen-S/DEVSPRINT_TEAM_INFINITY.git
cd DEVSPRINT_TEAM_INFINITY
```

### 2. Launch Local Server
```bash
# Using Python
python -m http.server 8080
```
Open **[http://localhost:8080/](http://localhost:8080/)** in your browser.

> 💡 For comprehensive step-by-step instructions, troubleshooting, running the Python ML pipeline, and deploying to Vercel, please see **[`SETUP_GUIDE.md`](./SETUP_GUIDE.md)**.

---

## 📂 Project Structure

```text
DEVSPRINT_TEAM_INFINITY/
├── README.md                    # Project overview & quick reference
├── SETUP_GUIDE.md               # Step-by-step local setup, pipeline & deployment guide
├── index.html                   # Root entry point redirecting to web UI
├── vercel.json                  # Production Vercel deployment configuration
│
├── M4/                          # Milestone 4 - Core Engine & Web UI
│   ├── web_ui/                  # Production Interactive Dashboard
│   │   ├── index.html           # 4-in-1 Tabbed Dashboard
│   │   ├── styles.css           # Glassmorphic UI Design System
│   │   └── app.js               # Reactive Analytics & Chart.js Engine
│   ├── detect.py                # Anomaly detection & baseline engine
│   ├── baseline.py              # Statistical baseline computation
│   ├── ml_isolation_forest.py   # Isolation Forest ML detector
│   ├── route_explain.py         # Root cause analysis & Alert routing
│   ├── evaluate.py              # Performance evaluation benchmark
│   └── test_evaluate_unit.py    # Unit & regression tests
│
└── PS-04_campaign_anomaly_alerting/  # Campaign timeseries datasets
```

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).
