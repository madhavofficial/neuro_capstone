# NeuroCapstone — UI Setup & Run Instructions

## 1. Project structure

The FastAPI backend is in the project root:

`capstone/`

The React/Vite frontend is in:

`capstone/User Interface/frontend/`

**Important:** Start the backend from the project root, not from `User Interface/frontend`.

---

## 2. Python environment

From the project root:

```powershell
cd "C:\Users\Manasa Ranganath\Desktop\LAB\capstone"
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Verified working versions:

```text
Python: 3.13
torch: 2.13.0+cpu
sentence-transformers: 5.1.2
transformers: 4.57.1
```

---

## 3. Install Python dependencies

Install the base dependencies:

```powershell
python -m pip install requests numpy biopython beautifulsoup4
```

Install the vector/RAG dependencies:

```powershell
python -m pip install faiss-cpu torch
python -m pip install "transformers==4.57.1" "sentence-transformers==5.1.2"
```

### Verify installation

```powershell
python -c "import torch, sentence_transformers, transformers; print('torch:', torch.__version__); print('sentence-transformers:', sentence_transformers.__version__); print('transformers:', transformers.__version__)"
```

Expected:

```text
torch: 2.13.0+cpu
sentence-transformers: 5.1.2
transformers: 4.57.1
```

Verify FAISS:

```powershell
python -c "import faiss; print('FAISS OK')"
```

Expected:

```text
FAISS OK
```

---

## 4. First-time biomedical model download

The literature retrieval stage uses:

```text
pritamdeka/S-PubMedBert-MS-MARCO
```

Test it with:

```powershell
python -c "from sentence_transformers import SentenceTransformer; print('IMPORT OK'); model=SentenceTransformer('pritamdeka/S-PubMedBert-MS-MARCO', device='cpu'); print('MODEL OK')"
```

Expected:

```text
IMPORT OK
MODEL OK
```

The first execution downloads the model from Hugging Face. This requires internet access and may take some time because the model is large.

A Windows symlink warning from Hugging Face can be ignored; the model still downloads and works.

---

# 5. Start the backend

Open **Terminal 1**.

From the project root:

```powershell
cd "C:\Users\Manasa Ranganath\Desktop\LAB\capstone"
.\.venv\Scripts\Activate.ps1
```

Start FastAPI:

```powershell
uvicorn api:app --host 127.0.0.1 --port 8001 --reload
```

Expected:

```text
Uvicorn running on http://127.0.0.1:8001
```

Keep this terminal running.

### Backend health check

Open:

`http://127.0.0.1:8001/health`

Expected:

```json
{
  "status": "ok"
}
```

---

# 6. Start the frontend

Open **Terminal 2**.

```powershell
cd "C:\Users\Manasa Ranganath\Desktop\LAB\capstone\User Interface\frontend"
```

Install frontend packages:

```powershell
npm install
```

Verify the production build:

```powershell
npm run build
```

Then start the development server:

```powershell
npm run dev
```

Open:

`http://localhost:5173`

The frontend communicates with the backend at:

`http://127.0.0.1:8001`

---

# 7. Complete startup — quick version

### Terminal 1

```powershell
cd "C:\Users\Manasa Ranganath\Desktop\LAB\capstone"
.\.venv\Scripts\Activate.ps1
uvicorn api:app --host 127.0.0.1 --port 8001 --reload
```

### Terminal 2

```powershell
cd "C:\Users\Manasa Ranganath\Desktop\LAB\capstone\User Interface\frontend"
npm install
npm run build
npm run dev
```

Then open:

`http://localhost:5173`

---

# 8. Backend API

The backend is implemented in:

`api.py`

Available endpoints:

```text
GET  /health
POST /analyze
```

The request model is:

```json
{
  "gene": "SNCA",
  "variant": "A53T"
}
```

The `/analyze` endpoint calls the existing scientific pipeline:

```python
run_pipeline(gene, variant)
```

The backend returns the real pipeline outputs rather than generating placeholder scientific data.

---

# 9. API test from PowerShell

With the backend running:

```powershell
$body = @{
    gene = "SNCA"
    variant = "A53T"
} | ConvertTo-Json
```

Send the request:

```powershell
$r = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/analyze" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

Check status:

```powershell
$r.status
```

Check literature evidence:

```powershell
$r.evidence
```

Check confidence matrix:

```powershell
$r.confidence_matrix
```

Check warnings:

```powershell
$r.warnings
```

---

# 10. Verified SNCA A53T test

The complete API request was successfully tested for:

```text
Gene: SNCA
Variant: A53T
```

Final status:

```text
SUCCESS
```

Confidence matrix:

```text
physics_engine:         HEURISTIC
literature_rag:         SUCCESS
clinical_context:       HIGH
clinical_context_scope: EXACT_VARIANT
physics_evidence_scope: SITE_PROPERTY_HEURISTIC
```

Two literature evidence items were returned.

### PMID 40779487

Title:

`Expression of human A53T alpha-synuclein without endogenous rat alpha-synuclein fails to elicit Parkinson's disease-related phenotypes in a novel humanized rat model.`

