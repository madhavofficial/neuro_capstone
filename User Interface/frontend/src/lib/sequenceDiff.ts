export interface ChainResidue {
  resseq: number;
  icode: string;
  letter: string;
}

export interface SequenceChain {
  chainId: string;
  residues: ChainResidue[];
}

export type SequenceDiffStatus = "diff" | "mismatch" | "missing" | "unreadable";

export interface SequenceDiff {
  status: SequenceDiffStatus;
  notice: string | null;
  chainId: string | null;
  wildType: ChainResidue[];
  variant: ChainResidue[];
  changeIndex: number | null;
  wildLetter: string | null;
  mutantLetter: string | null;
  position: number | null;
  variantLabel: string | null;
}

const STANDARD_THREE_TO_ONE: Record<string, string> = {
  ALA: "A",
  ARG: "R",
  ASN: "N",
  ASP: "D",
  CYS: "C",
  GLN: "Q",
  GLU: "E",
  GLY: "G",
  HIS: "H",
  ILE: "I",
  LEU: "L",
  LYS: "K",
  MET: "M",
  PHE: "F",
  PRO: "P",
  SER: "S",
  THR: "T",
  TRP: "W",
  TYR: "Y",
  VAL: "V",
};

const PDB_THREE_TO_ONE: Record<string, string> = {
  ...STANDARD_THREE_TO_ONE,
  MSE: "M",
};

const STANDARD_LETTERS = new Set(Object.values(STANDARD_THREE_TO_ONE));

function sliceField(line: string, start: number, end: number): string {
  return line.slice(start - 1, end);
}

function parseMissenseVariant(
  variant: string,
): { wildLetter: string; position: number; mutantLetter: string } | null {
  let cleaned = variant.trim();
  if (cleaned.startsWith("p.")) {
    cleaned = cleaned.slice(2);
  }

  const oneLetter = cleaned.toUpperCase().match(/^([A-Z])(\d+)([A-Z])$/);
  if (oneLetter) {
    const wildLetter = oneLetter[1];
    const mutantLetter = oneLetter[3];
    if (!STANDARD_LETTERS.has(wildLetter) || !STANDARD_LETTERS.has(mutantLetter)) {
      return null;
    }
    return {
      wildLetter,
      position: Number(oneLetter[2]),
      mutantLetter,
    };
  }

  const threeLetter = cleaned.match(/^([A-Za-z]{3})(\d+)([A-Za-z]{3})$/);
  if (!threeLetter) {
    return null;
  }

  const wildLetter = STANDARD_THREE_TO_ONE[threeLetter[1].toUpperCase()];
  const mutantLetter = STANDARD_THREE_TO_ONE[threeLetter[3].toUpperCase()];
  if (!wildLetter || !mutantLetter) {
    return null;
  }

  return {
    wildLetter,
    position: Number(threeLetter[2]),
    mutantLetter,
  };
}

