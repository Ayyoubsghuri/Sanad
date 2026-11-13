"""Which device the local models (embedder, reranker) run on, and a check you can run:  py -m legalrag.device"""
from __future__ import annotations

import os
import sys


def pick_device(preferred: str | None = None) -> str:
    """'cuda' when torch can see an NVIDIA GPU, 'mps' on Apple silicon, else 'cpu'.  LEGALRAG_DEVICE=cpu|cuda|cuda:1 overrides."""
    want = (preferred or os.environ.get("LEGALRAG_DEVICE") or "auto").lower()
    if want not in ("auto", ""):
        return want
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def describe() -> str:
    try:
        import torch
    except Exception as e:  # noqa: BLE001
        return f"torch is not importable: {e}"
    v = torch.__version__
    if torch.cuda.is_available():
        return f"GPU OK: {torch.cuda.get_device_name(0)} (torch {v}, CUDA {torch.version.cuda})"
    if "+cpu" in v or torch.version.cuda is None:
        return (f"torch {v} is the CPU-ONLY build, so it cannot use your GPU.\n"
                "  Fix (NVIDIA GPU): in the (env) run\n"
                "      pip uninstall -y torch\n"
                "      pip install torch --index-url https://download.pytorch.org/whl/cu124\n"
                "  then run this check again.  (nvidia-smi must work in cmd; if it does not, install the NVIDIA driver first.)")
    return f"torch {v} has CUDA {torch.version.cuda} but no GPU is visible: check the NVIDIA driver (nvidia-smi) and that no other program is using all the GPU memory."


def main() -> int:
    print(describe())
    print("device the app will use:", pick_device())
    return 0


if __name__ == "__main__":
    sys.exit(main())
