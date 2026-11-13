"""Calculator plumbing. Every tool is a pure function of (law pack, inputs): dated rate rows in, result + formula +
legal basis + the exact table rows used out. Tools fail closed (CalcError) instead of guessing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CalcError(Exception):
    """status: 'needs_input' (ask the user) or 'abstain' (cannot compute from the pack)."""

    def __init__(self, status: str, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.status, self.message, self.missing = status, message, missing or []


@dataclass
class CalcResult:
    tool: str
    inputs: dict[str, Any]
    result: dict[str, Any]
    formula: str
    legal_basis: list[str]
    table_rows: list[dict[str, Any]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified: bool = False
    as_of: str | None = None
    articles: list[dict[str, Any]] = field(default_factory=list)  # the law behind the result, quoted from the pack (calc/basis.py)

    def text(self) -> str:
        """Canonical rendering: the ONLY source of numbers the model may quote for this tool call."""
        lines = [f"{self.tool}", f"formula: {self.formula}", *self.steps, "result: " + "; ".join(f"{k}={_fmt(v)}" for k, v in self.result.items())]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool, "inputs": self.inputs, "result": self.result, "formula": self.formula, "legal_basis": self.legal_basis,
            "table_rows": self.table_rows, "steps": self.steps, "warnings": self.warnings,
            "verification": "verified_against_official_examples" if self.verified else "unverified", "as_of": self.as_of, "text": self.text(),
            "articles": self.articles,
        }


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return str(v)


def money(x: float) -> float:
    return round(x + 1e-9, 2)
