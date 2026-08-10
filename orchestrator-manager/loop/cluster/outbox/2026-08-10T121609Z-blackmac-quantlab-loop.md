## The research loop is starting

| agent | model | role | writes code |
|---|---|---|---|
| `blackmac-quantlab-loop` | mechanical (no language model) | executor | no |
| `blackmac-quantlab-proposer-opus5` | claude-opus-5 | proposer | **yes** |
| `blackmac-quantlab-critic-codex` | codex-cli (local) | critic | no |
| `blackmac-quantlab-critic-glm52` | glm-5.2 | critic | no |

Only the proposer may author repository code, and only in a reviewed change with a human present. The loop writes data -- rule trees and ledger records -- and never source. Critics return opinions, which are evidence and never instructions.