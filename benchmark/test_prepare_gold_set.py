import unittest
from unittest.mock import patch

from benchmark import prepare_gold_set


def mock_clinvar(review_status, classification):
    return [
        {"esearchresult": {"idlist": ["14007"]}},
        {
            "result": {
                "14007": {
                    "title": "SNCA A53T",
                    "protein_change": "A53T",
                    "germline_classification": {
                        "description": classification,
                        "review_status": review_status,
                    },
                }
            }
        },
    ]


class ClinVarResolverTests(unittest.TestCase):
    def resolve_with(self, review_status, classification, label="pathogenic"):
        with patch.object(
            prepare_gold_set,
            "_get_json",
            side_effect=mock_clinvar(review_status, classification),
        ):
            return prepare_gold_set.resolve({
                "variant_id": "snca-a53t",
                "gene": "SNCA",
                "variant": "A53T",
                "label": label,
                "label_source": "test",
                "clinvar_variation_id": "UNRESOLVED",
                "review_status": "seed",
                "condition": "test",
            })

    def test_reads_germline_review_status(self):
        result = self.resolve_with(
            "criteria provided, multiple submitters, no conflicts",
            "Pathogenic",
        )
        self.assertEqual(
            result["review_status"],
            "criteria provided, multiple submitters, no conflicts",
        )

    def test_rejects_single_submitter_record(self):
        result = self.resolve_with(
            "criteria provided, single submitter", "Pathogenic"
        )
        self.assertEqual(result["clinvar_variation_id"], "UNRESOLVED")

    def test_rejects_conflicting_classification(self):
        result = self.resolve_with(
            "criteria provided, conflicting classifications",
            "Conflicting classifications of pathogenicity",
        )
        self.assertEqual(result["clinvar_variation_id"], "UNRESOLVED")

    def test_requires_classification_to_match_curated_label(self):
        result = self.resolve_with(
            "criteria provided, multiple submitters, no conflicts",
            "Benign",
            label="pathogenic",
        )
        self.assertEqual(result["clinvar_variation_id"], "UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
