"""Step-definition registry (the extensibility surface).

Domain packages register step definitions by regex pattern; the runner matches a step's text
against them (keyword-agnostic, like Cucumber — a step defined with `@then` can still satisfy
a `Given`/`And`). Capture groups are passed to the handler after the `World`.

A process-global `registry` plus `given`/`when`/`then`/`step` decorators are exported so a
domain step module can simply:

    from evalkit import then

    @then(r'it wins >= (?P<pct>[\\d.]+)% of (?P<n>\\d+) battles vs (?P<baseline>\\w+)')
    def _(world, pct, n, baseline): ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass
class StepDef:
    pattern: re.Pattern
    func: Callable


class NoMatch(Exception):
    pass


class AmbiguousStep(Exception):
    pass


class StepRegistry:
    def __init__(self) -> None:
        self._defs: list[StepDef] = []

    def add(self, pattern: str, func: Callable) -> None:
        self._defs.append(StepDef(re.compile(pattern), func))

    def _decorator(self, pattern: str) -> Callable:
        def deco(func: Callable) -> Callable:
            self.add(pattern, func)
            return func

        return deco

    # Keyword-flavored decorators (all equivalent — matching ignores keyword).
    given = when = then = step = _decorator

    def resolve(self, text: str) -> tuple[Callable, tuple, dict]:
        """Find the single step definition matching `text`. Returns (func, args, kwargs)."""
        matches = []
        for d in self._defs:
            m = d.pattern.fullmatch(text) or d.pattern.match(text)
            if m:
                matches.append((d, m))
        if not matches:
            raise NoMatch(text)
        if len(matches) > 1:
            pats = ", ".join(repr(d.pattern.pattern) for d, _ in matches)
            raise AmbiguousStep(f"{text!r} matches multiple step defs: {pats}")
        d, m = matches[0]
        if m.groupdict():
            return d.func, (), m.groupdict()
        return d.func, m.groups(), {}


# process-global registry + convenience decorators
registry = StepRegistry()
given = registry.given
when = registry.when
then = registry.then
step = registry.step
