"""Aggregate cached judgments into PanelMetrics + the printed report."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from quorumcal.goldset import GoldTask, read_goldset
from quorumcal.judges import JudgeSpec
from quorumcal.metrics import bootstrap_n_eff, panel_metrics
from quorumcal.panel import cache_key, load_panels


def collect_rows(tasks: list[GoldTask], specs: list[JudgeSpec],
                 cache_dir: Path) -> tuple[list[tuple[str, list[str]]], float]:
    """Rows for panel_metrics plus summed cost. Missing cells are a hard error."""
    rows, cost = [], 0.0
    for t in tasks:
        verdicts = []
        for s in specs:
            cell = Path(cache_dir) / f"{cache_key(s, t.task_id)}.json"
            if not cell.exists():
                raise RuntimeError(
                    f"missing judgment {s.judge_id}×{t.task_id} — run "
                    "`panel run` to completion before reporting")
            try:
                rec = json.loads(cell.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"corrupt cache cell {cell} — re-run `panel run` to "
                    "heal it before reporting") from exc
            verdicts.append(rec["verdict"])
            cost += rec.get("cost_usd") or 0.0
        rows.append((t.label, verdicts))
    return rows, cost


def build_report(goldset_path, panels_path, cache_root,
                 delta: float = 0.1, epsilon: float = 0.1) -> dict:
    tasks = read_goldset(goldset_path)
    panels = load_panels(panels_path)
    diff_lines = {"valid": [], "invalid": []}
    for t in tasks:
        diff_lines[t.label].append(len(t.diff.splitlines()))
    out_panels = {}
    for name, specs in panels.items():
        # flat cache dir, not cache_root/name: cache_key already fully
        # qualifies judge|model|lens|task, so a per-panel subdir would
        # duplicate cells (and re-spend quota) for judges shared across
        # panels.
        rows, cost = collect_rows(tasks, specs, Path(cache_root))
        m = panel_metrics(rows, delta=delta, epsilon=epsilon)
        m_dict = dataclasses.asdict(m)
        wrong_vectors = m_dict.pop("wrong_vectors")
        n_eff_ci = bootstrap_n_eff(wrong_vectors) if len(wrong_vectors) >= 2 \
            else (m.n_effective, m.n_effective)
        out_panels[name] = {**m_dict, "cost_usd": cost,
                            "n_eff_ci": list(n_eff_ci),
                            "mean_diff_lines": {
                                lb: (sum(v) / len(v) if v else 0.0)
                                for lb, v in diff_lines.items()}}
    n_inv = sum(1 for t in tasks if t.label == "invalid")
    return {"panels": out_panels,
            "goldset": {"path": str(goldset_path), "n_tasks": len(tasks),
                        "n_invalid": n_inv, "n_valid": len(tasks) - n_inv},
            "delta": delta, "epsilon": epsilon}


def format_table(report: dict) -> str:
    hdr = (f"{'panel':<22} {'N_eff':>18} {'rho':>6} {'e_d':>5} {'u_e':>5} "
           f"{'q window':>9} {'err%':>5} {'cost$':>7}")
    lines = [hdr, "-" * len(hdr)]
    for name, p in report["panels"].items():
        q = f"[{p['q_min']},{p['q_max']}]" if p["feasible"] else "INFEAS"
        err = 100.0 * p["n_tasks_error"] / p["n_tasks_total"]
        guard = " GUARD-TRIPPED" if p["error_guard_tripped"] else ""
        lo, hi = p["n_eff_ci"]
        n_eff_str = f"{p['n_effective']:.2f} [{lo:.2f},{hi:.2f}]"
        lines.append(f"{name:<22} {n_eff_str:>18} {p['rho_bar']:>6.2f} "
                     f"{p['e_delta']:>5.1f} {p['u_epsilon']:>5.1f} {q:>9} "
                     f"{err:>4.1f}% {p['cost_usd']:>7.2f}{guard}")
    return "\n".join(lines)
