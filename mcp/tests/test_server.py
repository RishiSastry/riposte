"""Tests for the riposte-mcp tool implementations and server wiring."""

import asyncio

from riposte_mcp import server as s


def test_overview_and_topics():
    assert s.language_overview().startswith("# Riposte")
    topics = s.list_topics()
    assert "types_and_estimates" in topics
    assert "quirks" in topics
    assert s.get_topic("quirks").startswith("# Deliberate quirks")
    assert "No topic" in s.get_topic("does_not_exist")


def test_predicate_reference():
    ref = s.predicate_reference("can_ko")
    assert "can_ko(mon, mon) -> tribool" in ref
    assert "Example:" in ref
    assert "outspeeds" in s.predicate_reference("outspeeds")  # infix
    assert "No predicate" in s.predicate_reference("nope")


def test_explain_error_normalizes_code():
    assert s.explain_error("030").startswith("# E030")
    assert s.explain_error("e030").startswith("# E030")
    assert s.explain_error("E030").startswith("# E030")
    assert "No explanation" in s.explain_error("E999")


def test_check_program_valid_and_broken():
    valid = open("examples/hyper_offense.rpo").read()
    r = s.check_program(valid)
    assert r["status"] == "ok"
    assert r["diagnostics"] == []

    broken = (
        'bot "x" format gen9randombattle\n'
        "on turn:\n"
        " rule a: when can_ko(my.active, opponent.active) do use strongest_move against opponent.active\n"
        " otherwise: do use strongest_move against opponent.active\n"
    )
    rb = s.check_program(broken)
    assert rb["status"] == "error"
    assert rb["diagnostics"][0]["code"] == "E030"


def test_server_registers_all_tools():
    server = s.build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "language_overview",
        "list_topics",
        "get_topic",
        "predicate_reference",
        "explain_error",
        "check_program",
    }
