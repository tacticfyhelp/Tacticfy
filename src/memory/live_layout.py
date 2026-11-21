"""Live squad reader for FM27 driven by the verified `fm27_live_layout` section of offsets.json.

Two-step read (see probe_fm.py for how the layout was derived):
  1. Locate the squad record array by its in-record byte signature + fixed stride; each used record
     carries the person UID.
  2. Find every player database object by its vtable (game_plugin.dll + vtable_rva, ASLR-safe), join
     on UID, and decode attributes, hidden attributes, CA/PA, DOB and names from the DB object.

Read-only: the process is opened with PROCESS_QUERY_INFORMATION | PROCESS_VM_READ only.
"""

from __future__ import annotations

from collections import Counter
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import datetime as dt
import re
import struct
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is in requirements.txt
    np = None

from src.models.player import Player, PlayerHiddenAttributes, PlayerVisibleAttributes

# FM database order of the 15 position-familiarity bytes (validated on a live squad: left-footed
# full-backs land on DL, strikers on ST, holding midfielders on DM, etc.).
POSITION_ORDER = ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "AML", "AMC", "AMR", "ST", "WBL", "WBR"]
APP_POSITIONS = [p for p in POSITION_ORDER if p != "SW"]  # the engine has no sweeper slot
NATURAL_THRESHOLD = 15  # FM "accomplished" or better counts as a playable position

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_GUARD = 0x100
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}
WRITABLE = {0x04, 0x08, 0x40, 0x80}
CHUNK = 32 * 1024 * 1024


class LiveReadError(RuntimeError):
    """Raised when fm.exe is running but the live layout cannot be applied."""


class _MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD),
        ("_a1", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("_a2", wintypes.DWORD),
    ]


def _hex(value: Any) -> int:
    """Parse '0x1A', '0x190 -> ptr ...', or an int."""
    if isinstance(value, int):
        return value
    match = re.match(r"\s*(0x[0-9a-fA-F]+|\d+)", str(value))
    if not match:
        raise LiveReadError(f"Bad offset value in fm27_live_layout: {value!r}")
    return int(match.group(1), 0)


@dataclass
class _Layout:
    stride: int
    marker: bytes
    marker_off: int
    marker2_off: Optional[int]
    sq_uid: int
    sq_ca: int
    module: str
    vtable_rva: int
    positions: int
    attributes: int
    attribute_order: List[str]
    sharpness: int
    fatigue: int
    world_rep: int
    ca: int
    pa: int
    uid: int
    first_name: int
    last_name: int
    personality: int
    personality_order: List[str]
    dob_day: int
    dob_year: int

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "_Layout":
        try:
            sq, db = cfg["squad_array"], cfg["player_db_object"]
            return cls(
                stride=_hex(sq["record_stride"]),
                marker=bytes.fromhex(sq["marker_bytes"]),
                marker_off=_hex(sq["marker_offset"]),
                marker2_off=_hex(sq["secondary_marker_offset"]) if sq.get("secondary_marker_offset") else None,
                sq_uid=_hex(sq["uid_offset"]),
                sq_ca=_hex(sq["ca_offset"]),
                module=db["module"],
                vtable_rva=_hex(db["vtable_rva"]),
                positions=_hex(db["positions_offset"]),
                attributes=_hex(db["attributes_offset"]),
                attribute_order=list(db["attribute_order"]),
                sharpness=_hex(db["sharpness_u16"]),
                fatigue=_hex(db["fatigue_s16"]),
                world_rep=_hex(db["world_reputation_u16"]),
                ca=_hex(db["ca_u16"]),
                pa=_hex(db["pa_u16"]),
                uid=_hex(db["uid_offset"]),
                first_name=_hex(db["first_name"]),
                last_name=_hex(db["last_name"]),
                personality=_hex(db["personality_offset"]),
                personality_order=list(db["personality_order"]),
                dob_day=_hex(db["dob_day_of_year_u16"]),
                dob_year=_hex(db["dob_year_u16"]),
            )
        except KeyError as exc:
            raise LiveReadError(f"fm27_live_layout is missing key {exc}") from exc


@dataclass
class LivePlayerRecord:
    """Decoded raw values for one squad player (before mapping to Player)."""

    slot: int
    uid: int
    name: str
    ca: int
    pa: int
    positions: List[int]
    raw_attributes: List[int]
    personality: List[int]
    dob: dt.date
    sharpness: int
    fatigue: int
    world_rep: int


