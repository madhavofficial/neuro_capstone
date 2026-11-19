import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import assemble_payload
import pipeline
from benchmark.full_runner import _check_synthesis


def _mock_epmc_response(results, next_cursor=None):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    body = {"resultList": {"result": results}}
    if next_cursor is not None:
        body["nextCursorMark"] = next_cursor
    resp.json.return_value = body
    return resp


class TestDbsnpCitationsIntoEvidence(unittest.TestCase):
    def test_extract_dbsnp_citation_pmids_normalizes_and_deduplicates(self):
        context = {
            "dbsnp": {
                "rsid": "rs1800458",
                "dbsnp_data": {
                    "citations": [31270413, "31270413", "PMID: 7896964", "not-a-pmid", None, 12],
                },
            }
        }
        self.assertEqual(pipeline.extract_dbsnp_citation_pmids(context), ["31270413", "7896964"])

    def test_fetch_literature_merges_dbsnp_abstracts_with_epmc_and_skips_abstractless_pmids(self):
        epmc_search = _mock_epmc_response(
            [
                {
                    "pmid": "31217996",
                    "title": "TTR Gly6Ser polymorphism study",
                    "abstractText": "Europe PMC abstract for TTR G26S.",
                }
            ],
            next_cursor="*",
        )
        dbsnp_batch = _mock_epmc_response(
            [
                {
                    "pmid": "31270413",
                    "title": "gnomAD frequency analysis of TTR variants",
                    "abstractText": "Population allele frequencies of TTR G26S in gnomAD.",
                },
                {
                    "pmid": "99999999",
                    "title": "No abstract entry",
                    "abstractText": "",
                },
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(pipeline, "_require_literature_runtime"), \
                 patch.object(pipeline.time, "sleep"), \
                 patch("requests.get", side_effect=[epmc_search, dbsnp_batch]):
                corpus_path = pipeline.fetch_literature_json(
                    "TTR",
                    "G26S",
                    literature_dir=tmpdir,
                    extra_pmids=["31270413", "99999999", "88888888"],
                )

            papers = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
            by_pmid = {p["pmid"]: p for p in papers}
            self.assertIn("31217996", by_pmid)
            self.assertIn("31270413", by_pmid)
            self.assertEqual(by_pmid["31270413"]["source"], "dbsnp_citation")
            self.assertNotIn("99999999", by_pmid)
            self.assertNotIn("88888888", by_pmid)

    def test_fetch_papers_by_pmids_fetches_beyond_50_in_batches(self):
        pmids = [str(10000000 + i) for i in range(60)]

        def fake_get(url, params=None, timeout=30):
            query = params["query"]
            batch_ids = [tok.split("EXT_ID:")[1] for tok in query.split(" OR ")]
            return _mock_epmc_response(
                [{"pmid": pid, "title": f"Title {pid}", "abstractText": f"Abstract for {pid}."} for pid in batch_ids]
            )

        with patch("requests.get", side_effect=fake_get) as mock_get:
            papers = pipeline.fetch_papers_by_pmids(pmids)

        self.assertEqual(len(papers), 60)
        self.assertEqual(mock_get.call_count, 3)  # 25 + 25 + 10

    def test_short_dbsnp_abstract_survives_chunking_and_runs_through_vector_engine(self):
        import vector_engine

        with tempfile.TemporaryDirectory() as tmpdir:
            lit_dir = Path(tmpdir) / "literature"
            faiss_dir = Path(tmpdir) / "faiss"
            lit_dir.mkdir()
            faiss_dir.mkdir()

            corpus = [
                {
                    "pmid": "31217996",
                    "title": "TTR Gly6Ser polymorphism",
                    "abstract": "TTR G26S is a benign polymorphism observed in healthy populations.",
                },
                {
                    "pmid": "31270413",
                    "title": "gnomAD frequency of TTR G26S",
                    "abstract": "TTR G26S allele frequency in gnomAD is high and benign.",
                    "source": "dbsnp_citation",
                },
            ]
            (lit_dir / "TTR_G26S_corpus.json").write_text(json.dumps(corpus), encoding="utf-8")

            chunked_path = pipeline.process_literature_json("TTR", "G26S", literature_dir=str(lit_dir))
            chunks = json.loads(Path(chunked_path).read_text(encoding="utf-8"))
            self.assertEqual({c["pmid"] for c in chunks}, {"31217996", "31270413"})

            with patch.object(vector_engine, "_get_chunked_corpus_path", return_value=chunked_path), \
                 patch.object(vector_engine, "_get_faiss_dir", return_value=str(faiss_dir)):
                vector_engine.setup_pipeline("TTR", "G26S")
                ranked = vector_engine.retrieve_evidence("TTR", "G26S", "TTR G26S gnomAD allele frequency benign")

            self.assertIn("31270413", {r["pmid"] for r in ranked})
            self.assertTrue(all("rerank_score" in r for r in ranked))

    def test_retrieved_dbsnp_paper_is_citation_valid_and_unretrieved_stays_unverified(self):
        # Simulate encoder/reranker output containing both an EPMC chunk and a
        # dbSNP citation chunk passing the 0.70 gate, plus a low-scoring dbSNP
        # chunk that fails the gate.
        ranked_chunks = [
            {
                "pmid": "31217996",
                "title": "TTR Gly6Ser polymorphism study",
                "chunk": "TTR G26S is a benign polymorphism.",
                "rerank_score": 0.91,
            },
            {
                "pmid": "31270413",
                "title": "gnomAD frequency analysis of TTR variants",
                "chunk": "TTR G26S allele frequency in gnomAD is common.",
                "rerank_score": 0.82,
            },
            {
                "pmid": "7896964",
                "title": "Unrelated low-score chunk",
                "chunk": "Low relevance text.",
                "rerank_score": 0.25,
            },
        ]
        clinical_context = {
            "dbsnp": {
                "dbsnp_data": {
                    "citations": [31270413, 7896964, 55555555],
                }
            }
        }
        payload = assemble_payload.assemble_payload(
            query="TTR G26S",
            ranked_results=ranked_chunks,
            rag_status="SUCCESS",
            clinical_context=clinical_context,
        )
        evidence_pmids = {item["pmid"] for item in payload["evidence"]}
        self.assertEqual(evidence_pmids, {"31217996", "31270413"})

        synthesis = {
            "prediction": "benign",
            "conclusion": "TTR G26S is benign.",
            "uncertainty": False,
            "scope": "variant",
            "claims": [
                {"text": "TTR G26S is common in gnomAD.", "pmid": "31270413", "claim_type": "literature"},
                {"text": "TTR G26S cited in unretrieved dbSNP entry.", "pmid": "55555555", "claim_type": "literature"},
                {"text": "TTR G26S low-score paper.", "pmid": "7896964", "claim_type": "literature"},
            ],
        }
        valid, checks, _unc, _scope = _check_synthesis(synthesis, payload, {"gene": "TTR", "variant": "G26S"})
        self.assertTrue(valid)
        by_pmid = {c["pmid"]: c for c in checks}
        self.assertTrue(by_pmid["31270413"]["citation_valid"])
        self.assertFalse(by_pmid["31270413"]["unsupported"])
        self.assertFalse(by_pmid["55555555"]["citation_valid"])
        self.assertTrue(by_pmid["55555555"]["unsupported"])
        self.assertFalse(by_pmid["7896964"]["citation_valid"])
        self.assertTrue(by_pmid["7896964"]["unsupported"])


if __name__ == "__main__":
    unittest.main()
