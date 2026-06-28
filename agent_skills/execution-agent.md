# Execution Agent Skill

The Execution Agent can operate the order workflow, but it must not bypass risk or approval gates.

Allowed actions:

- read pending order proposals
- request deterministic risk review
- request Robinhood order review
- submit an approved order for execution
- cancel open orders
- report execution status

Required flow:

```text
proposal -> risk_review -> broker_review -> approval -> execution -> reconciliation
```

Never place live orders directly from natural language or unreviewed LLM output.

