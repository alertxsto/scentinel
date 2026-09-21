import pytest

from scentinel.core import casegen

pytestmark = pytest.mark.verification


def test_the_turbulent_diffusivity_moves_with_the_schmidt_number():
    """Pin the cited Sc_t range and the direction and scale of its effect."""
    molecular = casegen.scalar_diffusivity("CO")
    turbulent_viscosity = 1.0e-4
    at_sc_07 = molecular + turbulent_viscosity / 0.7
    at_sc_09 = molecular + turbulent_viscosity / 0.9

    assert casegen.ALPHA_DT == pytest.approx(
        1.0 / casegen.TURBULENT_SCHMIDT_NUMBER
    )
    assert 0.7 <= casegen.TURBULENT_SCHMIDT_NUMBER <= 0.9
    assert at_sc_07 > at_sc_09 > molecular
    assert (at_sc_07 - molecular) / (
        at_sc_09 - molecular
    ) == pytest.approx(0.9 / 0.7)
