"""Standalone diagnostic: attach to a live fm.exe and probe its memory for player structs.

Read-only. Does not touch the UI, engine, or config/offsets.json.

Usage:
    .venv\\Scripts\\python.exe probe_fm.py                      # access check + heuristic scan
    .venv\\Scripts\\python.exe probe_fm.py --name "Bukayo Saka"  # also find a name string (UTF-8/UTF-16)
    .venv\\Scripts\\python.exe probe_fm.py --ca 165 --pa 180     # also find u16 CA/PA pairs
"""

from __future__ import annotations

import argparse
import ctypes
import struct
import sys
import time
from collections import Counter
from ctypes import wintypes

import numpy as np

PROCESS_NAME = "fm.exe"

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
MEM_MAPPED = 0x40000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
READABLE = {0x02, 0x04, 0x08, 0x20, 0x40, 0x80}  # RO, RW, WC, XR, XRW, XWC
WRITABLE = {0x04, 0x08, 0x40, 0x80}

CHUNK = 32 * 1024 * 1024
ATTR_COUNT = 36          # outfield visible attributes
MAX_RUN = 96             # longer in-range runs are almost always tables/padding, not a player


class MBI(ctypes.Structure):
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


k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.CloseHandle.argtypes = [wintypes.HANDLE]


def find_pid(name: str) -> int | None:
    import psutil
    for p in psutil.process_iter(["name", "pid"]):
        if (p.info["name"] or "").lower() == name.lower():
            return p.info["pid"]
    return None


def rpm(h, addr: int, size: int) -> tuple[bytes | None, int, int]:
    """ReadProcessMemory -> (data, bytes_read, last_error)."""
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got))
    err = 0 if ok else ctypes.get_last_error()
    if got.value == 0:
        return None, 0, err
    return buf.raw[: got.value], got.value, err


def regions(h):
    addr, mbi = 0x10000, MBI()
    while addr < 0x7FFFFFFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        yield mbi.BaseAddress, mbi.RegionSize, mbi.State, mbi.Protect, mbi.Type
        nxt = mbi.BaseAddress + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt


def hexdump(data: bytes, base: int, width: int = 16) -> str:
    out = []
    for i in range(0, len(data), width):
        row = data[i:i + width]
        hx = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        out.append(f"    {base + i:016x}  {hx:<{width * 3}} {asc}")
    return "\n".join(out)


# --------------------------------------------------------------------------- step 1
def access_check(pid: int):
    print("=" * 78)
    print(f"STEP 1: attach + access check  (pid {pid})")
    print("=" * 78)

    # pymem attach (what the app uses)
    try:
        import pymem
        import pymem.process
        pm = pymem.Pymem(PROCESS_NAME)
        mod = pymem.process.module_from_name(pm.process_handle, PROCESS_NAME)
        hdr = pm.read_bytes(mod.lpBaseOfDll, 2)
        print(f"  pymem attach: OK   module base=0x{mod.lpBaseOfDll:x} size=0x{mod.SizeOfImage:x} "
              f"header={hdr!r}")
        pm.close_process()
    except Exception as exc:  # noqa: BLE001
        print(f"  pymem attach: FAILED -> {type(exc).__name__}: {exc}")

    # raw ctypes, minimal rights
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print(f"  OpenProcess(QUERY|VM_READ): FAILED, GetLastError={ctypes.get_last_error()}")
        sys.exit(1)
    print("  OpenProcess(QUERY|VM_READ): OK")

    stats = Counter()
    errs = Counter()
    total_commit = readable_bytes = 0
    t0 = time.time()
    regs = []
    for base, size, state, prot, typ in regions(h):
        if state != MEM_COMMIT:
            continue
        total_commit += size
        p = prot & 0xFF
        if prot & PAGE_GUARD or p == PAGE_NOACCESS or p not in READABLE:
            stats["skipped_noaccess_or_guard"] += 1
            continue
        regs.append((base, size, prot, typ))
        # probe first page of every readable region
        data, n, err = rpm(h, base, min(size, 4096))
        if data:
            stats["probe_ok"] += 1
            readable_bytes += size
        else:
            stats["probe_fail"] += 1
            errs[err] += 1
    kind = Counter("PRIVATE" if t == MEM_PRIVATE else "IMAGE" if t == MEM_IMAGE else "MAPPED"
                   for _, _, _, t in regs)
    print(f"  committed: {total_commit / 2**30:.2f} GiB   readable regions: {len(regs)} "
          f"({readable_bytes / 2**30:.2f} GiB)   by type: {dict(kind)}")
    print(f"  first-page RPM probe: ok={stats['probe_ok']} fail={stats['probe_fail']} "
          f"skipped(noaccess/guard)={stats['skipped_noaccess_or_guard']}   ({time.time() - t0:.1f}s)")
    if errs:
        print(f"  RPM error codes: {dict(errs)}  (5=ACCESS_DENIED, 299=PARTIAL_COPY)")
    verdict = "NO ReadProcessMemory block detected" if stats["probe_fail"] == 0 else \
        "SOME reads failed - see error codes"
    print(f"  VERDICT: {verdict}")
    return h, regs


