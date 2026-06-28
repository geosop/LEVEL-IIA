"""beta_min is the kappa-scaled single-participant resolution floor and scales
as 1/sqrt(n)."""
import numpy as np
from cri_leveliia.inference import beta_min, normal_equivalent_stringency

def test_formula_scaling():
    b1 = beta_min(1.0, 0.007, 48, kappa=2.0)
    b4 = beta_min(1.0, 0.007, 4 * 48, kappa=2.0)
    assert np.isclose(b1 / b4, 2.0, rtol=1e-6)   # 1/sqrt(n) -> quartering n doubles

def test_kappa_linear():
    assert np.isclose(beta_min(1.0, 0.007, 48, 1.0) * 2,
                      beta_min(1.0, 0.007, 48, 2.0))

def test_stringency_is_not_fixed_alpha():
    # the normal-equivalent stringency depends on se_pop, so it is NOT a fixed
    # population alpha level: different se give very different tail values
    s_small = normal_equivalent_stringency(40.0, 4.0)
    s_large = normal_equivalent_stringency(40.0, 20.0)
    assert s_small < s_large
    # the value swings by many orders of magnitude with se_pop, so it cannot be a
    # fixed population alpha level
    import numpy as np
    assert np.log10(s_large) - np.log10(s_small) > 10