Cross-encoder score:

`0.9756529331207275`

### PMID 41002401

Title:

`Modeling Synucleinopathy Using hESC-Derived Cerebral Organoids.`

Cross-encoder score:

`0.746527910232544`

Warnings:

```text
None
```

This confirms that the literature/RAG retrieval stage, FAISS retrieval, biomedical embedding model, cross-encoder reranking, and payload assembly are functioning for this test case.

---

# 11. Scientific pipeline flow

The backend connects the UI to the existing pipeline.

The overall flow is:

```text
User enters Gene + Variant
          |
          v
      React UI
          |
          v
    FastAPI /analyze
          |
          v
     run_pipeline()
          |
          +--------------------+
          |                    |
          v                    v
  Structure Retrieval     Clinical Context
          |                    |
          v                    |
    AlphaFold PDB              |
          |                    |
          v                    |
 Structural Physics            |
    Analysis                   |
          |                    |
          +---------+----------+
                    |
                    v
             NLP Query Formation
                    |
                    v
              Literature RAG
                    |
          +---------+---------+
          |                   |
          v                   v
    Bi-encoder            FAISS
    retrieval             search
          |                   |
          +---------+---------+
                    |
                    v
             Cross-encoder
                reranking
                    |
                    v
             Evidence assembly
                    |
                    v
             Confidence Matrix
                    |
                    v
              Final Payload
                    |
                    v
                FastAPI
                    |
                    v
                 React UI
```

---

# 12. Important RAG configuration

The vector engine is implemented in:

`vector_engine.py`

It uses:

```text
Bi-encoder:
pritamdeka/S-PubMedBert-MS-MARCO

Cross-encoder:
cross-encoder/ms-marco-TinyBERT-L-2-v2
```

Retrieval configuration:

```text
TOP_K_RETRIEVAL = 100
TOP_K_FINAL     = 5
```

The pipeline therefore retrieves a wider candidate pool first and then keeps the strongest reranked results.

The payload assembler applies:

```text
CONFIDENCE_THRESHOLD = 0.7
MAX_CHUNKS_PER_PMID  = 2
```

---

# 13. Confidence matrix

The payload contains three per-engine states:

```text
physics_engine
literature_rag
clinical_context
```

Possible values include:

### Physics

```text
HEURISTIC
ERROR
```

### Literature RAG

```text
SUCCESS
NULL_RESULTS
TIMEOUT_ERROR
```

### Clinical context

```text
HIGH
PARTIAL
UNAVAILABLE
```

The final global status is derived from these signals rather than being manually entered by the UI.

Possible global states include:

```text
SUCCESS
LOW_CONFIDENCE
STRUCTURAL_DISCOVERY_VUS
PREDICTED_PATHOGENIC_VUS
```

---

# 14. Troubleshooting

## `No module named 'faiss'`

Run:

```powershell
python -m pip install faiss-cpu
```

Verify:

```powershell
python -c "import faiss; print('FAISS OK')"
```

---

## `No module named 'torch'`

Run:

```powershell
python -m pip install torch
```

---

## `No module named 'sentence_transformers'`

Run:

```powershell
python -m pip install "sentence-transformers==5.1.2"
```

---

## `No module named 'bs4'`

Run:

```powershell
python -m pip install beautifulsoup4
```

---

## Transformers version mismatch

Use the verified version:

```powershell
python -m pip install "transformers==4.57.1"
```

and verify:

```powershell
python -c "import transformers; print(transformers.__version__)"
```

Expected:

```text
4.57.1
```

---

## Uvicorn says `Could not import module "api"`

Make sure the terminal is in:

```text
C:\Users\Manasa Ranganath\Desktop\LAB\capstone
```

Then run:

```powershell
uvicorn api:app --host 127.0.0.1 --port 8001 --reload
```

Do **not** start `uvicorn api:app` from:

```text
User Interface/frontend
```

---

## Literature retrieval warning

If the API returns:

```text
literature_rag: NULL_RESULTS
```

first inspect:

```powershell
$r.warnings
```

If the warning reports a missing Python package, install that dependency.

If the literature corpus itself is empty, check:

```text
data/literature/
```

and rerun the pipeline when network access is available.

---

# 15. Important scientific UI rule

The frontend is a presentation layer.

It must display the outputs produced by the backend/scientific pipeline and must not fabricate:

- Literature evidence
- PMID values
- Clinical classifications
- Physics measurements
- Confidence scores
- Pathogenicity predictions

The scientific result shown in the UI should always correspond to the API response.

---

# 16. Current verified state

At the time this README was updated:

```text
FAISS                         OK
PyTorch                       OK
Sentence Transformers         5.1.2
Transformers                  4.57.1
PubMedBERT model              downloaded successfully
Biomedical model import       OK
SNCA A53T API test            SUCCESS
Literature RAG                SUCCESS
Clinical context              HIGH
Physics engine                HEURISTIC
API warnings                  None
```

The verified SNCA A53T request demonstrates that the complete backend retrieval path is working.
