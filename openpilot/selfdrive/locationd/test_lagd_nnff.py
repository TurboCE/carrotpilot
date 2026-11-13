from types import SimpleNamespace as NS

import numpy as np
import pytest

from openpilot.selfdrive.locationd import lagd


@pytest.mark.parametrize("fingerprint,enabled,expected", [
  ("CHEVROLET_TRAVERSE", True, True), ("CHEVROLET_TRAILBLAZER", True, True),
  ("CHEVROLET_TRAILBLAZER_CC", True, True), ("CHEVROLET_TRAX", True, True),
  ("CHEVROLET_EQUINOX", True, False), ("HYUNDAI_SONATA", True, False),
  ("CHEVROLET_TRAILBLAZER", False, False),
])
def test_nnff_delay_changes_are_limited_to_requested_cars(monkeypatch, fingerprint, enabled, expected):
  monkeypatch.setattr(lagd, "Params", lambda: NS(get_bool=lambda key: enabled))
  estimator = lagd.LateralLagEstimator(NS(carFingerprint=fingerprint, steerActuatorDelay=0.2), 0.01)
  assert estimator.nnff_frogpilot_parity is expected


@pytest.mark.parametrize("parity,custom,expected", [
  (True, 30.0, 0.3), (False, 30.0, 0.32), (True, 0.0, 0.32),
  (True, -5.0, 0.32), (True, 150.0, 0.32), (True, float("nan"), 0.32),
])
def test_custom_delay_matches_model_selection_only_on_parity_cars(monkeypatch, parity, custom, expected):
  monkeypatch.setattr(lagd, "Params", lambda: NS(get_float=lambda key: custom))
  monkeypatch.setattr(lagd.messaging, "new_message", lambda service: NS(liveDelay=NS()))
  estimator = lagd.LateralLagEstimator.__new__(lagd.LateralLagEstimator)
  estimator.nnff_frogpilot_parity = parity
  estimator.initial_lag = 0.4
  estimator.min_valid_block_count = 5
  estimator.block_size = 100
  estimator.block_avg = NS(valid_blocks=10, idx=0, get=lambda: (0.32, 0.01, 0.33, 0.02))
  assert estimator.get_msg(True).liveDelay.lateralDelay == pytest.approx(expected)


def test_confidence_measures_the_selected_peak_not_an_earlier_lobe(monkeypatch):
  count = 256
  ncc = np.zeros(512)
  origin = count - 1
  ncc[origin + 18:origin + 23] = 0.95  # earlier, narrower candidate
  ncc[origin + 45:origin + 56] = 1.0  # selected, wider peak
  monkeypatch.setattr(lagd, "masked_normalized_cross_correlation", lambda *args: ncc)
  args = (np.zeros(count), np.zeros(count), np.ones(count, dtype=bool), 0.01, 0.15, 1.0)
  _, _, legacy = lagd.LateralLagEstimator.actuator_delay(*args)
  _, _, aligned = lagd.LateralLagEstimator.actuator_delay(*args, align_confidence_roi=True)
  assert legacy == pytest.approx(0.95)
  assert aligned == pytest.approx(0.89)


def test_actual_fft_recovers_a_known_delay():
  rng = np.random.default_rng(12)
  expected = np.convolve(rng.normal(size=4096), np.ones(7) / 7, mode="same")
  actual = np.roll(expected, 35)
  mask = np.ones(len(expected), dtype=bool)
  mask[:100] = mask[-100:] = False
  delay, correlation, confidence = lagd.LateralLagEstimator.actuator_delay(
    expected, actual, mask, 0.01, 0.15, 1.0, align_confidence_roi=True)
  assert delay == pytest.approx(0.35, abs=0.005)
  assert correlation > 0.99
  assert confidence > 0.9


@pytest.mark.parametrize("parity", [False, True])
def test_estimator_uses_frogpilot_input_policy_only_on_parity_cars(monkeypatch, parity):
  estimator = lagd.LateralLagEstimator.__new__(lagd.LateralLagEstimator)
  estimator.nnff_frogpilot_parity = parity
  estimator.points_enough = estimator.points_valid = lambda: True
  times = np.arange(1000) * 0.01
  signal = np.sin(times * 3.0) * 0.05
  estimator.points = NS(get=lambda: (times, signal.copy(), signal.copy(), np.ones(1000, dtype=bool)))
  estimator.last_estimate_t = 0.0
  estimator.t, estimator.dt = 10.0, 0.01
  estimator.min_ncc, estimator.min_confidence = 0.95, 0.7
  updates, calls = [], []
  estimator.block_avg = NS(update=updates.append)

  def capture(desired, actual, mask, dt, minimum, maximum, **kwargs):
    calls.append((desired.copy(), minimum))
    return 0.3, 1.0, 1.0

  monkeypatch.setattr(estimator, "actuator_delay", capture)
  estimator.update_estimate()
  assert calls[0][1] == (0.0 if parity else 0.15)
  assert np.array_equal(calls[0][0], signal) is parity
  assert updates == ([0.3] if parity else [])
