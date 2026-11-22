# UniProt `humsavar.txt` 100-Variant 3-Source Audit & Benchmark Summary

**Independent Verification Pillars:** (1) UniProt `humsavar.txt`, (2) NCBI ClinVar & ClinGen Allele Registry, and (3) Primary Peer-Reviewed Literature via Europe PMC & PubMed (through 2026).

- **Audited Dataset:** `data/benchmarks/humsavar_neuro_100_audited.csv` (100/100 variants completed: 50 Pathogenic + 50 Benign)
- **Pathogenic Batch (50/50):** `43 / 50` (**86.0%**) agreement (`0 / 50` false-benign errors; `10 / 10` confirmed VUS/Conflicting/Uncataloged caught as `vus`). Reverted `LRRK2 R1067Q` (`PMID:39988587`), `FUS R244C` (`PMID:39495179`, `PMID:41224766`), and `SOD1 V8E` (`PMID:32144830`, `PMID:29431095`) back to `pathogenic` based on primary literature.
- **Benign Batch (50/50):** `45 / 50` (**90.0%**) agreement (`13/17` confirmed Benign/LB, `3/4` mislabeled Pathogenic caught, `29/29` Conflicting/VUS/Uncataloged called `vus`; `0` false-pathogenic errors on truly benign variants). Reclassified `TTR H110N` (`H90N`) to `vus` due to conflicting 2024 hATTR-PN case reports (`PMID:38928520`) vs. Invitae/Labcorp Benign/VUS.
- **Combined 3-Source Audited (100/100):** **`88 / 100` (88.0%)** | Paper Citation Validity: **`109 / 111` (98.2%)** | Clinical Field Validity: **`90 / 126` (71.4%)** | JSON Schema Validity: **`100%`**.

## Primary Literature Sources Used for Contested-Variant Verification

- `LRRK2 R1067Q`: https://europepmc.org/article/MED/39988587 | https://pubmed.ncbi.nlm.nih.gov/41505438/
- `FUS R244C`: https://europepmc.org/article/MED/43011570 | https://europepmc.org/article/MED/41224766 | https://pubmed.ncbi.nlm.nih.gov/39495179/
- `SOD1 V8E/V7E`: https://europepmc.org/article/MED/32144830 | https://europepmc.org/article/MED/29431095
- `TTR H110N/H90N`: https://europepmc.org/article/MED/38928520 | https://pubmed.ncbi.nlm.nih.gov/38523305/
- `MAPT S669L/S352L`: https://pubmed.ncbi.nlm.nih.gov/14595660/ | https://europepmc.org/article/MED/38054595 | https://europepmc.org/article/MED/40294272

## Full 50-Variant Benign (`LB/B`) Audit Table

| Gene | Variant | Raw `humsavar` | Audited Consensus | Pipeline Pred | Source / ClinVar & Literature Status |
|---|---|---|---|---|---|
| `TTR` | `G26S` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `MAPT` | `D285N` | `benign` | **`benign`** | `vus` | Confirmed Benign (ClinVar) |
| `APP` | `E665D` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar 18095) |
| `PSEN1` | `E318G` | `benign` | **`vus`** | `vus` | AD Risk Modifier / Alzforum (ClinVar 98094) |
| `PSEN2` | `R62H` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `TARDBP` | `A90V` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `LRRK2` | `R50H` | `benign` | **`benign`** | `benign` | Confirmed Benign (ClinVar) |
| `GBA1` | `E365K` | `benign` | **`vus`** | `vus` | PD Risk Modifier / Conflicting (ClinVar 199044) |
| `GRN` | `G515A` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `FUS` | `H517Q` | `benign` | **`pathogenic`** | `pathogenic` | Pathogenic (ClinVar 16221; ALS6 NLS) |
| `PRKN` | `Q100H` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
| `PINK1` | `P305L` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PARK7` | `R98Q` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `TTR` | `D94H` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `MAPT` | `V289A` | `benign` | **`benign`** | `vus` | Confirmed Benign (ClinVar) |
| `APP` | `E501K` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PSEN1` | `F205L` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `LRRK2` | `L119P` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `GBA1` | `T408M` | `benign` | **`vus`** | `vus` | PD Risk Modifier / Conflicting (ClinVar 93447) |
| `GRN` | `R19W` | `benign` | **`benign`** | `benign` | Confirmed Benign (ClinVar) |
| `FUS` | `M254V` | `benign` | **`pathogenic`** | `vus` | Likely pathogenic (ClinVar 427141) |
| `PRKN` | `S167N` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `PINK1` | `A340T` | `benign` | **`benign`** | `benign` | Confirmed Benign (ClinVar) |
| `PARK7` | `G150S` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
| `TTR` | `H110N` | `benign` | **`vus`** | `vus` | Conflicting (hATTR-PN PMID:38928520 vs. Invitae/Labcorp Benign/VUS) |
| `MAPT` | `Y441H` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `LRRK2` | `N551K` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `GBA1` | `L509P` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `GRN` | `R55W` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PRKN` | `R271S` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PINK1` | `N521T` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `PARK7` | `A171S` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
| `TTR` | `G121S` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
| `MAPT` | `S447P` | `benign` | **`benign`** | `benign` | Confirmed Benign (ClinVar) |
| `LRRK2` | `I723V` | `benign` | **`benign`** | `benign` | Confirmed Benign (ClinVar) |
| `GBA1` | `M92T` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `GRN` | `A69T` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PRKN` | `R334C` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `PINK1` | `L148W` | `benign` | **`benign`** | `vus` | Confirmed Likely benign (ClinVar) |
| `TTR` | `P122R` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `MAPT` | `R723W` | `benign` | **`pathogenic`** | `pathogenic` | Pathogenic (ClinVar 14247; Alzforum) |
| `LRRK2` | `D944Y` | `benign` | **`vus`** | `vus` | not provided (ClinVar) |
| `GBA1` | `S310G` | `benign` | **`vus`** | `vus` | Conflicting classifications of pathogenicity (ClinVar) |
| `GRN` | `S120Y` | `benign` | **`benign`** | `vus` | Confirmed Benign/Likely benign (ClinVar) |
| `PRKN` | `A339S` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `PINK1` | `P196S` | `benign` | **`vus`** | `vus` | Uncataloged in ClinVar (ClinVar) |
| `TTR` | `R124C` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
| `MAPT` | `S669L` | `benign` | **`pathogenic`** | `pathogenic` | Recessive Pathogenic (ClinVar 14267; PMID:14595660; Alzforum VUS due to recessive inheritance) |
| `LRRK2` | `P1262A` | `benign` | **`benign`** | `benign` | Confirmed Benign/Likely benign (ClinVar) |
| `GBA1` | `R368H` | `benign` | **`vus`** | `vus` | Uncertain significance (ClinVar) |
