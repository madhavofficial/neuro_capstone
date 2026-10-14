# S669 structural-heuristic check

Each variant is a virtual amino-acid substitution on one wild-type PDB. Volume, hydropathy, and charge come from residue tables. SASA, DSSP, hydrogen bonds, salt bridges, and disulfides are read from that same wild-type model. NMR entries contribute their first model only. No mutant coordinate file is built.

## Set

The rows are the S669 direct set from Pancotti et al., Briefings in Bioinformatics 23:bbab555 (2022): 669 variants across 94 PDB chains. The figure of about 1,338 variants is this set plus the reverse mutation of each row. The reverse coordinates in that paper are Robetta models of the mutant. This run scores the direct rows only, on the wild-type structure.

Experimental ΔΔG uses the S669 sign: positive is destabilizing. The heuristic score uses the same direction.

## Score

The score is an untrained sum. Burial is 1.0 when SASA < 10 Å², 0.5 when SASA < 40 Å², and 0.2 otherwise. Helix and sheet sites keep the full packing terms; other DSSP labels halve them. Volume contributes `burial * |ΔV| / 60`. Hydropathy contributes `burial * (−ΔH) / 4.5`. Charge contributes `burial * (|q_mut| − |q_wt|)`. Lost hydrogen bonds, lost salt bridges, and lost disulfides each contribute 1 per contact measured on the wild-type atoms. Guessed gained contacts are omitted. A backbone-strain flag contributes 1. These scales were not fit on S669.

## Result

Scored 669 of 669. Skipped: none.

Pearson r = -0.235
Spearman ρ = -0.253

Published simple predictors on the S669 direct set, Pearson r: FoldX 0.22, DDGun 0.41, DDGun3D 0.43.

## Decision

Pearson -0.235 is below 0.22, the FoldX result on this same direct set and the low end of the published simple predictors. In the modules this task owns, the calculation is named a structural heuristic. S669 is a monomer-stability check, not an aggregation test.

## What a weak correlation leaves in place

The site metrics stay. They still describe the wild-type substitution, and the literature query still uses them for aggregation and misfolding. TTR disease is tetramer dissociation. S669 measures monomer folding stability. This check does not replace the heuristics with ThermoMPNN.
