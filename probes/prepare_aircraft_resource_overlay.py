"""Prepare or remove a reversible loose-file C17 compatibility overlay.

The Thai client metadata references two archive paths that are absent from its
file index: the C17 skeleton under Avatars/Skin and a fourth mesh LOD.  This
tool copies original, locally installed records to those missing paths.  It
never edits SFC/VFS archives and refuses to overwrite an existing loose file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT.parent / "32838"
INDEX = ROOT / "extracted/thai_vfs0/ALL_FILES.DAT"
SFC_LIST = ROOT / "extracted/thai_vfs0/ALL_SFC.DAT"
RECEIPT = ROOT / "private/aircraft-resource-overlay.json"
sys.path.insert(0, str(ROOT / "python-libs"))
import lz4.block

LIMIT = 16 * 1024 * 1024
HASH_SEED = 0x2E31F418D34D0915
SOURCES = {
    "Data/Avatars/Skin/Vehicle/EU_c17_001_Skel.qss": {
        "archive_path": r"\DATA\ACTORS\VEHICLE\EU_C17_001\EU_C17_001_SKEL.QSS",
        "key": "a46227e0c7ebc6d3",
        "decoded_size": 448,
        "archive_index": 8,
        "record_offset": 179788,
    },
    "Data/Avatars/Skin/Vehicle/EU_c17_001_LOD3.qsg": {
        "archive_path": r"\DATA\AVATARS\SKIN\VEHICLE\EU_C17_001_LOD2.QSG",
        "key": "3db6ee885fb7fb84",
        "decoded_size": 241079,
        "archive_index": 45,
        "record_offset": 67525738,
    },
}


def archive_key(name: str) -> str:
    value = HASH_SEED
    for byte in name.replace("/", "\\").upper().encode("ascii"):
        value = (value * 67 + byte) & 0xFFFFFFFFFFFFFFFF
    return value.to_bytes(8, "little").hex()


def load_index() -> dict[str, tuple[int, int, int, int]]:
    blob = INDEX.read_bytes()
    if len(blob) % 24:
        raise ValueError("ALL_FILES.DAT is not a sequence of 24-byte records")
    return {
        blob[offset:offset + 8].hex(): struct.unpack_from("<4I", blob, offset + 8)
        for offset in range(0, len(blob), 24)
    }


def archive_paths() -> list[Path]:
    lines = SFC_LIST.read_text(encoding="ascii").splitlines()
    return [CLIENT / line.strip().replace("\\", "/") for line in lines if line.strip()]


def extract_original(spec: dict, index: dict, archives: list[Path]) -> bytes:
    if archive_key(spec["archive_path"]) != spec["key"]:
        raise ValueError("Empirical archive-key mapping differs from the pinned key")
    indexed = index.get(spec["key"])
    expected = (spec["decoded_size"], spec["archive_index"],
                spec["record_offset"], indexed[3] if indexed else 0)
    if indexed is None or indexed[:3] != expected[:3]:
        raise ValueError(f"Pinned file index differs for {spec['key']}: {indexed}")
    if spec["decoded_size"] > LIMIT:
        raise ValueError("Decoded resource exceeds safety limit")
    archive = archives[spec["archive_index"]]
    if archive.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("Source archive exceeds safety limit")
    with archive.open("rb") as stream:
        # ALL_FILES points at the compressed payload, immediately after the
        # 8-byte key and 4-byte packed-size header.
        stream.seek(spec["record_offset"] - 12)
        header = stream.read(12)
        if len(header) != 12 or header[:8].hex() != spec["key"]:
            raise ValueError(f"SFC record key mismatch in {archive.name}")
        packed = struct.unpack_from("<I", header, 8)[0]
        if packed > LIMIT:
            raise ValueError("Packed resource exceeds safety limit")
        payload = stream.read(packed)
        trailer = stream.read(4)
    if len(payload) != packed or len(trailer) != 4:
        raise ValueError("Truncated SFC record")
    decoded_size = struct.unpack("<I", trailer)[0]
    if decoded_size != spec["decoded_size"]:
        raise ValueError("SFC decoded size differs from file index")
    decoded = lz4.block.decompress(payload, uncompressed_size=decoded_size)
    if len(decoded) != decoded_size:
        raise ValueError("Decoded resource length differs")
    return decoded


def safe_target(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise ValueError("Overlay target escapes client root")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--install", action="store_true")
    action.add_argument("--remove", action="store_true")
    parser.add_argument("--client-root", type=Path, default=CLIENT,
                        help="Alternate root for a safe staging/rollback test")
    args = parser.parse_args()
    client_root = args.client_root.resolve()

    if args.remove:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        if Path(receipt["client_root"]).resolve() != client_root:
            raise ValueError("Receipt belongs to a different client root")
        removed = []
        for row in receipt["files"]:
            target = safe_target(client_root, row["relative_path"])
            if not target.exists():
                continue
            if hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError(f"Refusing to remove modified file: {target}")
            target.unlink()
            removed.append(str(target))
        print(json.dumps({"removed": removed, "archives_modified": False}, indent=2))
        return

    index = load_index()
    archives = archive_paths()
    rows = []
    for relative, spec in SOURCES.items():
        data = extract_original(spec, index, archives)
        target = safe_target(client_root, relative)
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rows.append({"relative_path": relative, "sha256": hashlib.sha256(data).hexdigest(),
                     "bytes": len(data), "source_key": spec["key"],
                     "source_archive_path": spec["archive_path"]})
    receipt = {"client_root": str(client_root), "files": rows,
               "archives_modified": False,
               "scope": "Experimental loose-file compatibility overlay; not a rendering verification"}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
