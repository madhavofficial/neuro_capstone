import sys
import os
import json
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

# Dynamically add the parent directory (project root) to sys.path
# so we can import the existing scientific pipeline without modifying it.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from pipeline import run_pipeline
except ImportError as e:
    raise ImportError(f"Could not import 'pipeline' from project root ({PROJECT_ROOT}). Ensure pipeline.py exists.") from e

app = FastAPI(
    title="NeuroCapstone Local API",
    description="Local API adapter for the Protein Mutation Analysis pipeline.",
    version="1.0.0",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    gene: str = Field(..., min_length=1, description="Gene symbol (e.g., SNCA)")
    variant: str = Field(..., min_length=1, description="Variant specification (e.g., A53T)")

class AnalyzeResponse(BaseModel):
    gene: str
    variant: str
    context_data: Optional[Dict[str, Any]] = None
    physics_data: Optional[Dict[str, Any]] = None
    pdb_content: Optional[str] = None
    warnings: Optional[Dict[str, str]] = None

@app.get("/health")
def health_check():
    return {"status": "ok", "backend": "active", "project_root": PROJECT_ROOT}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_variant(payload: AnalyzeRequest):
    gene = payload.gene.strip()
    variant = payload.variant.strip()

    try:
        pdb_path, context_data, physics_json_path = await run_in_threadpool(
            run_pipeline, gene, variant
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scientific pipeline execution failed: {str(exc)}",
        )

    physics_data = None
    pdb_content = None
    warnings = {}

    if physics_json_path:
        if os.path.isfile(physics_json_path):
            try:
                with open(physics_json_path, "r", encoding="utf-8") as f:
                    physics_data = json.load(f)
            except Exception as e:
                warnings["physics_error"] = f"Failed to parse physics JSON: {str(e)}"
        else:
            warnings["physics_missing"] = f"Physics JSON file missing at: {physics_json_path}"
    else:
        warnings["physics_missing"] = "Pipeline returned no physics JSON path."

    if pdb_path:
        if os.path.isfile(pdb_path):
            try:
                with open(pdb_path, "r", encoding="utf-8") as f:
                    pdb_content = f.read()
            except Exception as e:
                warnings["pdb_error"] = f"Failed to read PDB file: {str(e)}"
        else:
            warnings["pdb_missing"] = f"PDB file missing at: {pdb_path}"
    else:
        warnings["pdb_missing"] = "Pipeline returned no PDB path."

    return AnalyzeResponse(
        gene=gene,
        variant=variant,
        context_data=context_data,
        physics_data=physics_data,
        pdb_content=pdb_content,
        warnings=warnings if warnings else None,
    )

