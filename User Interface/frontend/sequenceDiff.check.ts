import assert from "node:assert/strict";
import { buildSequenceDiff } from "./src/lib/sequenceDiff.ts";

function atom(
  record: "ATOM" | "HETATM",
  name: string,
  resname: string,
  chain: string,
  resseq: number,
  icode = " ",
): string {
  const serial = "1".padStart(5, " ");
  const atomName = name.padStart(3, " ").padEnd(4, " ");
  const residue = resname.padEnd(3, " ").slice(0, 3);
  const sequence = String(resseq).padStart(4, " ");
  const insertion = (icode || " ").slice(0, 1);
  return `${record.padEnd(6, " ")}${serial} ${atomName} ${residue} ${chain}${sequence}${insertion}   0.000   0.000   0.000  1.00  0.00           C`;
}

function pdb(lines: string[]): string {
  return lines.join("\n");
}

const matching = buildSequenceDiff(
  pdb([
    atom("ATOM", "N", "ALA", "A", 53),
    atom("ATOM", "CA", "ALA", "A", 53),
    atom("ATOM", "CA", "ALA", "A", 53),
    atom("ATOM", "CA", "VAL", "A", 54),
  ]),
  "A53T",
);
assert.equal(matching.status, "diff");
assert.equal(matching.chainId, "A");
assert.equal(matching.changeIndex, 0);
assert.equal(matching.wildType.map((residue) => residue.letter).join(""), "AV");
assert.equal(matching.variant.map((residue) => residue.letter).join(""), "TV");
assert.equal(matching.position, 53);

const prefixed = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "ALA", "A", 53)]),
  "p.A53T",
);
assert.equal(prefixed.status, "diff");
assert.equal(prefixed.variant[0]?.letter, "T");

const threeLetter = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "ALA", "A", 53), atom("ATOM", "CA", "GLY", "A", 54)]),
  "Ala53Thr",
);
assert.equal(threeLetter.status, "diff");
assert.equal(threeLetter.variant.map((residue) => residue.letter).join(""), "TG");

const gapped = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "ALA", "A", 10), atom("ATOM", "CA", "VAL", "A", 12)]),
  "V12T",
);
assert.equal(gapped.status, "diff");
assert.equal(gapped.changeIndex, 1);
assert.deepEqual(
  gapped.wildType.map((residue) => residue.resseq),
  [10, 12],
);
assert.equal(gapped.variant.map((residue) => residue.letter).join(""), "AT");

const twoChains = buildSequenceDiff(
  pdb([
    atom("ATOM", "CA", "GLY", "A", 5),
    atom("ATOM", "CA", "ALA", "B", 5),
    atom("ATOM", "CA", "LEU", "B", 6),
  ]),
  "A5T",
);
assert.equal(twoChains.chainId, "B");
assert.equal(twoChains.changeIndex, 0);
assert.equal(twoChains.variant.map((residue) => residue.letter).join(""), "TL");

const mismatch = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "GLY", "A", 53), atom("ATOM", "CA", "ALA", "A", 54)]),
  "A53T",
);
assert.equal(mismatch.status, "mismatch");
assert.equal(mismatch.changeIndex, null);
assert.equal(mismatch.variant.map((residue) => residue.letter).join(""), "GA");
assert.match(mismatch.notice ?? "", /residue 53 on chain A is G/i);
assert.match(mismatch.notice ?? "", /stated wild type is A/i);

const missing = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "ALA", "A", 10)]),
  "A53T",
);
assert.equal(missing.status, "missing");
assert.equal(missing.changeIndex, null);
assert.equal(missing.variant[0]?.letter, "A");
assert.match(missing.notice ?? "", /Residue 53 is absent/);

const insertion = buildSequenceDiff(
  pdb([
    atom("ATOM", "CA", "ALA", "A", 53, " "),
    atom("ATOM", "CA", "GLY", "A", 53, "A"),
  ]),
  "G53T",
);
assert.equal(insertion.status, "diff");
assert.equal(insertion.changeIndex, 1);
assert.equal(insertion.variant.map((residue) => residue.letter).join(""), "AT");

const selenomet = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "MSE", "A", 5)]),
  "M5A",
);
assert.equal(selenomet.status, "diff");
assert.equal(selenomet.wildType[0]?.letter, "M");
assert.equal(selenomet.variant[0]?.letter, "A");

const secondModel = buildSequenceDiff(
  pdb([
    "MODEL        1",
    atom("ATOM", "CA", "ALA", "A", 5),
    "ENDMDL",
    "MODEL        2",
    atom("ATOM", "CA", "GLY", "A", 5),
    "ENDMDL",
  ]),
  "A5T",
);
assert.equal(secondModel.status, "diff");
assert.equal(secondModel.wildType.map((residue) => residue.letter).join(""), "A");

const ignored = buildSequenceDiff(
  pdb([
    atom("HETATM", "CA", "HOH", "A", 1),
    atom("ATOM", "N", "GLY", "A", 2),
    atom("ATOM", "CA", "ALA", "A", 3),
  ]),
  "A3V",
);
assert.equal(ignored.wildType.map((residue) => residue.letter).join(""), "A");
assert.equal(ignored.changeIndex, 0);

const unreadableVariant = buildSequenceDiff(
  pdb([atom("ATOM", "CA", "ALA", "A", 1)]),
  "not-a-variant",
);
assert.equal(unreadableVariant.status, "unreadable");
assert.equal(unreadableVariant.variant.length, 0);
assert.equal(unreadableVariant.wildType[0]?.letter, "A");

const emptyStructure = buildSequenceDiff("", "A53T");
assert.equal(emptyStructure.status, "unreadable");
assert.equal(emptyStructure.wildType.length, 0);
assert.match(emptyStructure.notice ?? "", /No amino-acid chain/);

console.log("sequence diff checks passed");
