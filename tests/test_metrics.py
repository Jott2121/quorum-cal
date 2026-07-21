import pytest
from quorumcal.metrics import wilson_upper, empirical_quantile, pairwise_phi, mean_pairwise_phi, n_eff


def test_wilson_upper_zero_failures_still_positive():
    # 0/60 failures is NOT proof of zero rate — upper bound must be > 0
    u = wilson_upper(0, 60)
    assert 0.0 < u < 0.05


def test_wilson_upper_half():
    # k=30, n=60 at 90% one-sided: bound must sit above 0.5 but below 0.62
    u = wilson_upper(30, 60)
    assert 0.5 < u < 0.62


def test_wilson_upper_bounds_are_probabilities():
    assert wilson_upper(60, 60) <= 1.0
    assert wilson_upper(0, 1) >= 0.0


def test_wilson_upper_rejects_bad_input():
    with pytest.raises(ValueError):
        wilson_upper(5, 0)
    with pytest.raises(ValueError):
        wilson_upper(-1, 10)
    with pytest.raises(ValueError):
        wilson_upper(11, 10)


def test_empirical_quantile_conservative():
    # 10 values 1..10; p=0.9 → ceil(0.9*10)=9 → 9th smallest = 9
    assert empirical_quantile([float(v) for v in range(1, 11)], 0.9) == 9.0
    # p=1.0 → max
    assert empirical_quantile([3.0, 1.0, 2.0], 1.0) == 3.0
    # order must not matter
    assert empirical_quantile([9.0, 1.0, 5.0], 0.5) == 5.0


def test_empirical_quantile_monotone_in_p():
    vals = [0.0, 0.0, 1.0, 2.0, 2.0, 3.0]
    q = [empirical_quantile(vals, p) for p in (0.1, 0.5, 0.9)]
    assert q == sorted(q)


def test_empirical_quantile_rejects_empty():
    with pytest.raises(ValueError):
        empirical_quantile([], 0.9)


def test_phi_identical_vectors_is_one():
    v = [1, 0, 1, 1, 0, 0, 1, 0]
    assert pairwise_phi(v, v) == pytest.approx(1.0)


def test_phi_opposite_vectors_is_minus_one():
    a = [1, 0, 1, 0]
    b = [0, 1, 0, 1]
    assert pairwise_phi(a, b) == pytest.approx(-1.0)


def test_phi_zero_variance_defined_as_zero():
    # a judge that never errs has zero variance; phi is undefined → we define 0.0
    assert pairwise_phi([0, 0, 0, 0], [1, 0, 1, 0]) == 0.0


def test_phi_independent_vectors_near_zero():
    # constructed exactly balanced 2x2 table → phi == 0
    a = [1, 1, 0, 0]
    b = [1, 0, 1, 0]
    assert pairwise_phi(a, b) == pytest.approx(0.0)


def test_n_eff_perfectly_correlated_panel_is_one():
    v = [1, 0, 1, 1, 0, 0]
    rho = mean_pairwise_phi([v, v, v])
    assert rho == pytest.approx(1.0)
    assert n_eff(3, rho) == pytest.approx(1.0)


def test_n_eff_independent_panel_is_n():
    assert n_eff(3, 0.0) == pytest.approx(3.0)


def test_n_eff_clamps_negative_rho():
    # negative mean correlation would give N_eff > N; clamp to N
    assert n_eff(3, -0.5) == pytest.approx(3.0)


def test_mean_pairwise_phi_averages_all_pairs():
    a = [1, 0, 1, 1, 0, 0, 1, 0]
    b = list(a)
    c = [0, 0, 0, 0, 0, 0, 0, 0]  # zero variance → phi 0.0 with anyone
    # pairs: (a,b)=1.0, (a,c)=0.0, (b,c)=0.0 → mean 1/3
    assert mean_pairwise_phi([a, b, c]) == pytest.approx(1.0 / 3.0)


from quorumcal.metrics import PanelMetrics, panel_metrics


def _rows_all_correct(n_invalid=10, n_valid=10, judges=3):
    rows = [("invalid", ["reject"] * judges) for _ in range(n_invalid)]
    rows += [("valid", ["endorse"] * judges) for _ in range(n_valid)]
    return rows


