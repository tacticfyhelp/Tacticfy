"""Live RAM reader for Football Manager 27 (fm.exe)."""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional

from src.app_paths import APP_VERSION
from src.models.player import Player, PlayerHiddenAttributes, PlayerVisibleAttributes

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pymem
    import pymem.process
except ImportError:
    pymem = None

log = logging.getLogger("tacticfy.reader")


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``overlay`` into a copy of ``base`` (overlay wins on conflicts)."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class ProcessReadResult:
    """Result returned when attempting to read squad data from fm.exe."""

    success: bool
    source: str
    message: str
    players: List[Player] = field(default_factory=list)


class FM27ProcessReader:
    """Reads FM27 player structs directly from fm.exe process memory."""

    def __init__(self, offsets_path: Path, user_offsets_path: Optional[Path] = None) -> None:
        self.offsets_path = Path(offsets_path)
        # Optional writable overlay (user calibration) merged on top of the bundled offsets.
        self.user_offsets_path = Path(user_offsets_path) if user_offsets_path else None
        self.offsets: Dict[str, Any] = self._load_offsets()

    def _load_offsets(self) -> Dict[str, Any]:
        base: Dict[str, Any] = {}
        if self.offsets_path.exists():
            with self.offsets_path.open("r", encoding="utf-8") as handle:
                base = json.load(handle)
        overlay = self._load_user_overlay()
        return deep_merge(base, overlay) if overlay else base

    def _load_user_overlay(self) -> Dict[str, Any]:
        """User calibration overlay; ignored when written by another app version.

        A new release ships offsets for the current FM27 patch, so an overlay calibrated against an
        older release must not shadow them.
        """
        path = self.user_offsets_path
        if path is None or not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                overlay = json.load(handle)
        except (OSError, ValueError) as exc:
            log.warning("Ignoring unreadable user offsets overlay: %s", exc)
            return {}
        if not isinstance(overlay, dict):
            return {}
        if overlay.get("_app_version") != APP_VERSION:
            log.info("Ignoring user offsets overlay from app version %s (running %s)",
                     overlay.get("_app_version"), APP_VERSION)
            return {}
        return overlay

    def reload_offsets(self) -> None:
        """Reload offsets.json from disk after calibration."""
        self.offsets = self._load_offsets()

    @staticmethod
    def is_fm_running(process_name: str = "fm.exe") -> bool:
        """Return True if fm.exe is currently running."""
        if psutil is None:
            return False
        target = process_name.lower()
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name == target:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @staticmethod
    def _normalize_attr(raw_val: int, scale: str) -> int:
        """Convert raw byte value to FM 1-20 attribute scale."""
        if scale == "1-100":
            return max(1, min(20, round(raw_val / 5.0)))
        if raw_val > 20:
            return max(1, min(20, round(raw_val / 5.0)))
        return max(1, min(20, raw_val))

    def parse_player_struct(self, raw_bytes: bytes, player_index: int = 0, name: Optional[str] = None) -> Player:
        """Parse a raw memory buffer representing one FM27 player struct."""
        ps = self.offsets.get("player_struct", {})
        scale = ps.get("attribute_scale", "1-20_or_1-100")

        id_off = int(ps.get("id_offset", 0))
        age_off = int(ps.get("age_offset", 16))
        ca_off = int(ps.get("ca_offset", 20))
        pa_off = int(ps.get("pa_offset", 22))
        wage_off = int(ps.get("wage_offset", 24))
        val_off = int(ps.get("value_offset", 28))

        def read_u32(offset: int, default: int = 0) -> int:
            if 0 <= offset + 4 <= len(raw_bytes):
                return struct.unpack_from("<I", raw_bytes, offset)[0]
            return default

        def read_u16(offset: int, default: int = 0) -> int:
            if 0 <= offset + 2 <= len(raw_bytes):
                return struct.unpack_from("<H", raw_bytes, offset)[0]
            return default

        def read_u8(offset: int, default: int = 10) -> int:
            if 0 <= offset < len(raw_bytes):
                return raw_bytes[offset]
            return default

        player_id = read_u32(id_off, player_index + 1)
        age = max(15, min(45, read_u8(age_off, 23)))
        ca = max(1, min(200, read_u16(ca_off, 120)))
        pa = max(1, min(200, read_u16(pa_off, 140)))
        wage = read_u32(wage_off, 5000)
        value = read_u32(val_off, 1000000)

        vis_base = int(ps.get("visible_attributes_block_offset", 64))
        vis_map = ps.get("visible_attribute_offsets", {})
        vis_kwargs: Dict[str, int] = {}
        for attr_name, rel_off in vis_map.items():
            raw = read_u8(vis_base + int(rel_off), 10)
            vis_kwargs[attr_name] = self._normalize_attr(raw, scale)

        hid_base = int(ps.get("hidden_attributes_block_offset", 128))
        hid_map = ps.get("hidden_attribute_offsets", {})
        hid_kwargs: Dict[str, int] = {"ca": ca, "pa": pa}
        for attr_name, rel_off in hid_map.items():
            raw = read_u8(hid_base + int(rel_off), 10)
            hid_kwargs[attr_name] = max(1, min(20, raw))

        visible = PlayerVisibleAttributes(**vis_kwargs)
        hidden = PlayerHiddenAttributes(**hid_kwargs)
        is_gk = visible.reflexes >= 12 and visible.handling >= 12 and visible.finishing <= 8
        positions = ["GK"] if is_gk else ["MC"]

        return Player(
            player_id=player_id,
            name=name or f"FM27 Player #{player_id}",
            age=age,
            positions=positions,
            wage_weekly=wage,
            market_value=value,
            is_gk=is_gk,
            visible=visible,
            hidden=hidden,
        )

    @staticmethod
    def _find_pid(process_name: str) -> Optional[int]:
        target = process_name.lower()
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if (proc.info.get("name") or "").lower() == target:
                    return proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _read_squad_live_layout(self, process_name: str) -> ProcessReadResult:
        """Read the squad via the verified two-step squad_array + player_db_object layout."""
        import datetime as dt
        from src.memory.live_layout import FM27LiveSquadReader, LiveReadError, record_to_player

        layout_cfg = self.offsets["fm27_live_layout"]
        try:
            pid = self._find_pid(process_name)
            if pid is None:
                return ProcessReadResult(False, "not_running", f"{process_name} exited before it could be read.")
            reader = FM27LiveSquadReader(layout_cfg, process_name)
            records = reader.read_records(pid)
            game_date = layout_cfg.get("game_date")
            today = dt.date.fromisoformat(game_date) if game_date else dt.date.today()
            players = [record_to_player(rec, layout_cfg, today) for rec in records]
        except LiveReadError as exc:
            return ProcessReadResult(False, "live_layout_error", f"fm.exe is running but the live read failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the UI instead of crashing
            return ProcessReadResult(False, "error", f"Unexpected error reading {process_name}: {type(exc).__name__}: {exc}")

        players.sort(key=lambda p: -p.hidden.ca)
        source = "your managed team" if reader.last_source == "human_team" else "fm27_live_layout"
        message = (f"Loaded {len(players)} players directly from {process_name} RAM ({source}). "
                   "Wage/value are not yet mapped and show defaults.")
        full_min = int(layout_cfg.get("squad_array", {}).get("full_squad_min_players", 24))
        # Only the legacy signature array can be a partial match-day copy; the managed team is always complete.
        if reader.last_source == "squad_array" and reader.last_array_used_slots < full_min:
            message += (f" Only a {reader.last_array_used_slots}-player match/partial squad was in memory - "
                        "open the Squad screen in FM27 and reload to get the full squad.")
        return ProcessReadResult(
            success=True,
            source="live_ram",
            message=message,
            players=players,
        )

    def read_squad(self) -> ProcessReadResult:
        """Attach to fm.exe and read the squad if calibrated."""
        process_name = self.offsets.get("process_name", "fm.exe")
        if pymem is None or psutil is None:
            return ProcessReadResult(
                success=False,
                source="unavailable",
                message="pymem or psutil is not installed in this Python environment.",
            )

        if not self.is_fm_running(process_name):
            return ProcessReadResult(
                success=False,
                source="not_running",
                message=f"{process_name} is not running. Using fallback/mock squad instead.",
            )

        if "fm27_live_layout" in self.offsets:
            return self._read_squad_live_layout(process_name)

        if not self.offsets.get("calibrated", False):
            return ProcessReadResult(
                success=False,
                source="uncalibrated",
                message="fm.exe is running, but offsets.json is not calibrated yet. Open 'Calibrate Offsets (IGE)' to scan live memory.",
            )

        try:
            pm = pymem.Pymem(process_name)
            module = pymem.process.module_from_name(pm.process_handle, process_name)
            chain = self.offsets.get("squad_pointer_chain", {})
            base_offset = int(chain.get("base_offset", "0x0"), 16)
            addr = module.lpBaseOfDll + base_offset
            for off_hex in chain.get("offsets", []):
                addr = pm.read_longlong(addr) + int(off_hex, 16)

            stride = int(self.offsets.get("player_struct", {}).get("stride_bytes", 1024))
            players: List[Player] = []
            for idx in range(30):
                try:
                    raw = pm.read_bytes(addr + idx * stride, stride)
                    player = self.parse_player_struct(raw, player_index=idx)
                    if 15 <= player.age <= 45 and 1 <= player.hidden.ca <= 200:
                        players.append(player)
                except Exception:
                    break

            if not players:
                return ProcessReadResult(
                    success=False,
                    source="empty_read",
                    message="Attached to fm.exe, but no valid player structs were found at configured pointers. Please recalibrate offsets.",
                )

            return ProcessReadResult(
                success=True,
                source="live_ram",
                message=f"Loaded {len(players)} players directly from {process_name} RAM.",
                players=players,
            )
        except Exception as exc:
            return ProcessReadResult(
                success=False,
                source="error",
                message=f"Failed to read {process_name} memory: {exc}",
            )