function parsePdbChains(pdbContent: string): SequenceChain[] {
  const chains = new Map<string, ChainResidue[]>();
  const seen = new Set<string>();
  let modelCount = 0;
  let pastFirstModel = false;

  for (const line of pdbContent.split(/\r?\n/)) {
    const record = sliceField(line, 1, 6).trim();

    if (record === "MODEL") {
      modelCount += 1;
      if (modelCount > 1) {
        pastFirstModel = true;
      }
      continue;
    }

    if (record === "ENDMDL") {
      if (modelCount >= 1) {
        pastFirstModel = true;
      }
      continue;
    }

    if (pastFirstModel || record !== "ATOM") {
      continue;
    }

    if (sliceField(line, 13, 16).trim() !== "CA") {
      continue;
    }

    const letter = PDB_THREE_TO_ONE[sliceField(line, 18, 20).trim().toUpperCase()];
    if (!letter) {
      continue;
    }

    const resseqText = sliceField(line, 23, 26).trim();
    if (!/^-?\d+$/.test(resseqText)) {
      continue;
    }

    const chainId = sliceField(line, 22, 22) || " ";
    const resseq = Number(resseqText);
    const icode = sliceField(line, 27, 27).trim();
    const key = `${chainId}|${resseq}|${icode}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);

    const residues = chains.get(chainId) ?? [];
    if (!chains.has(chainId)) {
      chains.set(chainId, residues);
    }
    residues.push({ resseq, icode, letter });
  }

  return [...chains.entries()].map(([chainId, residues]) => ({
    chainId,
    residues,
  }));
}

function chainPhrase(chainId: string): string {
  return chainId.trim() ? `chain ${chainId}` : "the unlabeled chain";
}

function emptyDiff(
  notice: string,
  variantLabel: string | null,
  parsed: { wildLetter: string; position: number; mutantLetter: string } | null,
  chain: SequenceChain | null,
): SequenceDiff {
  return {
    status: "unreadable",
    notice,
    chainId: chain?.chainId ?? null,
    wildType: chain?.residues ?? [],
    variant: [],
    changeIndex: null,
    wildLetter: parsed?.wildLetter ?? null,
    mutantLetter: parsed?.mutantLetter ?? null,
    position: parsed?.position ?? null,
    variantLabel,
  };
}

export function buildSequenceDiff(pdbContent: string, variant: string): SequenceDiff {
  const chains = parsePdbChains(pdbContent);
  const parsed = parseMissenseVariant(variant);
  const variantLabel = variant.trim() || null;

  if (chains.length === 0) {
    return emptyDiff(
      "No amino-acid chain was found in this structure.",
      variantLabel,
      parsed,
      null,
    );
  }

  if (!parsed) {
    return emptyDiff(
      "This variant could not be read as a missense change. Use a code such as A53T.",
      variantLabel,
      null,
      chains[0],
    );
  }

  const matched = chains
    .map((chain) => ({
      chain,
      index: chain.residues.findIndex(
        (residue) =>
          residue.resseq === parsed.position && residue.letter === parsed.wildLetter,
      ),
    }))
    .find((candidate) => candidate.index >= 0);

  if (matched) {
    return {
      status: "diff",
      notice: null,
      chainId: matched.chain.chainId,
      wildType: matched.chain.residues,
      variant: matched.chain.residues.map((residue, index) =>
        index === matched.index ? { ...residue, letter: parsed.mutantLetter } : residue,
      ),
      changeIndex: matched.index,
      wildLetter: parsed.wildLetter,
      mutantLetter: parsed.mutantLetter,
      position: parsed.position,
      variantLabel,
    };
  }

  const chainWithPosition =
    chains.find((chain) =>
      chain.residues.some((residue) => residue.resseq === parsed.position),
    ) ?? chains[0];
  const actual = chainWithPosition.residues.find(
    (residue) => residue.resseq === parsed.position,
  );

  if (!actual) {
    return {
      status: "missing",
      notice: `Residue ${parsed.position} is absent from this structure, so this substitution was left unchanged.`,
      chainId: chainWithPosition.chainId,
      wildType: chainWithPosition.residues,
      variant: chainWithPosition.residues,
      changeIndex: null,
      wildLetter: parsed.wildLetter,
      mutantLetter: parsed.mutantLetter,
      position: parsed.position,
      variantLabel,
    };
  }

  return {
    status: "mismatch",
    notice: `Residue ${parsed.position} on ${chainPhrase(chainWithPosition.chainId)} is ${actual.letter}. The stated wild type is ${parsed.wildLetter}, so this substitution was left unchanged.`,
    chainId: chainWithPosition.chainId,
    wildType: chainWithPosition.residues,
    variant: chainWithPosition.residues,
    changeIndex: null,
    wildLetter: parsed.wildLetter,
    mutantLetter: parsed.mutantLetter,
    position: parsed.position,
    variantLabel,
  };
}

export function sequenceDiffSubline(diff: SequenceDiff): string | null {
  if (diff.wildType.length === 0) {
    return null;
  }

  const chain =
    diff.chainId && diff.chainId.trim() ? `Chain ${diff.chainId}` : "Unlabeled chain";
  const length = `${diff.wildType.length} ${
    diff.wildType.length === 1 ? "residue" : "residues"
  }`;

  if (diff.status === "unreadable" || !diff.variantLabel) {
    return `${chain} · ${length}`;
  }

  return `${chain} · ${length} · ${diff.variantLabel}`;
}
