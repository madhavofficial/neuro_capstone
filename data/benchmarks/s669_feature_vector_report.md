# S669 feature-vector check

Each row is the blinded structural feature vector from `benchmark/feature_vector.py`: wild-type exposure, SASA, secondary structure, B-factor, residue-table Δ volume, Δ hydrophobicity, and Δ charge, plus contacts measured on wild-type atoms. Guessed gained contacts are omitted. No mutant structure is built. AlphaMissense is not included, because an S669 row is a PDB chain and an experimental folding ΔΔG, not a clinical variant.

On these crystal and NMR entries the `plddt_confidence` column is the PDB B-factor, not an AlphaFold confidence.

Scored 669 of 669.

Experimental ΔΔG uses the S669 sign: positive is destabilizing.

| Feature | Pearson r | Spearman ρ |
| --- | ---: | ---: |
| sasa | 0.175 | 0.198 |
| plddt_confidence | 0.072 | 0.125 |
| delta_volume | 0.276 | 0.257 |
| delta_hydrophobicity | 0.177 | 0.236 |
| delta_charge | -0.019 | -0.066 |
| salt_bridges_lost | -0.018 | 0.026 |
| disulfides_lost | -0.107 | -0.096 |
| h_bonds_lost_est | 0.016 | 0.022 |
| backbone_strain_flag | -0.010 | -0.025 |
| heuristic_score | -0.235 | -0.253 |

`heuristic_score` is the existing untrained S669 sum of these same features. The other rows are the individual features, unfitted.
