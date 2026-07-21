"""quorumcal CLI. goldset build must run under the crucible venv python:
~/ai-agentic-code-testing/.venv/bin/python -m quorumcal.cli goldset build ..."""
from __future__ import annotations

import argparse
from pathlib import Path


def _cmd_goldset_build(args) -> int:
    from quorumcal.goldset import build_goldset, write_goldset
    n_revert = args.n_revert if args.n_revert is not None else args.n_invalid
    tasks = build_goldset(
        args.repo, args.name, Path(args.workdir),
        n_invalid=args.n_invalid, n_valid=args.n_valid, seed=args.seed,
        source_paths=args.source_path,
        n_revert=n_revert, strict_valid=not args.loose_valid,
    )
    write_goldset(args.out, tasks)
    n_inv = sum(1 for t in tasks if t.label == "invalid")
    print(f"wrote {len(tasks)} tasks ({n_inv} invalid / {len(tasks)-n_inv} valid) "
          f"to {args.out}")
    return 0


def _cmd_panel_run(args) -> int:
    from quorumcal.goldset import read_goldset
    from quorumcal.panel import load_panels, run_panel
    from quorumcal.judges import QuotaExhausted
    tasks = read_goldset(args.goldset)
    panels = load_panels(args.panels)
    try:
        for name, specs in panels.items():
            print(f"== panel {name}: {len(specs)} judges × {len(tasks)} tasks ==")
            # flat cache dir: cache_key already fully qualifies
            # judge|model|lens|task, so judges shared across panels must not
            # get duplicate cells under a per-panel subdir.
            run_panel(tasks, specs, Path(args.cache_dir))
    except QuotaExhausted as exc:
        print(f"QUOTA HALT: {exc}")
        print("finished cells are cached — re-run this exact command in the "
              "next quota window to resume")
        return 3
    return 0


