"""Unit tests for the evalkit engine — parser, registry, scenario execution, reporting.
Pure: no agent, no compiler, no battles."""

import tempfile
from pathlib import Path

from evalkit import RunResult, Status, StubDriver, World, report
from evalkit.gherkin_runner import run_feature
from evalkit.registry import StepRegistry


def _feature(text: str) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".feature", delete=False)
    f.write(text)
    f.close()
    return f.name


def _registry() -> StepRegistry:
    reg = StepRegistry()

    @reg.given(r"a value (?P<v>\d+)")
    def _set(world, v):
        world.data["v"] = int(v)

    @reg.then(r"it equals (?P<v>\d+)")
    def _eq(world, v):
        assert world.data["v"] == int(v), f"{world.data['v']} != {v}"

    @reg.when(r"the agent writes")
    async def _writes(world):
        world.artifact = await world.driver.write_program(world.brief, world.condition)

    return reg


def test_pass_fail_and_skip():
    reg = _registry()
    src = (
        "Feature: F\n  the brief\n"
        "  Scenario: good\n    Given a value 3\n    Then it equals 3\n"
        "  Scenario: bad\n    Given a value 3\n    Then it equals 4\n    Then it equals 3\n"
    )
    results = run_feature(_feature(src), reg, lambda: World(driver=StubDriver()))
    by_name = {r.name: r for r in results}
    assert by_name["good"].passed
    assert not by_name["bad"].passed
    # the step after the failing one is skipped
    assert by_name["bad"].steps[-1].status == Status.SKIPPED
    assert by_name["bad"].steps[1].status == Status.FAILED


def test_undefined_step():
    reg = _registry()
    src = "Feature: F\n  b\n  Scenario: s\n    Given a value 1\n    Then something undefined\n"
    results = run_feature(_feature(src), reg, lambda: World(driver=StubDriver()))
    assert results[0].steps[1].status == Status.UNDEFINED
    assert not results[0].passed


def test_when_calls_driver_with_feature_brief():
    reg = _registry()
    src = "Feature: F\n  discover the language\n  Scenario: s\n    When the agent writes\n"
    driver = StubDriver(default='bot "x" format gen9randombattle')
    results = run_feature(_feature(src), reg, lambda: World(driver=driver))
    assert results[0].passed
    # the brief handed to the driver is the Feature description
    # (re-run capturing the world isn't exposed, so assert via a recording driver)


def test_recording_driver_receives_brief():
    reg = _registry()

    class Recorder:
        seen = None

        async def write_program(self, brief, condition):
            Recorder.seen = brief
            return await StubDriver(default="src").write_program(brief, condition)

    src = "Feature: F\n  keep hazards up\n  Scenario: s\n    When the agent writes\n"
    run_feature(_feature(src), reg, lambda: World(driver=Recorder()))
    assert Recorder.seen == "keep hazards up"


def test_reporting_and_run_result():
    reg = _registry()
    src = (
        "Feature: F\n  b\n"
        "  Scenario: good\n    Given a value 5\n    Then it equals 5\n"
        "  Scenario: bad\n    Given a value 5\n    Then it equals 6\n"
    )
    results = run_feature(_feature(src), reg, lambda: World(driver=StubDriver()))
    run = RunResult(scenarios=results)
    assert run.total == 2 and run.passed == 1 and run.failed == 1 and not run.ok
    text = report.console(run)
    assert "1/2 scenarios passed" in text and "FAILED" in text
    js = report.to_json(run)
    assert js["passed"] == 1 and js["scenarios"][1]["status"] == "failed"
