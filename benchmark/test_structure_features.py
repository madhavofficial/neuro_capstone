import tempfile
import unittest
from pathlib import Path

from analyze_structure import (
    AGGREGATION_A3V,
    aggregation_window_size,
    delta_aggregation,
    interface_contacts_lost,
    load_structure,
)


def _atom(serial: int, name: str, resname: str, chain: str, resseq: int, x: float, y: float, z: float) -> str:
    atom_field = f" {name:<3s}" if len(name) < 4 else name
    element = name[0]
    return (
        f"ATOM  {serial:5d} {atom_field} {resname:>3s} {chain}{resseq:4d}"
        f"    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 90.00           {element:>2s}"
    )


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\nEND\n")


class AggregationTests(unittest.TestCase):
    def test_window_follows_sequence_length(self):
        self.assertEqual(aggregation_window_size(75), 5)
        self.assertEqual(aggregation_window_size(175), 7)
        self.assertEqual(aggregation_window_size(300), 9)
        self.assertEqual(aggregation_window_size(301), 11)

    def test_centre_substitution_changes_a4v_by_the_residue_over_the_window(self):
        sequence = "AAAAA"
        delta = delta_aggregation(sequence, 2, "I")
        expected = (AGGREGATION_A3V["I"] - AGGREGATION_A3V["A"]) / 5
        self.assertAlmostEqual(delta, expected, places=4)
        self.assertGreater(delta, 0.0)

    def test_alanine_to_threonine_lowers_aggregation_propensity(self):
        self.assertLess(delta_aggregation("AAAAA", 2, "T"), 0.0)


class InterfaceTests(unittest.TestCase):
    def test_cross_chain_salt_bridge_is_lost_when_the_charge_goes_away(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdb = Path(tmp) / "bridge.pdb"
            _write(
                pdb,
                [
                    _atom(1, "CA", "LYS", "A", 10, 0.0, 0.0, 0.0),
                    _atom(2, "NZ", "LYS", "A", 10, 0.0, 0.0, 1.5),
                    _atom(3, "CA", "ASP", "B", 20, 0.0, 0.0, 8.0),
                    _atom(4, "OD1", "ASP", "B", 20, 0.0, 0.0, 3.0),
                    _atom(5, "OD2", "ASP", "B", 20, 0.0, 0.0, 4.2),
                ],
            )
            structure = load_structure(str(pdb))
            self.assertEqual(interface_contacts_lost(structure, "A", 10, "LYS", "ALA"), 1)
            self.assertEqual(interface_contacts_lost(structure, "A", 10, "LYS", "ARG"), 0)

    def test_same_chain_salt_bridge_is_not_an_interface_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdb = Path(tmp) / "intra.pdb"
            _write(
                pdb,
                [
                    _atom(1, "CA", "LYS", "A", 10, 0.0, 0.0, 0.0),
                    _atom(2, "NZ", "LYS", "A", 10, 0.0, 0.0, 1.5),
                    _atom(3, "CA", "ASP", "A", 20, 0.0, 0.0, 8.0),
                    _atom(4, "OD1", "ASP", "A", 20, 0.0, 0.0, 3.0),
                    _atom(5, "OD2", "ASP", "A", 20, 0.0, 0.0, 4.2),
                    _atom(6, "CA", "ALA", "B", 1, 40.0, 40.0, 40.0),
                    _atom(7, "CB", "ALA", "B", 1, 41.0, 40.0, 40.0),
                ],
            )
            structure = load_structure(str(pdb))
            self.assertEqual(interface_contacts_lost(structure, "A", 10, "LYS", "ALA"), 0)

    def test_one_chain_file_has_no_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdb = Path(tmp) / "mono.pdb"
            _write(
                pdb,
                [
                    _atom(1, "CA", "LYS", "A", 10, 0.0, 0.0, 0.0),
                    _atom(2, "NZ", "LYS", "A", 10, 0.0, 0.0, 1.5),
                    _atom(3, "CA", "ASP", "A", 20, 0.0, 0.0, 8.0),
                    _atom(4, "OD1", "ASP", "A", 20, 0.0, 0.0, 3.0),
                ],
            )
            structure = load_structure(str(pdb))
            self.assertEqual(interface_contacts_lost(structure, "A", 10, "LYS", "ALA"), 0)


if __name__ == "__main__":
    unittest.main()
