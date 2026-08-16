"""Riposte policy IR (policy.json) — the compiler↔runtime contract.

The Rust compiler *emits* this; the Python runtime *interprets* it. It is versioned and
pydantic-validated on load. Conditions are a small expression tree of fully-resolved nodes
(no DSL string re-parsing at runtime, per SPEC §5). Epistemic typing (fact/est/tribool) is
checked at compile time; the runtime only needs structure, so nodes carry no type tags in
v0.1 — resolvers (`likely`/`worst_case`/`best_case`) are explicit nodes instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

IR_VERSION = "0.1"

# ─────────────────────────── expression nodes ───────────────────────────
# Each node has a distinct `kind` discriminator.


class Ref(BaseModel):
    """Accessor into the state surface (SPEC §4.3). `path` is a resolved token list, not a
    string to re-parse: e.g. ["my","active","hp_fraction"], ["opponent","active"] (the mon
    itself, as a predicate arg / action target), ["it","hp_fraction"] (bound by exists/best).
    """

    kind: Literal["ref"] = "ref"
    path: list[str]


class Lit(BaseModel):
    kind: Literal["lit"] = "lit"
    type: Literal["frac", "num", "bool", "type", "status", "move", "eff", "str"]
    value: object


class Pred(BaseModel):
    """Predicate call, e.g. can_ko(my.active, opponent.active). May yield bool or tribool;
    which one is a compile-time fact, so the runtime just evaluates."""

    kind: Literal["pred"] = "pred"
    name: str
    args: list["Expr"] = Field(default_factory=list)


class Outspeeds(BaseModel):
    """`a outspeeds b` infix predicate → tribool."""

    kind: Literal["outspeeds"] = "outspeeds"
    left: "Expr"
    right: "Expr"


class Resolve(BaseModel):
    """Mandatory tribool→bool resolver (SPEC §4.2, Q4)."""

    kind: Literal["resolve"] = "resolve"
    op: Literal["likely", "worst_case", "best_case"]
    arg: "Expr"


class Compare(BaseModel):
    kind: Literal["compare"] = "compare"
    op: Literal["=", "!=", "<", "<=", ">", ">="]
    left: "Expr"
    right: "Expr"


class EffCompare(BaseModel):
    """Categorical effectiveness comparison (SPEC Q2): `effectiveness(m,d) at_least super`."""

    kind: Literal["eff_cmp"] = "eff_cmp"
    op: Literal["at_least", "at_most", "="]
    left: "Expr"  # eff-valued
    right: str  # eff category: immune|strongly_resisted|resisted|neutral|super|overwhelming


class BoolOp(BaseModel):
    kind: Literal["and", "or"]
    operands: list["Expr"]


class Not(BaseModel):
    kind: Literal["not"] = "not"
    operand: "Expr"


class Exists(BaseModel):
    """`exists bench b where <body over it>` → bool."""

    kind: Literal["exists"] = "exists"
    domain: Literal["bench"] = "bench"
    var: str
    body: "Expr"


Expr = Annotated[
    Union[Ref, Lit, Pred, Outspeeds, Resolve, Compare, EffCompare, BoolOp, Not, Exists],
    Field(discriminator="kind"),
]

# ─────────────────────────────── actions ────────────────────────────────


class UseMove(BaseModel):
    kind: Literal["use_move"] = "use_move"
    move_id: str
    tera: bool = False


class UseStrongest(BaseModel):
    kind: Literal["use_strongest"] = "use_strongest"
    target: Ref
    tera: bool = False


class SwitchBest(BaseModel):
    kind: Literal["switch_best"] = "switch_best"
    domain: Literal["bench"] = "bench"
    by: "Expr"
    order: Literal["max", "min"] = "max"


Action = Annotated[Union[UseMove, UseStrongest, SwitchBest], Field(discriminator="kind")]

# ──────────────────────────── rules / policy ────────────────────────────


class Rule(BaseModel):
    rule_name: str
    when: Optional["Expr"] = None  # None ⇒ the mandatory `otherwise` rule
    action: Action


class Header(BaseModel):
    name: str
    format: str
    source_hash: Optional[str] = None
    compiler_version: Optional[str] = None


class Policy(BaseModel):
    ir_version: str = IR_VERSION
    header: Header
    on_turn: list[Rule]
    on_forced_switch: list[Rule]

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        data = json.loads(Path(path).read_text())
        return cls.model_validate(data)


# resolve forward references
for _m in (Pred, Outspeeds, Resolve, Compare, EffCompare, BoolOp, Not, Exists, SwitchBest, Rule):
    _m.model_rebuild()
