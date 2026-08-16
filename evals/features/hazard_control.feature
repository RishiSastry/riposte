Feature: Hazard control
  Write a Riposte bot that keeps entry hazards up — set Stealth Rock when your active mon
  knows it and the opponent's side doesn't already have it — pivots out of bad matchups when
  the opponent is faster and likely to KO you, and presses the attack when you have a clear KO.

  Scenario: Compiles, is competitive, and respects the quirks
    Given the steering condition "mcp-repair"
    And baselines random, maxbp, heuristics
    When the agent writes a Riposte bot
    Then the program compiles without errors
    And it wins >= 60% of 50 battles vs random
    And it makes <= 0 quirk violations
