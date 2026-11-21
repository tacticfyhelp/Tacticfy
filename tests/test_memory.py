"""Unit tests for FM27 memory struct parsing, AOB calibration, and fallback loaders."""

from pathlib import Path
import struct
import tempfile
import unittest

from src.memory.aob_calibrator import AOBCalibrator, CalibrationPlayerInput
from src.memory.fallback_loader import generate_sample_squad, load_squad_from_file
from src.memory.process_reader import FM27ProcessReader


class TestMemorySubsystem(unittest.TestCase):
    """Validate struct parsing, simulated AOB scanning, and fallback loaders."""

    def test_sample_squad_generation(self) -> None:
        squad = generate_sample_squad()
        self.assertEqual(len(squad), 26)
        self.assertTrue(any(p.is_gk for p in squad))
        self.assertTrue(any(p.pa_ca_delta >= 20 and p.age <= 21 for p in squad))

    def test_struct_parser(self) -> None:
        offsets_path = Path(__file__).resolve().parent.parent / "config" / "offsets.json"
        reader = FM27ProcessReader(offsets_path)
        buf = bytearray(256)
        struct.pack_into("<I", buf, 0, 999)      # player_id
        buf[16] = 22                              # age
        struct.pack_into("<H", buf, 20, 151)      # CA
        struct.pack_into("<H", buf, 22, 175)      # PA
        struct.pack_into("<I", buf, 24, 45000)    # wage
        buf[64 + 33] = 17                         # pace (1-20)
        buf[64 + 3] = 16                          # finishing (1-20)
        buf[128 + 3] = 15                         # professionalism

        player = reader.parse_player_struct(bytes(buf), name="Test Wonderkid")
        self.assertEqual(player.player_id, 999)
        self.assertEqual(player.age, 22)
        self.assertEqual(player.hidden.ca, 151)
        self.assertEqual(player.hidden.pa, 175)
        self.assertEqual(player.visible.pace, 17)
        self.assertEqual(player.visible.finishing, 16)
        self.assertEqual(player.hidden.professionalism, 15)

    def test_aob_calibrator_simulated_buffer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            offsets_copy = Path(tmpdir) / "offsets.json"
            offsets_copy.write_text('{"calibrated": false, "player_struct": {"stride_bytes": 1024}}', encoding="utf-8")
            calibrator = AOBCalibrator(offsets_copy)

            # Build two simulated player structs inside a memory buffer
            mem = bytearray(1024)
            # Player 1 at offset 128
            mem[124] = 21
            struct.pack_into("<HH", mem, 128, 156, 178)
            mem[140] = 15
            mem[141] = 13
            mem[142] = 16
            mem[143] = 16
            mem[144] = 17

            # Player 2 at offset 640
            mem[636] = 23
            struct.pack_into("<HH", mem, 640, 153, 172)
            mem[652] = 17
            mem[653] = 16
            mem[654] = 12
            mem[655] = 8
            mem[656] = 14

            p1 = CalibrationPlayerInput("Joao Neves", 21, 156, 178, pace=15, finishing=13, passing=16, tackling=16, decisions=17)
            p2 = CalibrationPlayerInput("Benjamin Sesko", 23, 153, 172, pace=17, finishing=16, passing=12, tackling=8, decisions=14)
            res = calibrator.calibrate_from_buffers([(0x10000000, bytes(mem))], p1, p2)
            self.assertTrue(res.success, res.message)
            self.assertEqual(res.discovered_offsets.get("estimated_stride"), 512)

    def test_csv_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "squad.csv"
            csv_path.write_text(
                "Name,Age,Position,CA,PA,Wage,Value,Pace,Finishing,Passing\n"
                "Test Striker,21,ST,140,168,25000,18000000,17,16,12\n",
                encoding="utf-8",
            )
            players = load_squad_from_file(csv_path)
            self.assertEqual(len(players), 1)
            self.assertEqual(players[0].name, "Test Striker")
            self.assertEqual(players[0].visible.pace, 17)


if __name__ == "__main__":
    unittest.main()
