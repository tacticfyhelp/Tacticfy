"""Array-of-Bytes (AOB) pattern scanner and IGE auto-calibration wizard."""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional, Tuple

from src.app_paths import APP_VERSION

try:
    import pymem
    import pymem.memory
except ImportError:
    pymem = None


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    """Windows MEMORY_BASIC_INFORMATION64 structure for VirtualQueryEx."""

    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD),
        ("__alignment1", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__alignment2", wintypes.DWORD),
    ]


MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
PAGE_READONLY = 0x02
PAGE_EXECUTE_READWRITE = 0x40
PAGE_GUARD = 0x100


@dataclass
class CalibrationPlayerInput:
    """Known exact values for a player read from the FM27 In-Game Editor."""

    name: str
    age: int
    ca: int
    pa: int
    pace: int
    finishing: int
    passing: int
    tackling: int
    decisions: int


@dataclass
class CalibrationResult:
    """Outcome of scanning memory or simulated buffers for player struct offsets."""

    success: bool
    message: str
    candidate_addresses: List[int] = field(default_factory=list)
    discovered_offsets: Dict[str, Any] = field(default_factory=dict)


class AOBCalibrator:
    """Scans fm.exe memory pages using known In-Game Editor values."""

    def __init__(self, offsets_path: Path) -> None:
        self.offsets_path = Path(offsets_path)

    @staticmethod
    def scan_buffer_for_player(
        buffer: bytes,
        player: CalibrationPlayerInput,
        base_address: int = 0,
        window_bytes: int = 256,
    ) -> List[Tuple[int, Dict[str, Any]]]:
        """Search a byte buffer for a matching CA/PA + attribute signature.

        Checks both 1-20 raw byte encoding and 1-100 (x5) internal encoding.
        """
        matches: List[Tuple[int, Dict[str, Any]]] = []
        ca_pa_bytes = struct.pack("<HH", player.ca, player.pa)

        start = 0
        while True:
            idx = buffer.find(ca_pa_bytes, start)
            if idx == -1:
                break

            region_start = max(0, idx - 64)
            region_end = min(len(buffer), idx + window_bytes)
            region = buffer[region_start:region_end]

            age_positions = [
                pos for pos in range(len(region)) if region[pos] == player.age
            ]
            if age_positions:
                for scale_mult in (1, 5):
                    target_attrs = {
                        "pace": player.pace * scale_mult,
                        "finishing": player.finishing * scale_mult,
                        "passing": player.passing * scale_mult,
                        "tackling": player.tackling * scale_mult,
                        "decisions": player.decisions * scale_mult,
                    }
                    found_rel: Dict[str, int] = {}
                    for attr_name, target_val in target_attrs.items():
                        for pos in range(len(region)):
                            if region[pos] == target_val and pos not in found_rel.values():
                                found_rel[attr_name] = (region_start + pos) - idx
                                break
                    if len(found_rel) == len(target_attrs):
                        struct_addr = base_address + idx
                        discovered: Dict[str, Any] = {
                            "ca_address": struct_addr,
                            "ca_relative": 0,
                            "pa_relative": 2,
                            "age_relative": (region_start + age_positions[0]) - idx,
                            "scale": "1-100" if scale_mult == 5 else "1-20",
                            "sample_attr_relatives": found_rel,
                        }
                        matches.append((struct_addr, discovered))
                        break

            start = idx + 2
        return matches

    def calibrate_from_buffers(
        self,
        buffers: List[Tuple[int, bytes]],
        player_one: CalibrationPlayerInput,
        player_two: Optional[CalibrationPlayerInput] = None,
    ) -> CalibrationResult:
        """Locate player struct layout across memory buffers and save offsets.json."""
        p1_matches: List[Tuple[int, Dict[str, Any]]] = []
        for base_addr, buf in buffers:
            p1_matches.extend(self.scan_buffer_for_player(buf, player_one, base_address=base_addr))

        if not p1_matches:
            return CalibrationResult(
                success=False,
                message="No memory region matched Player 1's CA/PA and attribute signature.",
            )

        selected_addr, selected_layout = p1_matches[0]
        if player_two is not None:
            p2_matches: List[Tuple[int, Dict[str, Any]]] = []
            for base_addr, buf in buffers:
                p2_matches.extend(self.scan_buffer_for_player(buf, player_two, base_address=base_addr))
            if not p2_matches:
                return CalibrationResult(
                    success=False,
                    message="Found Player 1 candidate, but Player 2 validation failed. Double-check IGE values.",
                    candidate_addresses=[m[0] for m in p1_matches],
                )
            stride = abs(p2_matches[0][0] - selected_addr)
            if stride > 0:
                selected_layout["estimated_stride"] = stride
            selected_layout["player_array_start"] = min(selected_addr, p2_matches[0][0])

        self._persist_calibration(selected_layout)
        return CalibrationResult(
            success=True,
            message=f"Calibration succeeded! Discovered {len(p1_matches)} candidate struct(s) and updated offsets.json.",
            candidate_addresses=[m[0] for m in p1_matches],
            discovered_offsets=selected_layout,
        )

    @staticmethod
    def _enumerate_readable_regions(process_handle: int) -> List[Tuple[int, int]]:
        """Enumerate committed, readable heap/data regions on Windows via VirtualQueryEx."""
        regions: List[Tuple[int, int]] = []
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        virtual_query_ex = kernel32.VirtualQueryEx
        virtual_query_ex.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION),
            ctypes.c_size_t,
        ]
        virtual_query_ex.restype = ctypes.c_size_t

        address = 0x10000
        max_address = 0x7FFFFFFFFFFF
        mbi = MEMORY_BASIC_INFORMATION()

        while address < max_address:
            res = virtual_query_ex(
                process_handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )
            if res == 0:
                break
            is_committed = mbi.State == MEM_COMMIT
            is_readable = mbi.Protect in (PAGE_READWRITE, PAGE_READONLY, PAGE_EXECUTE_READWRITE)
            is_not_guard = not (mbi.Protect & PAGE_GUARD)
            if is_committed and is_readable and is_not_guard and 0 < mbi.RegionSize <= 64 * 1024 * 1024:
                regions.append((mbi.BaseAddress, mbi.RegionSize))
            next_addr = mbi.BaseAddress + mbi.RegionSize
            if next_addr <= address:
                break
            address = next_addr
        return regions

    def calibrate_live_process(
        self,
        player_one: CalibrationPlayerInput,
        player_two: Optional[CalibrationPlayerInput] = None,
        process_name: str = "fm.exe",
    ) -> CalibrationResult:
        """Scan readable committed memory pages of a live fm.exe process."""
        if pymem is None:
            return CalibrationResult(
                success=False,
                message="pymem is not installed. Run on Windows with requirements.txt installed.",
            )
        try:
            pm = pymem.Pymem(process_name)
        except Exception as exc:
            return CalibrationResult(
                success=False,
                message=f"Could not attach to {process_name}: {exc}",
            )

        buffers: List[Tuple[int, bytes]] = []
        try:
            regions = self._enumerate_readable_regions(pm.process_handle)
            for base_addr, size in regions:
                try:
                    data = pm.read_bytes(base_addr, size)
                    buffers.append((base_addr, data))
                except Exception:
                    continue
        except Exception as exc:
            return CalibrationResult(
                success=False,
                message=f"Memory page enumeration failed: {exc}",
            )

        if not buffers:
            return CalibrationResult(
                success=False,
                message="Attached to fm.exe, but no readable memory regions were accessible. Try running as Administrator.",
            )

        return self.calibrate_from_buffers(buffers, player_one, player_two)

    def _persist_calibration(self, layout: Dict[str, Any]) -> None:
        """Write the calibration to ``offsets_path``.

        In the app this is the per-user overlay (``%LOCALAPPDATA%\Tacticfy\offsets.json`` when
        installed) that FM27ProcessReader merges over the bundled offsets, so the install folder is
        never written to. Only calibration keys are written; everything else is preserved.
        """
        existing: Dict[str, Any] = {}
        if self.offsets_path.exists():
            with self.offsets_path.open("r", encoding="utf-8") as handle:
                existing = json.load(handle)

        existing["_app_version"] = APP_VERSION
        existing["calibrated"] = True
        existing["last_calibrated_utc"] = datetime.now(timezone.utc).isoformat()
        existing["discovered_layout"] = layout
        struct_cfg = existing.setdefault("player_struct", {})
        if "estimated_stride" in layout:
            struct_cfg["stride_bytes"] = layout["estimated_stride"]
        if "scale" in layout:
            struct_cfg["attribute_scale"] = layout["scale"]

        self.offsets_path.parent.mkdir(parents=True, exist_ok=True)
        with self.offsets_path.open("w", encoding="utf-8") as handle:
            json.dump(existing, handle, indent=2)
