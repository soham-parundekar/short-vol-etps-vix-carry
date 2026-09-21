"""Tests for the GARCH-filtered EVT tail-risk layer (Phase 09).

The one to read first is the look-ahead test on ``filter_sigma``. The project's
ex-ante claim - what a model estimated on data to 31 December 2017 said about
5 February 2018 - is only as good as the guarantee that the volatility state for a
date uses nothing from that date or after. That is tested by perturbation: change a
later return and require every earlier output to be bit-identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from svcarry.econometrics.evt import fit_gpd
from svcarry.econometrics.tailrisk import (
    SplicedInnovations,
    conditional_exceedance,
    filter_sigma,
    simulate_first_passage,
    termination_table,
)

PARAMS = {"mu": -0.003, "omega": 1e-4, "alpha": 0.28, "gamma": -0.25, "beta": 0.78}
DIST_PARAMS = np.array([5.7, 0.2])      # skewed-t nu, lambda


@pytest.fixture
def innov():
    rng = np.random.default_rng(0)
    z = rng.standard_t(5, 20000) / np.sqrt(5 / 3)
    return SplicedInnovations("skewt", DIST_PARAMS, fit_gpd(z, q=0.95, tail="upper"))


# ----------------------------------------------------------------- the spliced law
def test_spliced_law_is_continuous_at_the_join(innov):
    u = innov.gpd.threshold
    assert innov.sf(u - 1e-9)[0] == pytest.approx(innov.sf(u + 1e-9)[0], abs=1e-7)
    assert innov.sf(u)[0] == pytest.approx(innov.gpd.exceed_rate, abs=1e-7)


def test_spliced_ppf_inverts_sf(innov):
    p = np.array([0.001, 0.2, 0.5, 0.9, 0.949, 0.951, 0.999, 0.999999])
    assert np.allclose(innov.sf(innov.ppf(p)), 1.0 - p, atol=1e-9)


def test_simulated_mass_above_threshold_matches_exceedance_rate(innov):
    x = innov.ppf(np.random.default_rng(1).random(400_000))
    assert np.mean(x > innov.gpd.threshold) == pytest.approx(innov.gpd.exceed_rate, abs=0.002)


# ------------------------------------------------------------- log versus simple
def test_threshold_is_converted_from_simple_to_log(innov):
    """P(R >= 0.80) must be evaluated at log(1.8) = 0.588, not at 0.80."""
    sig = 0.08
    p = conditional_exceedance(0.80, PARAMS["mu"], sig, innov)
    assert p == pytest.approx(innov.sf((np.log(1.8) - PARAMS["mu"]) / sig))


def test_conflating_log_and_simple_understates_the_probability(innov):
    sig = 0.08
    right = conditional_exceedance(0.80, PARAMS["mu"], sig, innov)[0]
    wrong = innov.sf((0.80 - PARAMS["mu"]) / sig)[0]      # 0.80 used as a LOG threshold
    assert right > 2.0 * wrong


# --------------------------------------------------------------- no look-ahead
def test_filter_sigma_uses_only_past_returns():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2017-01-02", periods=300)
    r = pd.Series(rng.normal(-0.003, 0.04, 300), index=idx)
    base = filter_sigma(PARAMS, r)
    k = 200
    bumped = r.copy()
    bumped.iloc[k] = 0.96                          # a 5 February 2018 on day k
    after = filter_sigma(PARAMS, bumped)
    assert np.array_equal(base.iloc[: k + 1].to_numpy(), after.iloc[: k + 1].to_numpy()), \
        "sigma on or before the shocked day must not see the shock"
    assert after.iloc[k + 1] > 3 * base.iloc[k + 1], "the next day's sigma must see it"


# --------------------------------------------------------- probabilities by state
def test_calm_states_carry_less_risk_than_average_under_the_model(innov):
    """Under a GARCH scale the one-day tail probability rises with sigma, so the
    calm-state probability is BELOW the unconditional one. The phase prompt originally
    asserted the reverse; the model cannot produce that, and this test records why."""
    idx = pd.bdate_range("2010-01-04", periods=1000)
    sig = pd.Series(np.random.default_rng(4).lognormal(np.log(0.04), 0.4, 1000), index=idx)
    t = termination_table(sig, PARAMS["mu"], innov, {"-1x": 0.80}).set_index("state")
    calm = t.loc[t.index.str.startswith("calm"), "p_daily"].iloc[0]
    assert calm < t.loc["unconditional", "p_daily"]


def test_unconditional_probability_averages_rather_than_plugging_in_mean_sigma(innov):
    """The tail probability is convex in sigma, so the average of the probabilities
    exceeds the probability at the average sigma (Jensen)."""
    idx = pd.bdate_range("2010-01-04", periods=1000)
    sig = pd.Series(np.random.default_rng(5).lognormal(np.log(0.04), 0.5, 1000), index=idx)
    t = termination_table(sig, PARAMS["mu"], innov, {"-1x": 0.80}).set_index("state")
    at_mean = conditional_exceedance(0.80, PARAMS["mu"], sig.mean(), innov)[0]
    assert t.loc["unconditional", "p_daily"] > at_mean


# -------------------------------------------------------------------- survival
def test_survival_is_monotone_and_capping_volatility_raises_it(innov):
    kw = dict(simple_thresholds={"-1x": 0.80, "-0.5x": 1.60}, n_paths=3000,
              n_steps=504, seed=9)
    free = simulate_first_passage(PARAMS, innov, **kw)
    capped = simulate_first_passage(PARAMS, innov, sigma_cap=0.10, **kw)
    for k in ("-1x", "-0.5x"):
        s = free[f"survival_{k}"].to_numpy()
        assert np.all(np.diff(s) <= 1e-12) and s[0] <= 1.0
        assert capped[f"survival_{k}"].iloc[-1] >= free[f"survival_{k}"].iloc[-1]
    assert (free["survival_-0.5x"] >= free["survival_-1x"] - 1e-12).all(), \
        "a -0.5x product needs a larger move to wipe out, so survives at least as often"


def test_survival_standard_error_is_binomial(innov):
    sv = simulate_first_passage(PARAMS, innov, {"-1x": 0.80}, n_paths=2000,
                                n_steps=252, seed=2)
    s = sv["survival_-1x"].iloc[-1]
    assert sv["se_-1x"].iloc[-1] == pytest.approx(np.sqrt(s * (1 - s) / 2000))
