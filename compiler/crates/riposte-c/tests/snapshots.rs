//! Golden snapshot tests (SPEC M1) for diagnostics — parse errors and the M1 name/scope +
//! structure checks. Each case compiles a small broken (or clean) program and snapshots the
//! `diag.json` report, so regressions in error codes/spans/messages are caught.
//!
//! Update snapshots after an intentional change with: `cargo insta review`
//! (or `INSTA_UPDATE=always cargo test -p riposte-c`).

use riposte_c::compile;

fn report(src: &str) -> serde_json::Value {
    compile("bot.rpo", src).report
}

#[test]
fn clean_example_has_no_diagnostics() {
    let src = include_str!("../../../../examples/hazard_control.rpo");
    let r = report(src);
    assert_eq!(r["status"], "ok");
    assert_eq!(r["diagnostics"].as_array().unwrap().len(), 0);
}

#[test]
fn missing_otherwise_e040() {
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when likely(can_ko(my.active, opponent.active)) do use \"tackle\"\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn illegal_action_in_forced_switch_e041() {
    let src = "bot \"x\" format gen9randombattle\n\
               on forced_switch:\n\
               \x20 rule a: when exists bench b where resists(b, opponent.active.primary_type) do use \"tackle\"\n\
               \x20 otherwise: do switch_to best bench by hp_fraction(it)\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn unrevealed_information_e020() {
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when opponent.active.moves do use \"tackle\"\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn unbound_it_e023() {
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when it.hp_fraction < 0.5 do use \"tackle\"\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn unknown_predicate_e022() {
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when likely(mega_ko(my.active, opponent.active)) do use \"tackle\"\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn unresolved_tribool_e030() {
    // can_ko is tribool; using it in `when` without a resolver is E030.
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when can_ko(my.active, opponent.active) do use strongest_move against opponent.active\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn redundant_resolver_e031() {
    // resists returns bool (a fact); wrapping it in likely(...) is E031.
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when likely(resists(my.active, opponent.active.primary_type)) do use strongest_move against opponent.active\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn categorical_effectiveness_e032() {
    // effectiveness is categorical; comparing it with a number is E032.
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               \x20 rule a: when effectiveness(opponent.active.primary_type, my.active) > 2 do use strongest_move against opponent.active\n\
               \x20 otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}

#[test]
fn parse_recovery_reports_multiple_e012() {
    let src = "bot \"x\" format gen9randombattle\n\
               on turn:\n\
               rule a: when @@@ do use \"tackle\"\n\
               rule b: when likely(can_ko(my.active, opponent.active)) do %%%\n\
               otherwise: do use strongest_move against opponent.active\n";
    insta::assert_json_snapshot!(report(src));
}
