import sys
# Force UTF-8 encoding for stdout to avoid UnicodeEncodeError on Windows terminals
if sys.stdout.encoding is None or sys.stdout.encoding.lower() != 'utf-8':
	try:
		sys.stdout.reconfigure(encoding='utf-8')
	except Exception:
		pass

# Generalized NLP query generator for any protein/variant
import json
import os
import argparse

def load_json(path):
	with open(path, 'r', encoding='utf-8') as f:
		return json.load(f)

def create_nlp_query(physics, context):
	# Extract relevant features for the query
	variant = physics.get("variant", "")
	residue_wt = physics["comparison_view"]["residue"]["wt"]
	residue_mut = physics["comparison_view"]["residue"]["mut"]
	pos = None
	import re
	m = re.match(r"[A-Za-z]+(\d+)[A-Za-z]+", variant)
	if m:
		pos = m.group(1)
	else:
		pos = variant[3:] if len(variant) > 3 else "?"
	delta_vol = physics["deltas"].get("delta_volume", "?")
	delta_hydro = physics["deltas"].get("delta_hydrophobicity", "?")
	exposure = physics.get("structural_context_wt", {}).get("exposure", "")
	query = (
		f"Steric clash and volume increase (ΔV={delta_vol}) at position {pos} "
		f"({residue_wt}→{residue_mut}), disrupting the hydrophobic core (Δhydrophobicity={delta_hydro}, {exposure} residue). "
	)
	# Add context: top disease associations
	diseases = []
	try:
		diseases = [d['disease'] for d in context.get('gene_level_context', {}).get('recall_layer_ensembl', {}).get('top_diseases', [])[:2]]
	except Exception:
		pass
	if diseases:
		query += f"Associated with: {', '.join(diseases)}."
	return query

def main():
	parser = argparse.ArgumentParser(description="Generate NLP query for any protein/variant.")
	parser.add_argument("gene", help="Gene symbol, e.g. SNCA")
	parser.add_argument("variant", help="Variant code, e.g. A53T")
	parser.add_argument("--data-dir", default="data", help="Base data directory")
	args = parser.parse_args()

	# Compose file paths
	base = f"{args.gene}_{args.variant}"
	physics_path = os.path.join(args.data_dir, "analysis", f"{base}_physics.json")
	context_path = os.path.join(args.data_dir, "context", f"{base}_context.json")
	output_dir = os.path.join(args.data_dir, "NLP queries")
	output_path = os.path.join(output_dir, f"{base}_query.txt")

	# Check that required files exist
	if not os.path.exists(physics_path):
		raise FileNotFoundError(f"Missing physics file: {physics_path}")
	if not os.path.exists(context_path):
		raise FileNotFoundError(f"Missing context file: {context_path}")

	physics = load_json(physics_path)
	context = load_json(context_path)
	query = create_nlp_query(physics, context)
	os.makedirs(output_dir, exist_ok=True)
	with open(output_path, 'w', encoding='utf-8') as f:
		f.write(query)
	print(f"NLP query saved to {output_path}\n\n{query}")

if __name__ == "__main__":
	main()
