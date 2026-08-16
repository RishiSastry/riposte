Feature: Hyper offense
  Write a Riposte bot that plays hyper-offense: terastallize early to secure a KO when one is
  likely and tera is available, otherwise press the strongest attack whenever you can KO, and
  pivot to a bench mon that can likely KO the opponent when you are outsped.

  Scenario: Compiles, is competitive, and respects the quirks
    Given the steering condition "mcp-repair"
    When the agent writes a Riposte bot
    Then the program compiles without errors
    And it wins >= 60% of 50 battles vs random
    And it makes <= 0 quirk violations
