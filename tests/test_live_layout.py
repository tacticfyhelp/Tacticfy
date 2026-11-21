"""Unit tests for the live reader's human-managed-team detection, run against simulated process memory."""

import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

from src.memory.live_layout import FM27LiveSquadReader, LiveReadError, _TeamLayout

CFG = json.loads((Path(__file__).resolve().parent.parent / "config" / "offsets.json").read_text(encoding="utf-8"))
LAYOUT = CFG["fm27_live_layout"]
MODULE_BASE = 0x7FF000000000
MEM_BASE = 0x10000000
MEM_SIZE = 0x200000


class FakeMemory:
    """A flat chunk of 'process memory' plus helpers to build team / manager / player objects in it."""

    def __init__(self) -> None:
        self.buf = bytearray(MEM_SIZE)
        self.cursor = MEM_BASE + 0x1000
        self.team = _TeamLayout.from_config(LAYOUT["human_team"])
        db = LAYOUT["player_db_object"]
        self.person_vt = MODULE_BASE + int(db["vtable_rva"], 16)
        self.uid_off = int(db["uid_offset"], 16)
        self.ca_off = int(db["ca_u16"], 16)
        self.pa_off = int(db["pa_u16"], 16)

    def alloc(self, size: int) -> int:
        addr = self.cursor
        self.cursor += (size + 0xF) & ~0xF
        return addr

    def put_q(self, addr: int, value: int) -> None:
        struct.pack_into("<Q", self.buf, addr - MEM_BASE, value)

    def put(self, addr: int, fmt: str, value: int) -> None:
        struct.pack_into(fmt, self.buf, addr - MEM_BASE, value)

    def read(self, addr: int, size: int) -> bytes:
        off = addr - MEM_BASE
        if off < 0 or off >= MEM_SIZE:
            return b""
        return bytes(self.buf[off: off + size])

    def player(self, uid: int, ca: int, pa: int) -> int:
        """Allocate a player object; returns the pointer stored in team vectors (object start)."""
        obj = self.alloc(self.team.person_offset + 0x1400)
        person = obj + self.team.person_offset
        self.put_q(person, self.person_vt)
        self.put(person + self.uid_off, "<I", uid)
        self.put(person + self.ca_off, "<H", ca)
        self.put(person + self.pa_off, "<H", pa)
        return obj

    def team_obj(self, player_ptrs, human: bool) -> int:
        team = self.alloc(0xB8)
        self.put_q(team, MODULE_BASE + self.team.team_vtable_rva)
        vec = self.alloc(8 * max(1, len(player_ptrs)))
        for i, p in enumerate(player_ptrs):
            self.put_q(vec + 8 * i, p)
        self.put_q(team + self.team.players_vector, vec)
        self.put_q(team + self.team.players_vector + 8, vec + 8 * len(player_ptrs))
        manager = self.alloc(0x60)
        mgr_rva = self.team.human_manager_vtable_rva if human else self.team.human_manager_vtable_rva + 0xCE00
        self.put_q(manager, MODULE_BASE + mgr_rva)
        self.put_q(team + self.team.manager, manager)
        return team


@unittest.skipUnless(sys.platform == "win32", "the live reader is Windows-only")
class TestHumanTeamDetection(unittest.TestCase):
    def make_reader(self, mem: FakeMemory, layout=None) -> FM27LiveSquadReader:
        reader = FM27LiveSquadReader(layout or LAYOUT)
        reader._read = mem.read
        reader._regions = lambda: [(MEM_BASE, MEM_SIZE, 0x04, 0x20000)]
        reader._chunks = lambda regions, private_only=True, writable_only=False: iter([(MEM_BASE, mem.read(MEM_BASE, MEM_SIZE))])
        reader._module_base = lambda pid, name: MODULE_BASE
        reader._read_name = lambda ptr_field: ""
        return reader

    def read(self, reader: FM27LiveSquadReader):
        with mock.patch.object(reader._k32, "OpenProcess", return_value=1), \
                mock.patch.object(reader._k32, "CloseHandle", return_value=True):
            return reader.read_records(pid=1234)

    def test_human_team_is_chosen_over_ai_teams(self) -> None:
        mem = FakeMemory()
        ai_squad = [mem.player(100 + i, 120, 130) for i in range(25)]
        my_squad = [mem.player(500 + i, 90 + i, 140) for i in range(38)]
        mem.team_obj(ai_squad, human=False)
        mem.team_obj(my_squad, human=True)
        mem.team_obj(ai_squad[:20], human=False)
        reader = self.make_reader(mem)
        records = self.read(reader)
        self.assertEqual(reader.last_source, "human_team")
        self.assertEqual(reader.last_human_teams, 1)
        self.assertEqual(sorted(r.uid for r in records), list(range(500, 538)))
        self.assertEqual({r.ca for r in records}, set(range(90, 128)))

    def test_stale_team_with_dangling_pointer_is_ignored(self) -> None:
        mem = FakeMemory()
        stale = [mem.player(900 + i, 100, 110) for i in range(16)] + [MEM_BASE + 0x40]  # last ptr: no player there
        mem.team_obj(stale, human=True)
        live = [mem.player(700 + i, 110, 120) for i in range(30)]
        mem.team_obj(live, human=True)
        reader = self.make_reader(mem)
        records = self.read(reader)
        self.assertEqual(reader.last_human_teams, 1)
        self.assertEqual(sorted(r.uid for r in records), list(range(700, 730)))

    def test_signature_array_is_never_used_when_human_team_is_configured(self) -> None:
        mem = FakeMemory()
        mem.team_obj([mem.player(1, 100, 120) for _ in range(1)], human=False)
        reader = self.make_reader(mem)
        with mock.patch.object(reader, "_locate_squad", side_effect=AssertionError("stale array consulted")):
            with self.assertRaises(LiveReadError) as ctx:
                self.read(reader)
        self.assertIn("No team managed by a human", str(ctx.exception))

    def test_duplicate_players_are_listed_once_and_bad_values_dropped(self) -> None:
        mem = FakeMemory()
        p = mem.player(42, 120, 130)
        broken = mem.player(43, 0, 130)  # CA 0 = undecodable -> dropped
        mem.team_obj([p, p, broken, mem.player(44, 100, 150)], human=True)
        records = self.read(self.make_reader(mem))
        self.assertEqual([r.uid for r in records], [42, 44])

    def test_largest_human_squad_wins(self) -> None:
        mem = FakeMemory()
        mem.team_obj([mem.player(300 + i, 110, 120) for i in range(23)], human=True)  # e.g. a national team
        mem.team_obj([mem.player(600 + i, 110, 120) for i in range(40)], human=True)  # the club
        reader = self.make_reader(mem)
        records = self.read(reader)
        self.assertEqual(reader.last_human_teams, 2)
        self.assertEqual(len(records), 40)

    def test_layout_without_human_team_uses_legacy_path(self) -> None:
        legacy = {k: v for k, v in LAYOUT.items() if k != "human_team"}
        reader = FM27LiveSquadReader(legacy)
        self.assertIsNone(reader.team_layout)

    def test_config_values_parse(self) -> None:
        t = _TeamLayout.from_config(LAYOUT["human_team"])
        self.assertEqual(t.players_vector, 0x38)
        self.assertEqual(t.manager, 0x80)
        self.assertEqual(t.person_offset, 0x148)
        with self.assertRaises(LiveReadError):
            _TeamLayout.from_config({"team_vtable_rva": "0x1"})


if __name__ == "__main__":
    unittest.main()
