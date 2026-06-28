# Risk Agent Skill

The Risk Agent evaluates whether an order proposal is allowed under deterministic portfolio rules.

Checks:

- valid symbol and side
- max notional per order
- max position concentration
- max daily order count
- buying power availability
- market tradability
- duplicate proposal detection

The Risk Agent may explain a result, but the actual allow/block decision must come from deterministic policy code.

