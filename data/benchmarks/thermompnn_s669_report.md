# ThermoMPNN on S669

ThermoMPNN reads the wild-type PDB and the amino-acid change. No mutant coordinate file is built. NMR entries use the first model only. Weights are `thermoMPNN_default.pt` from Kuhlman-Lab/ThermoMPNN.

Scored 669 of 669. Skipped: none.

The S669 table in this repo uses positive ΔΔG for a destabilizing mutation. ThermoMPNN's own S669 loader multiplies that column by −1 before scoring, so both correlations are reported.

Pearson vs experimental ΔΔG = -0.424
Spearman vs experimental ΔΔG = -0.478

Pearson vs −ΔΔG (ThermoMPNN S669 convention) = 0.424
Spearman vs −ΔΔG (ThermoMPNN S669 convention) = 0.478

Published ThermoMPNN Pearson on S669 is 0.43 (Dieckhaus et al., PNAS 2024). FoldX is 0.22 and Rosetta is 0.39 on the direct set (Pancotti et al., 2022).
