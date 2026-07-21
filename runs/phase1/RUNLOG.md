# Phase 1 run log — started 2026-07-20
Suites verified green: rag-guard 88 passed (0.07s); bow 1329 passed + 1 skipped (18.88s)
Scope: rag-guard = rag_guard/retriever.py, rag_guard/guard.py, rag_guard/pipeline.py
Scope: bow = bow/routing.py (single file — 19s/mutation-run budget cap)

## Pre-run events
- Live smoke PASSED: 2 synthetic tasks x 1 real sonnet judge — seeded bug → reject, clean diff → endorse (smoke-cache/ committed as receipt)
- Gold-set build failed twice, root-caused and fixed both times:
  1. ec8bf82: write_scope needed also_copy=[top package] (mutmut sandbox lacked sibling modules)
  2. 72980d6: real path now delegates to crucible.scope.detect — hazard tests importing local packages (e.g. rag-guard tests/test_hook.py → bin) get --ignore'd, exactly crucible's own recipe
- Build attempt 3 launched (fresh /tmp/qc-work)

## Spot-check gate (Step 4) — TRIPPED then cleared
- Round 1: CRITICAL leak — mutmut status header ('# <id>: killed') present in every invalid diff. Fixed d48dfba (strip #-lines); gold sets re-normalized in place.
- Round 2: two residual cues: (a) a/-b/ path prefixes discriminated classes — fixed 3d8123a + re-normalized; (b) mutmut XX-string mutants (XXqueryXX) trivially machine-identifiable — DROPPED from set (12 rag-guard, 3 bow).
- Final set: 59 tasks (45 invalid / 14 valid), no residual mechanical cues. Known limits: valid side sparse (few commits touch scoped files); diff-size confound (invalid ~10 lines, valid ~46) — reported in report.json.

## RESULT — 2026-07-20
472 cells (59 tasks x 8 unique judge-cells), all healed, 0% errors. 16 cells (3.4%) were
judged under a v2 prompt adding an explicit no-tools line (tool-seeking judges ended turns
without verdicts; cache keys carry no prompt hash — flagged for the writeup).

  identical-sonnet     N_eff 1.15 [1.00,3.00]  rho 0.80  e_d 0.0  u_e 2.0  q[1,1]
  diverse-lens-sonnet  N_eff 1.93 [1.69,3.00]  rho 0.28  e_d 0.0  u_e 1.0  q[1,2]
  mixed-tier           N_eff 1.72 [1.58,3.00]  rho 0.37  e_d 0.0  u_e 2.0  q[1,1]

GATE (pre-committed: <=2.0 proceed / >=2.5 stop): identical-sonnet N_eff = 1.15 -> GATE PASSED.
Collapse confirmed: three identical sonnet judges behave like ~1.15 independent votes; their
rare mistakes are almost perfectly shared (rho 0.80). Prompt diversity alone (same model,
three lenses) nearly doubles effective independence (1.93); tier diversity buys less (1.72).
Individually the judges are strong: 90th-pct false-endorsement count is 0 in every panel.
Caveats for the writeup: bootstrap CI uppers reach 3.0 (error events are rare at n=59 —
grow the set for power); valid side sparse (14); diff-size confound reported in report.json.
Phase 2 (Codex + Grok lineages) is now justified per the gate. NOT started in this plan.
