"""legalrag-eval: run the golden set against a pack and exit non-zero when a gate fails (use in CI)."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ..config import Settings
from ..state import build_context
from .golden import run_golden


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="legalrag-eval")
    ap.add_argument("--pack", type=Path, required=True)
    ap.add_argument("--public-key-hex")
    ap.add_argument("--allow-unsigned", action="store_true")
    a = ap.parse_args(argv)
    tmp = Path(tempfile.mkdtemp())
    ctx = build_context(Settings(data_dir=tmp, lawpack_path=a.pack, lawpack_public_key_hex=a.public_key_hex, allow_unsigned_pack=a.allow_unsigned))
    if not ctx.pack_usable():
        print(json.dumps({"error": ctx.pack_error}))
        return 2
    rep = run_golden(ctx)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0 if rep["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
