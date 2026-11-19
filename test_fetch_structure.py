import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

import fetch_structure
import pipeline


def _mock_response(status_code=200, json_data=None, content=b""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.content = content
    return resp


class TestFetchStructureFallback(unittest.TestCase):
    def test_uses_saved_pdb_when_uniprot_returns_403(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = Path(tmpdir) / "SNCA.pdb"
            saved.write_text("ATOM      1  CA  ALA A  53       0.000   0.000   0.000  1.00 90.00           C\n", encoding="utf-8")
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", return_value=_mock_response(status_code=403)) as mock_get:
                result = fetch_structure.get_structure("SNCA")

            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(result, str(saved))
            self.assertIsNone(fetch_structure.get_last_structure_error())

    def test_uses_saved_pdb_when_uniprot_raises_connection_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = Path(tmpdir) / "SNCA.pdb"
            saved.write_text("ATOM      1  CA  ALA A  53       0.000   0.000   0.000  1.00 90.00           C\n", encoding="utf-8")
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", side_effect=requests.exceptions.ConnectionError("proxy blocked")) as mock_get:
                result = fetch_structure.get_structure("SNCA")

            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(result, str(saved))

    def test_pipeline_error_includes_uniprot_failure_when_no_local_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", return_value=_mock_response(status_code=403)):
                with self.assertRaises(RuntimeError) as ctx:
                    pipeline.run_pipeline(
                        "SNCA",
                        "A53T",
                        run_structure=True,
                        run_context=False,
                        run_analysis=False,
                        run_fetch_literature=False,
                        run_process_literature=False,
                    )

            msg = str(ctx.exception)
            self.assertIn("Structure step failed for SNCA A53T", msg)
            self.assertIn("UniProt", msg)
            self.assertIn("403", msg)

    def test_reachable_uniprot_downloads_uncached_alphafold_model(self):
        uniprot_ok = _mock_response(
            status_code=200,
            json_data={
                "results": [
                    {
                        "primaryAccession": "P37840",
                        "proteinDescription": {
                            "recommendedName": {"fullName": {"value": "Alpha-synuclein"}}
                        },
                    }
                ]
            },
        )
        af_api_ok = _mock_response(
            status_code=200,
            json_data=[{"pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P37840-F1-model_v4.pdb"}],
        )
        pdb_download_ok = _mock_response(status_code=200, content=b"HEADER    ALPHAFOLD\nEND\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", side_effect=[uniprot_ok, af_api_ok, pdb_download_ok]) as mock_get:
                result = fetch_structure.get_structure("SNCA")

            self.assertEqual(mock_get.call_count, 3)
            self.assertEqual(result, os.path.join(tmpdir, "SNCA.pdb"))
            self.assertTrue(Path(result).is_file())
            self.assertIn("ALPHAFOLD", Path(result).read_text(encoding="utf-8"))

    def test_reachable_uniprot_still_runs_before_using_saved_pdb(self):
        uniprot_ok = _mock_response(
            status_code=200,
            json_data={
                "results": [
                    {
                        "primaryAccession": "P37840",
                        "proteinDescription": {
                            "recommendedName": {"fullName": {"value": "Alpha-synuclein"}}
                        },
                    }
                ]
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = Path(tmpdir) / "SNCA.pdb"
            saved.write_text("HEADER    CACHED\nEND\n", encoding="utf-8")
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", return_value=uniprot_ok) as mock_get:
                result = fetch_structure.get_structure("SNCA")

            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(result, str(saved))

    def test_empty_uniprot_result_does_not_fall_back_to_local_pdb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = Path(tmpdir) / "BOGUS.pdb"
            saved.write_text("HEADER    STALE\nEND\n", encoding="utf-8")
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", return_value=_mock_response(status_code=200, json_data={"results": []})):
                result = fetch_structure.get_structure("BOGUS")

            self.assertIsNone(result)
            self.assertIn("no reviewed human entry", fetch_structure.get_last_structure_error())

    def test_last_structure_error_is_thread_local(self):
        import threading

        other_error = []

        def worker():
            with tempfile.TemporaryDirectory() as tmpdir:
                with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                     patch.object(fetch_structure.requests, "get", return_value=_mock_response(status_code=502)):
                    fetch_structure.get_structure("OTHER")
            other_error.append(fetch_structure.get_last_structure_error())

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_structure, "STRUCTURE_DIR", tmpdir), \
                 patch.object(fetch_structure.requests, "get", return_value=_mock_response(status_code=403)):
                fetch_structure.get_structure("MAIN")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        self.assertIn("403", fetch_structure.get_last_structure_error())
        self.assertIn("502", other_error[0])


if __name__ == "__main__":
    unittest.main()