class FM27LiveSquadReader:
    """Reads the current squad from a running fm.exe using fm27_live_layout."""

    def __init__(self, layout_cfg: Dict[str, Any], process_name: str = "fm.exe") -> None:
        if sys.platform != "win32":
            raise LiveReadError("Live memory reading is only supported on Windows.")
        if np is None:
            raise LiveReadError("numpy is required for the live reader.")
        self.layout = _Layout.from_config(layout_cfg)
        self.process_name = process_name
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._k32.OpenProcess.restype = wintypes.HANDLE
        self._k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
        self._k32.VirtualQueryEx.restype = ctypes.c_size_t
        self._k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                                ctypes.POINTER(ctypes.c_size_t)]
        self._k32.ReadProcessMemory.restype = wintypes.BOOL
        self._k32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._h = None
        self.last_array_used_slots = 0

    # ------------------------------------------------------------------ low-level
    def _read(self, addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        self._k32.ReadProcessMemory(self._h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
        return buf.raw[: got.value]

    def _q(self, addr: int) -> int:
        d = self._read(addr, 8)
        return struct.unpack("<Q", d)[0] if len(d) == 8 else 0

    def _regions(self) -> List[Tuple[int, int, int, int]]:
        out, addr, mbi = [], 0x10000, _MBI()
        while addr < 0x7FFFFFFF0000:
            if not self._k32.VirtualQueryEx(self._h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            prot = mbi.Protect
            if mbi.State == MEM_COMMIT and not prot & PAGE_GUARD and (prot & 0xFF) in READABLE:
                out.append((mbi.BaseAddress, mbi.RegionSize, prot, mbi.Type))
            nxt = mbi.BaseAddress + mbi.RegionSize
            if nxt <= addr:
                break
            addr = nxt
        return out

    def _chunks(self, regions, private_only=True, writable_only=False):
        for base, size, prot, typ in regions:
            if private_only and typ != MEM_PRIVATE:
                continue
            if writable_only and (prot & 0xFF) not in WRITABLE:
                continue
            off = 0
            while off < size:
                n = min(CHUNK, size - off)
                data = self._read(base + off, n)
                if data:
                    yield base + off, data
                off += n

    def _module_base(self, pid: int, name: str) -> int:
        import pymem.process
        mod = pymem.process.module_from_name(self._h, name)
        if mod is None:
            raise LiveReadError(f"{name} is not loaded in {self.process_name} (game still starting?).")
        return mod.lpBaseOfDll

    # ------------------------------------------------------------------ steps
    def _used_slots(self, recs: List[int]) -> int:
        """Distinct players (UIDs with CA != 0) in an array; duplicate copies don't count twice."""
        L = self.layout
        uids = set()
        for base in recs:
            d = self._read(base + L.sq_ca, 2)
            if len(d) == 2 and struct.unpack("<H", d)[0] != 0:
                u = self._read(base + L.sq_uid, 4)
                uids.add(struct.unpack("<I", u)[0] if len(u) == 4 else base)
        return len(uids)

    def _locate_squad_arrays(self, regions) -> List[List[int]]:
        """Every signature-marked record array in memory (record base addresses per array)."""
        L = self.layout
        arrays: List[List[int]] = []
        claimed: set = set()  # marker addresses already assigned to an array
        n = len(L.marker)

        def is_record(m: int) -> bool:
            # Primary marker at m; since the FM27 2026-11-19 patch each record also repeats the marker at
            # secondary_marker_offset, which rejects "phantom" arrays aligned on the second copy.
            if self._read(m, n) != L.marker:
                return False
            return L.marker2_off is None or self._read(m - L.marker_off + L.marker2_off, n) == L.marker

        for addr, data in self._chunks(regions, writable_only=True):
            i = data.find(L.marker)
            while i != -1:
                m = addr + i
                if m not in claimed and is_record(m) and is_record(m + L.stride):
                    while is_record(m - L.stride):
                        m -= L.stride
                    recs = []
                    while is_record(m):
                        claimed.add(m)
                        recs.append(m - L.marker_off)
                        m += L.stride
                    arrays.append(recs)
                i = data.find(L.marker, i + 1)
        return arrays

    def _locate_squad(self, regions) -> List[int]:
        """Prefer the full squad array (most used slots) over match-day / partial arrays."""
        arrays = self._locate_squad_arrays(regions)
        if not arrays:
            return []
        return max(arrays, key=lambda recs: (self._used_slots(recs), len(recs)))

    def _find_db_objects(self, regions, vtable: int, wanted: set) -> Dict[int, int]:
        found: Dict[int, int] = {}
        for addr, data in self._chunks(regions):
            qq = np.frombuffer(data[: len(data) // 8 * 8], "<u8")
            for j in np.flatnonzero(qq == vtable).tolist():
                obj = addr + j * 8
                uid = struct.unpack("<I", self._read(obj + self.layout.uid, 4) or b"\0\0\0\0")[0]
                if uid in wanted and uid not in found:
                    found[uid] = obj
            if len(found) == len(wanted):
                break
        return found

    def _read_name(self, ptr_field: int) -> str:
        target = self._q(self._q(ptr_field))
        raw = self._read(target + 4, 96) if target else b""
        return raw.split(b"\0")[0].decode("utf-8", "replace") if raw else ""

    def _decode(self, slot: int, uid: int, obj: int) -> LivePlayerRecord:
        L = self.layout
        d = self._read(obj, max(L.dob_year, L.personality + 8, L.attributes + 54) + 2)
        u16 = lambda o: struct.unpack_from("<H", d, o)[0]
        day, year = u16(L.dob_day), u16(L.dob_year)
        try:
            dob = dt.date(year, 1, 1) + dt.timedelta(days=max(0, day - 1))
        except (ValueError, OverflowError):
            dob = dt.date(2000, 1, 1)
        name = f"{self._read_name(obj + L.first_name)} {self._read_name(obj + L.last_name)}".strip()
        return LivePlayerRecord(
            slot=slot, uid=uid, name=name or f"FM27 Player #{uid}",
            ca=u16(L.ca), pa=u16(L.pa),
            positions=list(d[L.positions:L.positions + 15]),
            raw_attributes=list(d[L.attributes:L.attributes + len(L.attribute_order)]),
            personality=list(d[L.personality:L.personality + len(L.personality_order)]),
            dob=dob, sharpness=u16(L.sharpness),
            fatigue=struct.unpack_from("<h", d, L.fatigue)[0], world_rep=u16(L.world_rep),
        )

    # ------------------------------------------------------------------ public
    def read_records(self, pid: int) -> List[LivePlayerRecord]:
        L = self.layout
        self._h = self._k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
        if not self._h:
            raise LiveReadError(f"OpenProcess failed (error {ctypes.get_last_error()}). Try running as Administrator.")
        try:
            regions = self._regions()
            recs = self._locate_squad(regions)
            if not recs:
                raise LiveReadError("Squad array signature not found. Load your save and open a squad screen, "
                                    "or the game was patched and the layout needs re-verifying.")
            slots: List[Tuple[int, int, int]] = []
            seen_uids: set = set()
            for slot, base in enumerate(recs):
                d = self._read(base, L.stride)
                if len(d) < L.stride or struct.unpack_from("<H", d, L.sq_ca)[0] == 0:
                    continue
                uid = struct.unpack_from("<I", d, L.sq_uid)[0]
                # FM can keep a second copy of part of the squad in records contiguous with the main
                # array (seen 2026-11-20: 104-slot run, 16 players listed twice) -> one record per UID.
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)
                slots.append((slot, uid, struct.unpack_from("<H", d, L.sq_ca)[0]))
            if not slots:
                raise LiveReadError("Squad array found but all slots are empty.")
            vtable = self._module_base(pid, L.module) + L.vtable_rva
            objs = self._find_db_objects(regions, vtable, {uid for _, uid, _ in slots})
            out: List[LivePlayerRecord] = []
            for slot, uid, sq_ca in slots:
                obj = objs.get(uid)
                if obj is None:
                    continue
                rec = self._decode(slot, uid, obj)
                if rec.ca != sq_ca:  # layout drift guard: DB object must agree with the squad record
                    continue
                out.append(rec)
            self.last_array_used_slots = len(slots)
            if not out:
                raise LiveReadError("Squad slots found but no matching player database objects "
                                    "(vtable_rva may be stale after a game patch).")
            return out
        finally:
            self._k32.CloseHandle(self._h)
            self._h = None


# ---------------------------------------------------------------------- mapping to app model
def familiarity_from_bytes(ratings: List[int]) -> Dict[str, int]:
    return {pos: max(1, min(20, int(v))) for pos, v in zip(POSITION_ORDER, ratings) if pos != "SW"}


def positions_from_familiarity(fam: Dict[str, int]) -> List[str]:
    ranked = sorted((v, -APP_POSITIONS.index(p), p) for p, v in fam.items())
    ranked.reverse()
    playable = [p for v, _, p in ranked if v >= NATURAL_THRESHOLD]
    return playable or [ranked[0][2]]


def record_to_player(rec: LivePlayerRecord, layout_cfg: Dict[str, Any], today: dt.date) -> Player:
    attr_order = layout_cfg["player_db_object"]["attribute_order"]
    pers_order = layout_cfg["player_db_object"]["personality_order"]
    values = {name: max(1, min(20, round(raw / 5))) for name, raw in zip(attr_order, rec.raw_attributes)}
    values.update({name: max(1, min(20, int(v))) for name, v in zip(pers_order, rec.personality)})

    vis_fields = PlayerVisibleAttributes.__dataclass_fields__.keys()
    hid_fields = PlayerHiddenAttributes.__dataclass_fields__.keys()
    visible = PlayerVisibleAttributes(**{k: v for k, v in values.items() if k in vis_fields})
    hidden = PlayerHiddenAttributes(ca=rec.ca, pa=rec.pa, **{k: v for k, v in values.items() if k in hid_fields})

    fam = familiarity_from_bytes(rec.positions)
    positions = positions_from_familiarity(fam)
    left, right = values.get("left_foot", 1), values.get("right_foot", 20)
    foot = "Either" if min(left, right) >= 15 else ("Left" if left > right else "Right")
    age = today.year - rec.dob.year - ((today.month, today.day) < (rec.dob.month, rec.dob.day))

    return Player(
        player_id=rec.uid,
        name=rec.name,
        age=age,
        positions=positions,
        position_familiarity=fam,
        preferred_foot=foot,
        left_foot=left,
        right_foot=right,
        is_gk=positions[0] == "GK",
        visible=visible,
        hidden=hidden,
        # wage_weekly / market_value / contract_expiry_year: not yet mapped in memory -> model defaults
    )
