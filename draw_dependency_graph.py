"""
Neuro-Capstone File Dependency Graph Visualizer
Generates a publication/presentation-grade diagram of inter-file module dependencies.
Run: python draw_dependency_graph.py
Saves: data/file_dependency_graph.png and data/file_dependency_graph.svg
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os

# ── Palette ──────────────────────────────────────────────────────────────────
BG        = "#F8FAFC"    # ultra-clean background
PANEL_BG  = "#FFFFFF"
ENTRY     = "#1E40AF"    # royal blue
CORE_SCI  = "#047857"    # emerald green (biology/physics)
TRANSFORM = "#B45309"    # amber (nlp)
ORCH      = "#6D28D9"    # purple (orchestration)
RAG       = "#0E7490"    # cyan/teal (vector engine)
PAYLOAD   = "#BE123C"    # rose/crimson (payload assembly)
LLM       = "#9A3412"    # rust/orange (reasoning engine)
API_UI    = "#334155"    # slate dark (api/ui)
ARROW_COL = "#64748B"    # slate arrow
TEXT_MAIN = "#0F172A"
TEXT_MUTED= "#475569"

fig = plt.figure(figsize=(18, 12), facecolor=BG)
ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
ax.set_facecolor(PANEL_BG)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

# ── Helpers ──────────────────────────────────────────────────────────────────
def node(x, y, w, h, title, subtitle, color, zorder=3):
    from matplotlib.patches import FancyBboxPatch
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0,rounding_size=0.012",
        linewidth=1.6, edgecolor=color,
        facecolor=color + "12",
        zorder=zorder,
    )
    ax.add_patch(box)
    ax.text(x, y + 0.012, title, color=color, fontsize=8.5, fontweight="bold",
            ha="center", va="center", zorder=zorder+1, fontfamily="DejaVu Sans")
    ax.text(x, y - 0.014, subtitle, color=TEXT_MUTED, fontsize=6.8,
            ha="center", va="center", zorder=zorder+1, fontfamily="DejaVu Sans")

def edge(x0, y0, x1, y1, color=ARROW_COL, label_txt="", rad=0.0, lw=1.3, style="->"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(
                    arrowstyle=f"{style}, head_width=0.22, head_length=0.011",
                    color=color, lw=lw,
                    connectionstyle=f"arc3,rad={rad}"),
                zorder=2)
    if label_txt:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx, my + 0.010, label_txt, color=color, fontsize=5.8,
                ha="center", va="center", zorder=4,
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#FFFFFF", edgecolor=color, lw=0.6, alpha=0.9))

# ── Title ────────────────────────────────────────────────────────────────────
ax.text(0.5, 0.970, "Neuro-Capstone — Codebase File Dependency Graph",
        color=TEXT_MAIN, fontsize=14, fontweight="bold", ha="center", va="center")
ax.text(0.5, 0.948, "Static Import & Execution Call Graph Across System Modules",
        color=TEXT_MUTED, fontsize=8.5, ha="center", va="center")

# ── Node Coordinates ─────────────────────────────────────────────────────────
W_STD = 0.19
H_STD = 0.062

# ── Node Coordinates (3 Clean Columns) ───────────────────────────────────────
W_STD = 0.22
H_STD = 0.070

# Column 1: Client Interfaces & Entry Points (x = 0.15)
node(0.15, 0.84, W_STD, H_STD, "pipeline.py", "Master Scientific CLI\n(Coordinates All 9 Stages)", ENTRY)
node(0.15, 0.60, W_STD, H_STD, "app.py", "CLI Runner for Dual-RAG\n(Query evidence runner)", ENTRY)
node(0.15, 0.36, W_STD, H_STD, "User Interface / api.py", "FastAPI REST Server\n(Endpoints: /analyze, /reasoning)", API_UI)
node(0.15, 0.12, W_STD, H_STD, "benchmark / full_runner.py", "Batch Validation Runner\n(Benchmarking ClinVar Gold Set)", API_UI)

# Column 2: Core Domain Engines (x = 0.50)
node(0.50, 0.88, W_STD, H_STD, "fetch_structure.py", "AlphaFold DB PDB Downloader\nUniProt Accession Resolver", CORE_SCI)
node(0.50, 0.72, W_STD, H_STD, "fetch_context.py", "Clinical Genetics Consensus\nClinVar · dbSNP · OpenTargets", CORE_SCI)
node(0.50, 0.56, W_STD, H_STD, "analyze_structure.py", "BioPython Physics Engine\nΔV · SASA · DSSP · Backbone Strain", CORE_SCI)
node(0.50, 0.40, W_STD, H_STD, "nlp_formation.py", "Hybrid Query Builder\nTranslates ΔV/ΔH to Query Concepts", TRANSFORM)
node(0.50, 0.24, W_STD, H_STD, "vector_engine.py", "Two-Stage Neural Retrieval\nS-PubMedBERT + TinyBERT Reranker", RAG)

# Column 3: Orchestration, Assembly & LLM Synthesis (x = 0.84)
node(0.84, 0.78, W_STD, H_STD, "orchestration.py", "Master Evidence Controller\nStrict 4-Phase Sequencer", ORCH)
node(0.84, 0.52, W_STD, H_STD, "assemble_payload.py", "Confidence Matrix & Gating\nThreshold ≥ 0.70 · Dedup max 2/PMID", PAYLOAD)
node(0.84, 0.26, W_STD, 0.085, "reasoning_engine.py", "Multi-Modal LLM Engine\n• Biophysics + Clinical + Dual-RAG\n• Server-Side PMID Validation", LLM)

# ── Edges / Dependencies ─────────────────────────────────────────────────────

# 1. pipeline.py -> Core Data & Transform
edge(0.15 + W_STD/2, 0.85, 0.50 - W_STD/2, 0.88, color=ENTRY, label_txt="calls get_structure()")
edge(0.15 + W_STD/2, 0.84, 0.50 - W_STD/2, 0.73, color=ENTRY, label_txt="calls fetch_all_context()", rad=-0.05)
edge(0.15 + W_STD/2, 0.83, 0.50 - W_STD/2, 0.58, color=ENTRY, label_txt="calls calculate_physics_metrics()", rad=-0.10)
edge(0.15 + W_STD/2, 0.82, 0.50 - W_STD/2, 0.42, color=ENTRY, label_txt="calls run_nlp_formation()", rad=-0.16)

# 2. pipeline.py -> orchestration.py
edge(0.15 + W_STD/2, 0.86, 0.84 - W_STD/2, 0.80, color=ENTRY, label_txt="calls phase_3 & phase_4", rad=0.10)

# 3. app.py -> orchestration.py
edge(0.15 + W_STD/2, 0.60, 0.84 - W_STD/2, 0.76, color=ENTRY, label_txt="calls run_full_pipeline()", rad=0.08)

# 4. User Interface / api.py calls
edge(0.15 + W_STD/2, 0.38, 0.50 - W_STD/2, 0.55, color=API_UI, label_txt="calls run_pipeline()", rad=0.15)
edge(0.15 + W_STD/2, 0.36, 0.84 - W_STD/2, 0.74, color=API_UI, label_txt="calls run_full_pipeline()", rad=0.20)
edge(0.15 + W_STD/2, 0.34, 0.84 - W_STD/2, 0.28, color=API_UI, label_txt="calls generate_reasoning()", rad=-0.05)

# 5. Core Data Interconnections
# analyze_structure -> nlp_formation
edge(0.50, 0.56 - H_STD/2, 0.50, 0.40 + H_STD/2, color=CORE_SCI, label_txt="passes physics deltas")

# orchestration.py connections
edge(0.84 - W_STD/2, 0.80, 0.15 + W_STD/2, 0.82, color=ORCH, label_txt="imports fetch_literature_json()", rad=0.18)
edge(0.84 - W_STD/2, 0.77, 0.50 + W_STD/2, 0.41, color=ORCH, label_txt="imports create_nlp_query()", rad=-0.08)
edge(0.84 - W_STD/2, 0.75, 0.50 + W_STD/2, 0.25, color=ORCH, label_txt="calls vector_engine.retrieve_evidence()", rad=-0.12)
edge(0.84, 0.78 - H_STD/2, 0.84, 0.52 + H_STD/2, color=ORCH, label_txt="calls assemble_payload.run()")

# vector_engine -> assemble_payload
edge(0.50 + W_STD/2, 0.24, 0.84 - W_STD/2, 0.50, color=RAG, label_txt="passes Top-K ranked chunks", rad=0.08)

# nlp_formation -> assemble_payload (VUS directive import)
edge(0.50 + W_STD/2, 0.39, 0.84 - W_STD/2, 0.53, color=TRANSFORM, label_txt="imports VUS directive", rad=0.05)

# 6. Three Multimodal Streams into reasoning_engine.py
# Stream ①: assemble_payload -> reasoning_engine
edge(0.84, 0.52 - H_STD/2, 0.84, 0.26 + 0.085/2, color=PAYLOAD, label_txt="① Dual-RAG Literature Evidence", lw=2.0)

# Stream ②: fetch_context -> reasoning_engine
edge(0.50 + W_STD/2, 0.71, 0.84, 0.26 + 0.085/2, color=CORE_SCI, label_txt="② Clinical Benchmark Context", rad=0.32, lw=1.6)

# Stream ③: analyze_structure -> reasoning_engine
edge(0.50 + W_STD/2, 0.56, 0.84 - W_STD/2, 0.25, color=CORE_SCI, label_txt="③ Structural Biophysics Metrics", rad=0.14, lw=1.6)

# ── Legend ───────────────────────────────────────────────────────────────────
legend_items = [
    (ENTRY,     "Entry / CLI"),
    (CORE_SCI,  "Bioinformatics & Physics"),
    (TRANSFORM, "NLP Query Transformation"),
    (ORCH,      "Phase Orchestration"),
    (RAG,       "Vector Retrieval (Dual-RAG)"),
    (PAYLOAD,   "Payload Assembly & Gating"),
    (LLM,       "LLM Synthesis / Reasoning"),
    (API_UI,    "API Backend & Benchmark"),
]
patches = [mpatches.Patch(facecolor=c + "18", edgecolor=c, label=l) for c, l in legend_items]
ax.legend(handles=patches, loc="lower center", fontsize=7.5,
          facecolor="#FFFFFF", edgecolor="#CBD5E1",
          labelcolor=TEXT_MAIN, framealpha=1.0,
          ncol=4, handlelength=1.4, bbox_to_anchor=(0.5, 0.02))

# ── Save ─────────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
out_png = "data/file_dependency_graph.png"
fig.savefig(out_png, dpi=200, bbox_inches="tight", facecolor=BG)
print(f"[OK] Saved PNG  → {out_png}")

out_svg = "data/file_dependency_graph.svg"
fig.savefig(out_svg, format="svg", bbox_inches="tight", facecolor=BG)
print(f"[OK] Saved SVG  → {out_svg}")
plt.close()