def test_panel_metrics_perfect_panel():
    m = panel_metrics(_rows_all_correct())
    assert m.e_delta == 0.0
    assert m.u_epsilon == 0.0
    assert m.q_min == 1
    assert m.q_max == 3
    assert m.feasible
    assert m.n_effective == pytest.approx(3.0)   # zero-variance pairs → rho 0
    assert not m.error_guard_tripped


def test_panel_metrics_lockstep_wrong_panel():
    # all 3 judges endorse every invalid task together: e_delta = 3, infeasible
    rows = [("invalid", ["endorse"] * 3) for _ in range(10)]
    rows += [("valid", ["endorse"] * 3) for _ in range(10)]
    m = panel_metrics(rows)
    assert m.e_delta == 3.0
    assert m.q_min == 4          # floor(3)+1 > n_judges
    assert not m.feasible
    assert m.n_effective == pytest.approx(1.0)   # identical error vectors


def test_panel_metrics_error_rows_excluded_and_guard():
    rows = _rows_all_correct(n_invalid=9, n_valid=9)
    rows.append(("invalid", ["error", "reject", "reject"]))
    m = panel_metrics(rows)
    assert m.n_tasks_total == 19
    assert m.n_tasks_used == 18
    assert m.n_tasks_error == 1
    assert m.error_guard_tripped          # 1/19 > 5%


def test_panel_metrics_abstain_charges_liveness_not_safety():
    rows = [("invalid", ["reject"] * 3) for _ in range(10)]
    rows += [("valid", ["abstain", "endorse", "endorse"]) for _ in range(10)]
    m = panel_metrics(rows)
    assert m.e_delta == 0.0
    assert m.u_epsilon == 1.0
    assert m.q_max == 2          # 3 - ceil(1)
    assert m.feasible


def test_panel_metrics_wrong_rates_and_uppers():
    rows = [("invalid", ["endorse", "reject", "reject"]) for _ in range(10)]
    rows += [("valid", ["endorse", "endorse", "endorse"]) for _ in range(10)]
    m = panel_metrics(rows)
    assert m.per_judge_wrong_rate[0] == pytest.approx(0.5)   # judge 0 wrong on 10/20
    assert m.per_judge_wrong_rate[1] == 0.0
    assert m.per_judge_wrong_upper[1] > 0.0                  # 0/20 still bounded above 0


def test_panel_metrics_rejects_empty_or_mismatched():
    with pytest.raises(ValueError):
        panel_metrics([])
    with pytest.raises(ValueError):
        panel_metrics([("invalid", ["reject", "reject"]), ("valid", ["endorse"])])
    with pytest.raises(ValueError):
        panel_metrics([("weird", ["reject", "reject", "reject"])])


from quorumcal.metrics import bootstrap_n_eff


def test_bootstrap_n_eff_perfectly_correlated_panel_collapses_to_one():
    v = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0]
    vectors = [v, v, v]
    lo, hi = bootstrap_n_eff(vectors, iters=500, seed=0)
    assert lo == pytest.approx(1.0)
    assert hi == pytest.approx(1.0)


def test_bootstrap_n_eff_independent_zero_variance_panel_is_n():
    # zero-variance columns → phi undefined → defined as 0.0 → rho_bar 0.0 →
    # n_eff == n_judges for every resample, so the CI collapses to [N, N].
    zero = [0, 0, 0, 0, 0, 0, 0, 0]
    vectors = [zero, zero, zero]
    lo, hi = bootstrap_n_eff(vectors, iters=500, seed=0)
    assert lo == pytest.approx(3.0)
    assert hi == pytest.approx(3.0)


def test_bootstrap_n_eff_deterministic_under_same_seed():
    vectors = [[1, 0, 1, 1, 0, 0, 1, 0], [0, 1, 1, 0, 0, 1, 1, 0],
              [1, 1, 0, 0, 1, 0, 1, 1]]
    a = bootstrap_n_eff(vectors, iters=300, seed=42)
    b = bootstrap_n_eff(vectors, iters=300, seed=42)
    assert a == b