def _cmd_report(args) -> int:
    import json as _json
    from quorumcal.report import build_report, format_table
    rep = build_report(args.goldset, args.panels, args.cache_dir,
                       delta=args.delta, epsilon=args.epsilon)
    print(format_table(rep))
    Path(args.out).write_text(_json.dumps(rep, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    if any(p["error_guard_tripped"] for p in rep["panels"].values()):
        print("ERROR GUARD TRIPPED: >5% error rows in at least one panel — "
              "numbers above are not trustworthy; re-run `panel run` to heal "
              "errors first")
        return 1
    return 0


def _cmd_profile_emit(args) -> int:
    import json as _json
    from datetime import date
    from quorumcal.goldset import read_goldset
    from quorumcal.panel import cache_key, load_panels
    from quorumcal.profile import build_profile, panel_baseline
    report = _json.loads(Path(args.report).read_text(encoding="utf-8"))
    panels = load_panels(args.panels)
    tasks = read_goldset(args.goldset)
    specs = panels[args.panel]
    baseline = panel_baseline(tasks, specs, Path(args.cache_dir))
    observed = {}
    for s in specs:
        # claude-lineage cells recorded before the 2026-07-21 provenance fix
        # carry the ancillary-haiku artifact — do NOT harvest them into the
        # whitelist (spec models remain whitelisted; drop this exemption after
        # the next recalibration runs fully under the fixed adapter).
        if s.lineage == "claude":
            observed[s.judge_id] = []
            continue
        seen = set()
        for t in tasks:
            cell = Path(args.cache_dir) / f"{cache_key(s, t.task_id)}.json"
            m = _json.loads(cell.read_text(encoding="utf-8")).get("model_reported")
            if m:
                seen.add(m)
        observed[s.judge_id] = sorted(seen)
    prof = build_profile(report, panels, args.panel, baseline,
                         domain=args.domain, emitted_at=date.today().isoformat(),
                         q=args.q, expiry_days=args.expiry_days,
                         observed_models=observed)
    Path(args.out).write_text(_json.dumps(prof, indent=2, sort_keys=True))
    print(_json.dumps({"wrote": args.out, "panel": args.panel,
                       "q": prof["q"], "expires_at": prof["expires_at"]}))
    return 0


def _cmd_profile_check(args) -> int:
    import json as _json
    from datetime import date
    from quorumcal.profile import check_profile
    prof = _json.loads(Path(args.profile).read_text(encoding="utf-8"))
    today = args.today or date.today().isoformat()
    res = check_profile(prof, today=today)
    print(_json.dumps(res))
    return {"valid": 0, "expired": 2, "provenance-drifted": 4}[res["status"]]


def _cmd_monitor(args) -> int:
    import json as _json
    from quorumcal.monitor import run_monitor
    prof = _json.loads(Path(args.profile).read_text(encoding="utf-8"))
    lines = Path(args.log).read_text(encoding="utf-8").splitlines()
    res = run_monitor(prof, lines)
    print(_json.dumps(res, sort_keys=True))
    if res["provenance_alarm"]:
        return 4
    if res["alarm"]:
        return 5
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="quorumcal")
    sub = p.add_subparsers(dest="cmd", required=True)

    gs = sub.add_parser("goldset").add_subparsers(dest="gs_cmd", required=True)
    b = gs.add_parser("build", help="build a labeled gold set from a repo")
    b.add_argument("--repo", required=True, help="path to the subject git repo")
    b.add_argument("--name", required=True, help="short repo name for task ids")
    b.add_argument("--workdir", required=True, help="scratch clone dir (created)")
    b.add_argument("--out", required=True, help="output goldset.jsonl")
    b.add_argument("--n-invalid", type=int, default=60)
    b.add_argument("--n-valid", type=int, default=60)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--source-path", action="append", required=True,
                   help="mutation scope source path (repeatable)")
    b.add_argument("--n-revert", type=int, default=None,
                   help="mutant-revert valid tasks (truth-by-construction); "
                        "default = --n-invalid")
    b.add_argument("--loose-valid", action="store_true",
                   help="disable the strict commit-valid filter "
                        "(new-file/oversize diffs allowed)")
    b.set_defaults(fn=_cmd_goldset_build)

    pn = sub.add_parser("panel").add_subparsers(dest="panel_cmd", required=True)
    r = pn.add_parser("run", help="run all panels over the gold set (cached)")
    r.add_argument("--goldset", required=True)
    r.add_argument("--panels", required=True, help="panels.json")
    r.add_argument("--cache-dir", required=True)
    r.set_defaults(fn=_cmd_panel_run)

    rp = sub.add_parser("report", help="aggregate judgments into the numbers")
    rp.add_argument("--goldset", required=True)
    rp.add_argument("--panels", required=True)
    rp.add_argument("--cache-dir", required=True)
    rp.add_argument("--out", required=True)
    rp.add_argument("--delta", type=float, default=0.1)
    rp.add_argument("--epsilon", type=float, default=0.1)
    rp.set_defaults(fn=_cmd_report)

    pr = sub.add_parser("profile").add_subparsers(dest="profile_cmd", required=True)
    pe = pr.add_parser("emit", help="emit a risk profile from a calibration run")
    pe.add_argument("--report", required=True)
    pe.add_argument("--panels", required=True)
    pe.add_argument("--goldset", required=True)
    pe.add_argument("--cache-dir", required=True)
    pe.add_argument("--panel", required=True)
    pe.add_argument("--out", required=True)
    pe.add_argument("--domain",
                    default="code-change verification (crucible-seeded gold set)")
    pe.add_argument("--q", type=int, default=None,
                    help="chosen quorum; default q_min; must lie in the feasible window")
    pe.add_argument("--expiry-days", type=int, default=30)
    pe.set_defaults(fn=_cmd_profile_emit)
    pc = pr.add_parser("check", help="valid / expired / provenance-drifted")
    pc.add_argument("--profile", required=True)
    pc.add_argument("--today", default=None, help="ISO date override for tests")
    pc.set_defaults(fn=_cmd_profile_check)

    mo = sub.add_parser("monitor", help="CUSUM drift check over a verdict log")
    mo.add_argument("--profile", required=True)
    mo.add_argument("--log", required=True)
    mo.set_defaults(fn=_cmd_monitor)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
