"""Guard: the runtime implements exactly the predicates the compiler type-checks.

predicates.toml is the single source of truth (SPEC §4.4). This test fails if the toml and
the runtime dispatch drift — e.g. a predicate added to the toml (and thus accepted by the
compiler) that the interpreter would crash on at runtime.
"""

import tomllib
from pathlib import Path

from riposte_rt.interp import SUPPORTED_PREDICATES

TOML = Path(__file__).resolve().parents[2] / "predicates.toml"


def test_runtime_supports_every_toml_predicate():
    data = tomllib.loads(TOML.read_text())
    toml_names = set(data["predicates"])
    assert toml_names == set(SUPPORTED_PREDICATES), (
        f"drift between predicates.toml and runtime:\n"
        f"  only in toml:    {toml_names - set(SUPPORTED_PREDICATES)}\n"
        f"  only in runtime: {set(SUPPORTED_PREDICATES) - toml_names}"
    )
