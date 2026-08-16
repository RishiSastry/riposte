"""Reporters: human console output, plus JUnit XML and JSON for CI ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from .result import RunResult, Status

_MARK = {
    Status.PASSED: "✓",
    Status.FAILED: "✗",
    Status.ERROR: "!",
    Status.UNDEFINED: "?",
    Status.SKIPPED: "-",
}


def console(run: RunResult) -> str:
    lines: list[str] = []
    for sc in run.scenarios:
        head = "✓" if sc.passed else "✗"
        lines.append(f"{head} {sc.feature} :: {sc.name}")
        for st in sc.steps:
            mark = _MARK.get(st.status, "?")
            lines.append(f"    {mark} {st.keyword.strip()} {st.text}")
            if st.message and st.status in (Status.FAILED, Status.ERROR, Status.UNDEFINED):
                lines.append(f"        → {st.message}")
    lines.append("")
    lines.append(f"{run.passed}/{run.total} scenarios passed" + ("" if run.ok else "  FAILED"))
    return "\n".join(lines)


def to_json(run: RunResult) -> dict:
    return {
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "ok": run.ok,
        "scenarios": [
            {
                "feature": sc.feature,
                "name": sc.name,
                "status": sc.status.value,
                "tags": sc.tags,
                "steps": [
                    {
                        "keyword": st.keyword.strip(),
                        "text": st.text,
                        "status": st.status.value,
                        "message": st.message,
                        "duration_s": st.duration_s,
                    }
                    for st in sc.steps
                ],
            }
            for sc in run.scenarios
        ],
    }


def write_json(run: RunResult, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_json(run), indent=2))


def write_junit(run: RunResult, path: str | Path) -> None:
    suite = ET.Element(
        "testsuite",
        name="evalkit",
        tests=str(run.total),
        failures=str(run.failed),
    )
    for sc in run.scenarios:
        case = ET.SubElement(suite, "testcase", classname=sc.feature, name=sc.name)
        if not sc.passed:
            bad = next(
                (s for s in sc.steps if s.status in (Status.FAILED, Status.ERROR, Status.UNDEFINED)),
                None,
            )
            fail = ET.SubElement(case, "failure", message=(bad.message if bad else "failed"))
            fail.text = "\n".join(f"{s.keyword}{s.text} [{s.status.value}]" for s in sc.steps)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
