=============================================================================
🧬 PROJECT: NEURO-CAPSTONE PIPELINE (Stage 1 & 2)
=============================================================================
DESCRIPTION:
This pipeline integrates Biological Context (Evolutionary AI + Clinical History)
with Structural Physics (AlphaFold + Molecular Mechanics) to predict the
pathogenicity of neurodegenerative mutations.

It addresses the limitations of standard AI (like AlphaMissense) by cross-
referencing results with historical clinical data and preparing for direct
physical simulation.

=============================================================================
🚀 SETUP & INSTALLATION
=============================================================================
1. PRE-REQUISITES:
   - Python 3.8 or higher
   - Internet connection (for API access to EBI, UniProt, OpenTargets)

2. INSTALL DEPENDENCIES:
   Run the following command to install required libraries:
   
   pip install requests numpy biopython

   (Note: 'pysam' is NO LONGER REQUIRED. The pipeline now uses the 
   MyVariant.info REST API for maximum cross-platform compatibility.)

3. DIRECTORY STRUCTURE:
   Ensure your folder looks like this:
   /project_root
      ├── fetch_context.py      # Stage 1: Biology/Context Engine
      ├── fetch_structure.py    # Stage 2: Structure Downloader
      ├── data/
      │   ├── context/          # JSON reports save here
      │   └── structure/        # PDB files save here
      └── INSTRUCTIONS.txt

=============================================================================
🧪 HOW TO RUN: TEST CASES
=============================================================================
Run these commands in your terminal to validate the pipeline.

=============================================================================
✅ ONE-COMMAND PIPELINE (NEW)
=============================================================================
Instead of running structure, context, and analysis separately, you can run:

   python pipeline.py SNCA --variant A53T --analysis-out-dir data/analysis

PIPELINE INPUT METHODS (WHAT USERS CAN PROVIDE)

1) Single target (most common)
   - Input a gene symbol as the first positional argument, plus an optional variant.
   Examples:
     python pipeline.py SNCA --variant A53T
     python pipeline.py MAPT --variant P301L

2) Batch file (many targets)
   - Provide a file via --batch with one target per line.
   - Each line can be whitespace-separated or comma-separated:
      GENE VARIANT
      GENE,VARIANT
      GENE            (variant optional; analysis will be skipped/blocked without it)

3) Variant formats supported
   - 1-letter amino acid code: A53T
   - 3-letter amino acid code: Ala53Thr
   Notes:
   - Context + physics support both formats.
   - Some external databases are strict about reference numbering; a commonly used
    clinical label may differ from RefSeq numbering (e.g., “A4V” vs “Ala5Val”).

4) Optional overrides / controls
   - --id <UniProtAccession>
      Use a specific UniProt ID instead of resolving from the gene symbol.
   - --seq <AASEQUENCE>
      Provide a canonical sequence override for structure folding (used if AlphaFold is unavailable).
   - --chain <ChainID>
      Analyze a specific chain (default: first chain in the PDB).
   - --analysis-out-dir <folder>
      Where physics JSON is written (default: data/analysis).
   - --no-structure / --no-context / --no-analysis
      Skip any stage (useful for debugging or re-running only one step).

This runs (in order):
   1) fetch_structure.get_structure (downloads or generates the PDB)
   2) fetch_context.fetch_all_context (writes data/context/*_context.json)
   3) analyze_structure.calculate_physics_metrics (writes physics JSON)

Batch mode (one target per line):

   # targets.txt
   SNCA A53T
   TTR V50M
   TTR T139M

Run:
   python pipeline.py --batch targets.txt --analysis-out-dir data/analysis

You can also run context-only or analysis-only:
   # context only
   python pipeline.py SNCA --variant A53T --no-structure --no-analysis

   # analysis only (requires a PDB already downloaded)
   python pipeline.py SNCA --variant A53T --no-structure --no-context

Optional flags:
   --no-structure   Skip structure step
   --no-context     Skip context step
   --no-analysis    Skip physics analysis step

-----------------------------------------------------------------------------
TEST CASE 1: THE "BASELINE" (Parkinson's Disease)
-----------------------------------------------------------------------------
Goal: Verify the system correctly identifies a well-known pathogenic mutation.
Command:
   python fetch_context.py SNCA --variant A53T

Expected Output:
   - Identity: Confirmed SNCA (P37840).
   - Mapping: A53T mapped to Genomic Coordinate.
   - Sniper: "HIT: AlphaMissense Score ~0.98 (Pathogenic)".
   - Context: OpenTargets confirms "Parkinson's Disease".
   - Result: SUCCESS.

-----------------------------------------------------------------------------
TEST CASE 2: THE "EFFICIENCY FILTER" (Protective/Benign)
-----------------------------------------------------------------------------
Goal: Verify the system saves resources by flagging benign variants early.
Command:
   python fetch_context.py TTR --variant T139M

   (Note: T139M is the sequence coordinate for the clinical variant T119M).

Expected Output:
   - Sniper: "AlphaMissense Score < 0.2 (Benign)".
   - Filter Warning: "⚠️ [FILTER] Variant appears BENIGN."
   - Result: SUCCESS (Correctly identifies protective variant).

-----------------------------------------------------------------------------
TEST CASE 3: THE "CAPSTONE HIGHLIGHT" (The False Negative)
-----------------------------------------------------------------------------
Goal: Demonstrate why this project is necessary. Show AI failure vs. History.
Command:
   python fetch_context.py TTR --variant V50M

   (Note: V50M is the sequence coordinate for the clinical variant V30M).

Expected Output:
   - Sniper: "AlphaMissense Score ~0.43 (Ambiguous/Benign)".
   - Logic Check: The score is LOW despite this being a known killer.
   - Safety Net: OpenTargets finds 500+ associations with "Amyloidosis".
   - Insight: Proves that evolutionary AI misses late-onset diseases,
     justifying the need for the Physics Engine.

-----------------------------------------------------------------------------
TEST CASE 4: STRUCTURE RETRIEVAL (Preparation for Physics)
-----------------------------------------------------------------------------
Goal: Download the 3D model for the next stage of analysis.
Command:
   python fetch_structure.py TTR

Expected Output:
   - Resolves UniProt ID (P02766).
   - Downloads 'TTR.pdb' from AlphaFold Database.
   - Saves to 'data/structure/TTR.pdb'.

=============================================================================
⚠️ EDGE CASES & TROUBLESHOOTING
=============================================================================

1. THE "NUMBERING TRAP" (Clinical vs. Sequence)
   - Issue: Inputting "V30M" for TTR returns "No Variant Found".
   - Cause: Medical papers exclude the 20-aa signal peptide. Databases don't.
   - Fix: Always use the UniProt Sequence position (Add +20 for TTR).
     Use 'V50M' instead of 'V30M'.

2. NETWORK TIMEOUTS
   - Issue: "Connection Error" or "Sniper Missed".
   - Cause: School Wi-Fi blocking EBI/OpenTargets APIs.
   - Fix: Try a different network or increase `timeout=10` in the script.

3. "VARIANT NOT FOUND"
   - Issue: Sniper returns valid coordinates but no score.
   - Cause: The mutation might be truly novel (never seen before).
   - System Behavior: The pipeline relies on the "Precision Layer" (OpenTargets)
     and will eventually defer to the Physics Engine (Step 3).
mahika,manasa,kirthan and bhargav
=============================================================================