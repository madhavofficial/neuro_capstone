# Benchmark workflow

The checked-in `gold_variants.seed.csv` is a candidate manifest. Resolve it
against ClinVar before calling it a gold set:

```bash
python benchmark/prepare_gold_set.py
python -m benchmark.benchmark --gold data/benchmarks/gold_variants.csv --dry-run
python -m benchmark.benchmark --gold data/benchmarks/gold_variants.csv
```

For the full stage-by-stage benchmark and visual report:

```bash
BENCHMARK_OFFLINE=1 python3 -m benchmark.full_runner \
  --gold data/benchmarks/gold_variants.csv
```

Remove `BENCHMARK_OFFLINE=1` and configure `GROQ_API_KEY` and/or
`OPENROUTER_API_KEY` to run model synthesis. The full runner executes the real
structure, physics, clinical, literature, retrieval, and payload stages for
each ablation. It writes per-run payload/synthesis files under
`data/benchmarks/runs/`, plus `results.jsonl`, `metrics.json`,
`model_comparison.csv`, `benchmark_report.md`, `gbenchmark_report.md`, and
`benchmark_report.html`.

The resolver records a ClinVar variation ID, review status, condition, source
URL, and retrieval date. Unresolved candidates are written to an audit file so
an incomplete reference set is visible and cannot silently be mistaken for a
complete benchmark. The generated
`gold_variants_unresolved.csv` is an audit file. The runner excludes those
rows and prints the verified count; do not report the benchmark as complete
until the verified set reaches the planned 40--60 variants and label balance.

The model catalog includes GPT-OSS 120B on Groq, Llama 3.3 70B and Qwen3 235B
on OpenRouter, with DeepSeek R1 available as an opt-in entry. Verify model IDs
and provider availability at run time because hosted model catalogs change.
