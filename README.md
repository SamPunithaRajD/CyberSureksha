# SecureDocXAI

**Explainable AI-Based Multi-Document Fraud Detection and Financial Risk Scoring Using Vision Transformers and Large Language Models**

SecureDocXAI is an enterprise-grade financial document intelligence platform engineered for banking, underwriting, and forensic audit workflows. It unifies multi-page computer vision, layout understanding, deep forensic anomaly detection, cross-document relationship reasoning, and conversational Explainable AI (XAI).

---

## 🌟 Key Capabilities

### 1. Multi-Document Case Intelligence
- **Holistic Case Management**: Groups applicant files (Payslips, Bank Statements, ID proofs, Invoices) under a single case structure.
- **Cross-Document Consistency Engine**: Compares names, addresses, dates of birth, PAN numbers, Aadhaar numbers, account numbers, IFSC codes, branch names, employer names, and salary credits across multiple documents to identify fraud, identity discrepancies, and phantom employers.

### 2. Vision Transformer (ViT) & Layout Intelligence
- **Layout Understanding**: Modular Vision Transformer pipeline (LayoutLMv3 architecture) extracting visual regions, key-value pairs, tables, and document layout hierarchies.
- **Forensic Tampering Detection**: Error Level Analysis (ELA), copy-move forgery localization, and visual artifact segmentation to expose modified text, spliced pixels, and altered figures.

### 3. Explainable AI & LLM Reasoning Engine
- **Narrative Investigation Reports**: Converts technical anomalies into executive summaries, fraud explanations, and underwriting recommendations.
- **Interactive Investigator Q&A**: Built-in chat interface enabling fraud analysts and branch managers to query documents in plain English (e.g., *"Is the IFSC code valid for this bank?"*, *"Are transaction patterns realistic?"*).

### 4. Deterministic Financial Risk & Trust Scoring
- **Composite Risk Scorer**: Calibrated risk tiers (`Clean`, `Review`, `High Risk`, `Critical`) derived from metadata reliability, mathematical transaction integrity, structural layout signals, and cross-document reconciliation.
- **Trust Profile Scoring**: Independent multi-axis trust scores assessing identity coherence, financial feasibility, and document authenticity.

### 5. Multi-Page OCR & Logical Math Verification
- **Page-Aware OCR**: High-accuracy EasyOCR extraction with page-level bounding box coordinate mapping and OCR error correction.
- **Banking Math Validations**: Validates payslip equations (`Gross = Basic + Allowances + Bonus`, `Net = Gross - Deductions`) and running bank statement balances across all document pages.

### 6. Role-Based Access Control (RBAC) & Compliance
- **Segregated Enterprise Workflows**: Dedicated interfaces and action permissions for 5 institutional roles:
  - **Underwriting Officer**: Application upload and submission tracking.
  - **Fraud Analyst**: Diagnostic investigation queue, anomaly inspection, and manager escalation.
  - **Branch Manager**: Escalated case review, decision overrides, and branch fraud metrics.
  - **Compliance Auditor**: Read-only immutable transaction ledger and regulatory exports.
  - **System Admin**: Operator provisioning, threshold tuning, and platform monitoring.
- **Immutable Audit Trails**: Standardized JSON audit logging capturing every action, justification, timestamp, and user identity.

---

## 🏗️ System Architecture

```
                               ┌────────────────────────────────┐
                               │   SecureDocXAI React Frontend   │
                               │    (Vite + Tailwind + Recharts) │
                               └────────────────┬───────────────┘
                                                │ REST / JSON
                               ┌────────────────▼────────────────┐
                               │       FastAPI Backend API       │
                               │   (RBAC, JWT, Case Controller)  │
                               └───────┬────────────────┬────────┘
                                       │                │
            ┌──────────────────────────┴────┐      ┌────┴───────────────────────────┐
            │   Multi-Page Vision Engine    │      │  Multi-Document Reasoning Core │
            ├───────────────────────────────┤      ├────────────────────────────────┤
            │ • EasyOCR Page Extractor      │      │ • Relationship Cross-Validator │
            │ • OCR Error Correction Layer  │      │ • Correlation Graph Builder    │
            │ • ViT LayoutLMv3 Pipeline     │      │ • LLM Forensic Explainer (XAI) │
            │ • ELA & Tampering Forensics   │      │ • Composite Risk & Trust Scorer│
            └──────────────┬────────────────┘      └────────────────┬───────────────┘
                           │                                        │
                           └───────────────────┬────────────────────┘
                                               │
                                 ┌─────────────▼────────────┐
                                 │      MongoDB Database    │
                                 │ (Cases, Docs, Analyses,  │
                                 │  Audit Logs, Notifs)     │
                                 └──────────────────────────┘
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- MongoDB (running on `localhost:27017` or via Docker)

---

### Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch the FastAPI application:**
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   The backend API will be available at [http://localhost:8000](http://localhost:8000) with interactive Swagger documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### Frontend Setup

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node packages:**
   ```bash
   npm install
   ```

3. **Start the development server:**
   ```bash
   npm run dev
   ```
   The frontend UI will be available at [http://localhost:5173](http://localhost:5173).

---

### Docker Deployment

To spin up the entire application stack including MongoDB:
```bash
docker-compose up --build
```

---

## 👥 Default Demo Accounts

Default role accounts seeded automatically on initial launch:

| Role | Email | Password |
|---|---|---|
| **Underwriting Officer** | `underwriter@bank.com` | `Password123` |
| **Fraud Analyst** | `analyst@bank.com` | `Password123` |
| **Branch Manager** | `manager@bank.com` | `Password123` |
| **Compliance Auditor** | `auditor@bank.com` | `Password123` |
| **System Admin** | `admin@bank.com` | `Password123` |

*(One-click quick login is also available directly on the login interface.)*

---

## 🧪 Verification & Testing

To run the end-to-end integration and notification test suites:

```bash
cd backend
python test_cases_flow.py
python test_notifications.py
```

---

## 📄 License
This project is licensed under the Apache 2.0 License.
