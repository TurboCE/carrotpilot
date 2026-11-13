import math

import pytest

from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature, get_model_desired_curvature, get_nnff_model_smoothing
from openpilot.selfdrive.controls.lib.drive_helpers import use_carrot_lane_planner


@pytest.mark.parametrize("previous,target", [(0.0, 0.001), (0.002, -0.001), (-0.002, 0.0)])
def test_full_nnff_does_not_add_another_model_target_filter(previous, target):
  assert get_model_desired_curvature(target, previous, True) == target
  alpha = 1 - math.exp(-0.01 / 0.1)
  assert get_model_desired_curvature(target, previous) == pytest.approx(alpha * target + (1 - alpha) * previous)


@pytest.mark.parametrize("speed", [5.0, 15.0, 25.0, 35.0])
@pytest.mark.parametrize("direction", [-1, 1])
def test_full_nnff_uses_frogpilot_acceleration_limit(speed, direction):
  requested = direction * min(0.2, 5.0 / speed ** 2)
  curvature, limited = clip_curvature(speed, requested, requested, 0.0, True)
  assert curvature == pytest.approx(direction * min(0.2, 3.0 / speed ** 2))
  assert limited


def test_other_paths_keep_carrot_low_speed_acceleration_limit():
  curvature, _ = clip_curvature(15.0, 0.02, 0.02, 0.0)
  assert curvature == pytest.approx(4.5 / 15.0 ** 2)


def test_full_nnff_still_limits_target_jerk():
  curvature, _ = clip_curvature(20.0, 0.0, 0.1, 0.0, True)
  assert curvature == pytest.approx(5.0 / 20.0 ** 2 * 0.01)


@pytest.mark.parametrize("base,expected", [(0.0, 0.0), (0.13, 0.13), (0.3, 0.3), (1.0, 0.6), (-0.1, 0.0)])
def test_nnff_uses_the_selected_models_smoothing(base, expected):
  assert get_nnff_model_smoothing(base) == pytest.approx(expected)


def test_full_nnff_uses_model_target_even_when_lane_planner_is_selected():
  assert not use_carrot_lane_planner(True, 80., 0., True)
  assert use_carrot_lane_planner(True, 80., 0.)
  assert not use_carrot_lane_planner(False, 80., 0.)
  assert not use_carrot_lane_planner(True, 20., 40.)