# --------------------------------------------------------------------------- step 2
def iter_chunks(h, regs, private_writable_only=True):
    for base, size, prot, typ in regs:
        if private_writable_only and (typ != MEM_PRIVATE or (prot & 0xFF) not in WRITABLE):
            continue
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            data, got, _ = rpm(h, base + off, n)
            if data:
                yield base + off, data
            off += n


def runs_in_range(a: np.ndarray, lo: int, hi: int, min_len: int, max_len: int):
    m = ((a >= lo) & (a <= hi)).astype(np.int8)
    d = np.diff(np.concatenate(([0], m, [0])))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    lens = ends - starts
    keep = (lens >= min_len) & (lens <= max_len)
    return starts[keep], lens[keep]


def score_block(blk: np.ndarray, scale: int) -> float | None:
    """Return a plausibility score for an attribute block, or None if implausible."""
    distinct = len(np.unique(blk))
    std = float(blk.std())
    if scale == 20:
        if distinct < 9 or std < 2.5 or blk.max() - blk.min() < 9:
            return None
    else:
        if distinct < 16 or std < 10 or blk.max() - blk.min() < 40:
            return None
        # reject ASCII-ish text (digits/uppercase/punct dominate)
        txt = np.isin(blk, np.frombuffer(b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ _-.,:/", np.uint8)).mean()
        if txt > 0.6:
            return None
    # long runs of a single value are tables, not players
    if np.max(np.bincount(blk)) > len(blk) * 0.25:
        return None
    # monotonic sequences are lookup tables
    diffs = np.diff(blk.astype(np.int16))
    if (diffs >= 0).mean() > 0.85 or (diffs <= 0).mean() > 0.85:
        return None
    return distinct + std / (5 if scale == 100 else 1)


def heuristic_scan(h, regs, top: int):
    print()
    print("=" * 78)
    print("STEP 2: heuristic scan of private RW heap for attribute blocks")
    print(f"        (runs of {ATTR_COUNT}..{MAX_RUN} bytes in 1..20 or 1..100, varied, non-monotonic)")
    print("=" * 78)
    t0 = time.time()
    scanned = 0
    cands = {20: [], 100: []}
    for base, data in iter_chunks(h, regs):
        scanned += len(data)
        a = np.frombuffer(data, dtype=np.uint8)
        for scale, (lo, hi) in ((20, (1, 20)), (100, (1, 100))):
            starts, lens = runs_in_range(a, lo, hi, ATTR_COUNT, MAX_RUN)
            for s, ln in zip(starts.tolist(), lens.tolist()):
                blk = a[s:s + ln]
                sc = score_block(blk, scale)
                if sc is not None:
                    cands[scale].append((sc, base + s, ln, base, data, s))
            # keep memory bounded: drop raw refs for low scorers later
        for scale in cands:
            if len(cands[scale]) > 20000:
                cands[scale].sort(key=lambda c: -c[0])
                cands[scale] = cands[scale][:5000]
    print(f"  scanned {scanned / 2**30:.2f} GiB in {time.time() - t0:.1f}s")

    for scale in (20, 100):
        lst = sorted(cands[scale], key=lambda c: -c[0])
        print()
        print(f"  --- scale 1..{scale}: {len(lst)} candidate blocks ---")
        if not lst:
            continue
        # stride analysis: player objects of the same class tend to sit at a fixed spacing
        addrs = sorted(c[1] for c in lst)
        deltas = Counter(b - a for a, b in zip(addrs, addrs[1:]) if 64 <= b - a <= 0x4000)
        common = deltas.most_common(5)
        print(f"  most common spacing between candidates: "
              + ", ".join(f"0x{d:x}({d})x{n}" for d, n in common) if common else "  no repeating spacing")
        for sc, addr, ln, cbase, data, s in lst[:top]:
            vals = list(data[s:s + ln])
            print(f"\n  [score {sc:5.1f}] addr=0x{addr:016x} run_len={ln}")
            print(f"    values: {vals[:47]}")
            ctx_start = max(0, s - 32)
            print(hexdump(data[ctx_start:s + ln + 16], cbase + ctx_start))


# --------------------------------------------------------------------------- optional targeted
def targeted_scan(h, regs, name: str | None, ca: int | None, pa: int | None, top: int):
    print()
    print("=" * 78)
    print("STEP 3: targeted search")
    print("=" * 78)
    needles = []
    if name:
        needles.append(("utf8 name", name.encode("utf-8")))
        needles.append(("utf16 name", name.encode("utf-16-le")))
    if ca is not None and pa is not None:
        needles.append(("u16 CA,PA", struct.pack("<HH", ca, pa)))
        needles.append(("u8 CA,PA", bytes([ca & 0xFF, pa & 0xFF])) if ca < 256 and pa < 256 else None)
    needles = [n for n in needles if n]
    hits = {lbl: [] for lbl, _ in needles}
    for base, data in iter_chunks(h, regs, private_writable_only=False):
        for lbl, nd in needles:
            if len(hits[lbl]) >= 2000:
                continue
            i = data.find(nd)
            while i != -1 and len(hits[lbl]) < 2000:
                hits[lbl].append((base + i, base, data, i))
                i = data.find(nd, i + 1)
    for lbl, lst in hits.items():
        print(f"\n  {lbl}: {len(lst)} hit(s)" + (" (capped)" if len(lst) >= 2000 else ""))
        for addr, cbase, data, i in lst[:top]:
            print(f"   @0x{addr:016x}")
            print(hexdump(data[max(0, i - 32): i + 96], cbase + max(0, i - 32)))


# --------------------------------------------------------------------------- squad decode (FM27 build, 2026-11)
# Layout verified live against an IGE anchor (GK, CA 112 / PA 125): 45/45 attributes,
# 13/13 hidden, CA/PA, sharpness, fatigue, world rep, DOB, names. Two linked structures:
#
#  1. Squad record array (0x1E60-byte records, back-to-back). Located by a data signature:
#     constant table 03 01 04 02 05 03 06 04 at +0x4CC (and, since the 2026-11-19 patch, again at +0xA64),
#     repeated at +STRIDE. CA at +0x1230 (0 = empty slot),
#     person UID at +0x50. Contains a copy of positions/attributes but NOT PA/personality/name.
#  2. Database player object (one per player in the whole save; ~197k). Identified by its vtable,
#     game_plugin.dll + DB_VTABLE_RVA (ASLR-safe; only changes when the game is patched).
#     Joined to the squad record via UID (record +0x50 == object +0x150).
SQ_STRIDE = 0x2400  # was 0x1E60 before the 2026-11-19 patch
SQ_MARKER = bytes([3, 1, 4, 2, 5, 3, 6, 4])
SQ_MARKER_OFF = 0x4CC
SQ_MARKER2_OFF = 0xA64  # second marker copy added by the 2026-11-19 patch
SQ_UID_OFF = 0x50
SQ_CA_OFF = 0x1230  # was 0xC98

DB_VTABLE_RVA = 0x4C9A2E8  # was 0x4C40B88
DB = {
    "positions": 0x008,      # 15 x u8, 1..20 (index 0 = GK; other indices not yet labelled)
    "attributes": 0x017,     # 54 x u8, 1..100 (IGE value = round(raw / 5)), order = ATTR_ORDER
    "sharpness": 0x110,      # u16
    "fatigue": 0x112,        # s16
    "world_rep": 0x11A,      # u16
    "ca": 0x11C,             # u16
    "pa": 0x11E,             # u16
    "uid": 0x150,            # u32, matches squad record +0x50
    "first_name_ptr": 0x190, # -> ptr -> string object, UTF-8 text at +4
    "last_name_ptr": 0x198,
    "personality": 0x1B0,    # 8 x u8, 1..20, order = PERSONALITY_ORDER
    "dob_day": 0x1C8,        # u16 day-of-year (1-based)
    "dob_year": 0x1CA,       # u16
}
ATTR_ORDER = [
    "crossing", "dribbling", "finishing", "heading", "long_shots", "marking", "off_the_ball", "passing",
    "penalty_taking", "tackling", "vision", "handling", "aerial_reach", "command_of_area", "communication",
    "kicking", "throwing", "anticipation", "decisions", "one_on_ones", "positioning", "reflexes", "first_touch",
    "technique", "left_foot", "right_foot", "flair", "corners", "teamwork", "work_rate", "long_throws",
    "eccentricity", "rushing_out", "punching", "acceleration", "free_kick_taking", "strength", "stamina", "pace",
    "jumping_reach", "leadership", "dirtiness", "balance", "bravery", "consistency", "aggression", "agility",
    "important_matches", "injury_proneness", "versatility", "natural_fitness", "determination", "composure",
    "concentration",
]
PERSONALITY_ORDER = ["adaptability", "ambition", "loyalty", "pressure", "professionalism", "sportsmanship",
                     "temperament", "controversy"]
GROUPS = {
    "Technical": ["corners", "crossing", "dribbling", "finishing", "first_touch", "free_kick_taking", "heading",
                  "long_shots", "long_throws", "marking", "passing", "penalty_taking", "tackling", "technique"],
    "Mental": ["aggression", "anticipation", "bravery", "composure", "concentration", "decisions", "determination",
               "flair", "leadership", "off_the_ball", "positioning", "teamwork", "vision", "work_rate"],
    "Physical": ["acceleration", "agility", "balance", "jumping_reach", "natural_fitness", "pace", "stamina",
                 "strength"],
    "Goalkeeping": ["aerial_reach", "command_of_area", "communication", "eccentricity", "handling", "kicking",
                    "one_on_ones", "punching", "reflexes", "rushing_out", "throwing"],
    "Hidden": ["adaptability", "ambition", "controversy", "loyalty", "pressure", "professionalism",
               "sportsmanship", "temperament", "consistency", "dirtiness", "important_matches",
               "injury_proneness", "versatility"],
}
ABBR = {"free_kick_taking": "FK", "first_touch": "Fst", "long_shots": "LSh", "long_throws": "LTh",
        "penalty_taking": "Pen", "off_the_ball": "OtB", "jumping_reach": "Jum", "natural_fitness": "NFt",
        "aerial_reach": "Aer", "command_of_area": "Cmd", "one_on_ones": "1v1", "rushing_out": "Rsh",
        "important_matches": "ImM", "injury_proneness": "Inj", "professionalism": "Prf",
        "sportsmanship": "Spt", "temperament": "Tmp", "controversy": "Ctv", "adaptability": "Adp",
        "consistency": "Cns", "concentration": "Cnc", "composure": "Cmp", "communication": "Com"}


def locate_squad_array(h, regs):
    """Prefer the full squad array (most used slots) over match-day / partial arrays."""
    arrays = locate_squad_arrays(h, regs)
    for recs in arrays:
        print(f"  signature array @0x{recs[0]:x}: {len(recs)} slots, {used_slots(h, recs)} used")
    return max(arrays, key=lambda recs: (used_slots(h, recs), len(recs))) if arrays else []


def used_slots(h, recs) -> int:
    """Distinct players (UIDs with CA != 0); duplicate copies of a player don't count twice."""
    uids = set()
    for r in recs:
        d = rpm(h, r + SQ_CA_OFF, 2)[0]
        if d and len(d) == 2 and struct.unpack("<H", d)[0] != 0:
            u = rpm(h, r + SQ_UID_OFF, 4)[0]
            uids.add(struct.unpack("<I", u)[0] if u and len(u) == 4 else r)
    return len(uids)


def is_sq_record(h, m: int) -> bool:
    """Primary marker at m plus the second copy (rejects phantom arrays aligned on the second copy)."""
    return rpm(h, m, 8)[0] == SQ_MARKER and rpm(h, m - SQ_MARKER_OFF + SQ_MARKER2_OFF, 8)[0] == SQ_MARKER


def locate_squad_arrays(h, regs):
    arrays, claimed = [], set()
    for base, size, prot, typ in regs:
        if typ != MEM_PRIVATE or (prot & 0xFF) not in WRITABLE:
            continue
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            data, _, _ = rpm(h, base + off, n)
            if data:
                i = data.find(SQ_MARKER)
                while i != -1:
                    m = base + off + i
                    if m not in claimed and is_sq_record(h, m) and is_sq_record(h, m + SQ_STRIDE):
                        while is_sq_record(h, m - SQ_STRIDE):
                            m -= SQ_STRIDE
                        recs = []
                        while is_sq_record(h, m):
                            claimed.add(m)
                            recs.append(m - SQ_MARKER_OFF)
                            m += SQ_STRIDE
                        arrays.append(recs)
                    i = data.find(SQ_MARKER, i + 1)
            off += n
    return arrays


def find_db_objects(h, regs, vtable: int) -> dict:
    """uid -> object address for every object whose first qword is the player vtable."""
    out = {}
    for base, size, prot, typ in regs:
        if typ != MEM_PRIVATE:
            continue
        off = 0
        while off < size:
            n = min(CHUNK, size - off)
            data, _, _ = rpm(h, base + off, n)
            if data:
                qq = np.frombuffer(data[: len(data) // 8 * 8], "<u8")
                for j in np.flatnonzero(qq == vtable).tolist():
                    o = base + off + j * 8
                    uid_b = data[j * 8 + DB["uid"]: j * 8 + DB["uid"] + 4]
                    if len(uid_b) < 4:
                        uid_b = rpm(h, o + DB["uid"], 4)[0] or b"\0\0\0\0"
                    out.setdefault(struct.unpack("<I", uid_b)[0], o)
            off += n
    return out


def read_name(h, ptr_addr: int) -> str:
    """obj+0x190/0x198 -> name entry -> string object; UTF-8 text starts at string+4."""
    addr = ptr_addr
    for _ in range(2):
        d, _, _ = rpm(h, addr, 8)
        if not d:
            return "?"
        addr = struct.unpack("<Q", d)[0]
    s, _, _ = rpm(h, addr + 4, 64)
    return (s or b"?").split(b"\0")[0].decode("utf-8", "replace")


def decode_player(h, obj: int) -> dict:
    d, _, _ = rpm(h, obj, 0x1D0)
    u16 = lambda o: struct.unpack_from("<H", d, o)[0]
    attrs = d[DB["attributes"]: DB["attributes"] + 54]
    pers = d[DB["personality"]: DB["personality"] + 8]
    p = {"obj": obj,
         "name": f"{read_name(h, obj + DB['first_name_ptr'])} {read_name(h, obj + DB['last_name_ptr'])}",
         "ca": u16(DB["ca"]), "pa": u16(DB["pa"]), "sharpness": u16(DB["sharpness"]),
         "fatigue": struct.unpack_from("<h", d, DB["fatigue"])[0], "world_rep": u16(DB["world_rep"]),
         "dob": (u16(DB["dob_day"]), u16(DB["dob_year"])),
         "positions": list(d[DB["positions"]: DB["positions"] + 15]),
         "raw_attrs": list(attrs)}
    for name, raw in zip(ATTR_ORDER, attrs):
        p[name] = max(1, min(20, round(raw / 5)))
    for name, val in zip(PERSONALITY_ORDER, pers):
        p[name] = val
    return p


def squad_dump(h, regs, anchor_ca: int | None, anchor_age: int | None, game_year: int, game_day: int):
    import datetime as dt
    print()
    print("=" * 78)
    print("SQUAD DECODE")
    print("=" * 78)
    t0 = time.time()
    recs = locate_squad_array(h, regs)
    if not recs:
        print("  squad array signature not found")
        return
    import pymem
    pm = pymem.Pymem(PROCESS_NAME)
    gp = next((m for m in pm.list_modules() if m.name.lower() == "game_plugin.dll"), None)
    if gp is None:
        print("  game_plugin.dll not loaded")
        return
    uid2obj = find_db_objects(h, regs, gp.lpBaseOfDll + DB_VTABLE_RVA)
    print(f"  squad array: {len(recs)} slots @0x{recs[0]:x}   player DB objects: {len(uid2obj)}   "
          f"({time.time() - t0:.1f}s)")
    ref = dt.date(game_year, 1, 1) + dt.timedelta(days=game_day - 1)
    players = []
    seen_uids = set()
    for slot, r in enumerate(recs):
        d, _, _ = rpm(h, r, SQ_STRIDE)
        if not d or struct.unpack_from("<H", d, SQ_CA_OFF)[0] == 0:
            continue
        uid = struct.unpack_from("<I", d, SQ_UID_OFF)[0]
        if uid in seen_uids:  # duplicate copy of a player in a contiguous second block
            continue
        seen_uids.add(uid)
        obj = uid2obj.get(uid)
        if obj is None:
            print(f"  slot {slot}: uid {uid} has no DB object")
            continue
        p = decode_player(h, obj)
        p["slot"], p["uid"] = slot, uid
        p["squad_ca"] = struct.unpack_from("<H", d, SQ_CA_OFF)[0]
        dob = dt.date(p["dob"][1], 1, 1) + dt.timedelta(days=p["dob"][0] - 1)
        p["dob_date"] = dob
        p["age"] = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
        p["gk"] = p["positions"][0] >= 15
        players.append(p)
    agree = sum(p["ca"] == p["squad_ca"] for p in players)
    print(f"  decoded {len(players)} players; DB CA == squad-record CA for {agree}/{len(players)}")
    print(f"  ages computed against game date {ref.isoformat()}")

    print(f"\n  {'slot':>4} {'name':24} {'age':>3} {'DOB':10} {'CA':>3} {'PA':>3} {'pos':>4} "
          f"{'foot L/R':>8} {'sharp':>5} {'fatig':>5} {'wRep':>5}")
    for p in sorted(players, key=lambda x: -x["ca"]):
        mark = "  <== anchor" if p["ca"] == anchor_ca and (anchor_age is None or p["age"] == anchor_age) else ""
        pos = "GK" if p["gk"] else f"#{p['positions'].index(max(p['positions']))}"
        print(f"  {p['slot']:4d} {p['name'][:24]:24} {p['age']:3d} {p['dob_date'].isoformat():10} {p['ca']:3d} "
              f"{p['pa']:3d} {pos:>4} {p['left_foot']:3d}/{p['right_foot']:<4d} {p['sharpness']:5d} "
              f"{p['fatigue']:5d} {p['world_rep']:5d}{mark}")

    for group, names in GROUPS.items():
        hdr = " ".join(f"{ABBR.get(n, n[:3].title()):>3}" for n in names)
        print(f"\n  {group}\n  {'name':24} {hdr}")
        for p in sorted(players, key=lambda x: -x["ca"]):
            if group == "Goalkeeping" and not p["gk"]:
                continue
            print(f"  {p['name'][:24]:24} " + " ".join(f"{p[n]:3d}" for n in names))

    anchor = next((p for p in players if p["ca"] == anchor_ca and (anchor_age is None or p["age"] == anchor_age)),
                  None)
    other_gk = next((p for p in sorted(players, key=lambda x: -x["ca"]) if p["gk"] and p is not anchor), None)
    for p in (anchor, other_gk):
        if p is None:
            continue
        print(f"\n  --- {p['name']} (slot {p['slot']}, DB obj 0x{p['obj']:x}, uid {p['uid']}) ---")
        print(f"    positions[15] @+0x{DB['positions']:x}: {p['positions']}")
        print(f"    attrs raw @+0x{DB['attributes']:x}: {p['raw_attrs']}")
        for i, n in enumerate(ATTR_ORDER):
            if i % 6 == 0:
                print("    ", end="")
            print(f"[{i:2d}] {n:17s}{p['raw_attrs'][i]:3d}->{p[n]:2d}  ", end="\n" if i % 6 == 5 else "")
        print()
        print("    personality @+0x%x: %s" % (DB["personality"], {n: p[n] for n in PERSONALITY_ORDER}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--squad", action="store_true", help="locate + decode the squad via the player DB objects")
    ap.add_argument("--anchor-ca", type=int)
    ap.add_argument("--anchor-age", type=int)
    ap.add_argument("--game-year", type=int, default=2026, help="in-game current year (for age)")
    ap.add_argument("--game-day", type=int, default=322, help="in-game current day-of-year (for age)")
    ap.add_argument("--name")
    ap.add_argument("--ca", type=int)
    ap.add_argument("--pa", type=int)
    ap.add_argument("--top", type=int, default=8, help="candidates to print per category")
    ap.add_argument("--no-heuristic", action="store_true")
    args = ap.parse_args()

    pid = find_pid(PROCESS_NAME)
    if pid is None:
        print(f"{PROCESS_NAME} is not running.")
        return 1
    h, regs = access_check(pid)
    try:
        if args.squad:
            squad_dump(h, regs, args.anchor_ca, args.anchor_age, args.game_year, args.game_day)
        elif not args.no_heuristic:
            heuristic_scan(h, regs, args.top)
        if args.name or (args.ca is not None and args.pa is not None):
            targeted_scan(h, regs, args.name, args.ca, args.pa, args.top)
    finally:
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
