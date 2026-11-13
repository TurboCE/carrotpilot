# Scoped GM NNFF follow-up verification, 2026-11-12

Target: TurboCE/carrotpilot `nnff_fix`, based on `trailblazer` c1dd929.
Scope: Traverse, Trailblazer (including CC) and Trax. No vehicle installation,
restart, stored-gain change, safety-limit increase or new PR was performed.

## Additional corrections

- Explicit Trailblazer CC→Trailblazer and Trax→Volt donor selection, matching
  the pinned FrogPilot substitution table. Traverse→Trailblazer is retained.
  Own models precede donors; a donor's firmware-specific model precedes its
  generic file. Firmware-string normalization follows FrogPilot in this scope.
- Full NNFF directly uses the model target, bypassing the Carrot lane planner
  and additional 0.1 s control-stage target filter. The acceleration ceiling is
  3 m/s² plus roll compensation. Other paths retain their policies.
- Modeld and NNFF share the selected fixed model smoothing time. The recorded
  LatSmoothSec=13 is 0.13 s, not the unused initialization constant zero and not
  the previously assumed Frog default 0.1 s. Manual delay 30 is 0.3 s; the NNFF
  jerk horizon is therefore 0.43 s, while future NN inputs use physical delay.
- Scoped automatic delay estimation follows FrogPilot's input/range policy;
  manual positive delay overrides consistently. Confidence indexing is aligned
  with the selected correlation peak. Invalid override values use auto delay.
- Disabling manual torque tuning restores default factors and PID gains.
- The imported CustomSteerMax ceiling is restricted to the requested GM scope;
  unrelated GM vehicles regain their original custom-limit handling.

Existing NNFF pose, frame-local friction, conditional integration, AlwaysLateral
limiter feedback and history-reset corrections are retained. No curve-dependent
gain scheduling is added.

## Model smoothing audit

The legacy dynamic-uncertainty helper indexes a valid (1,33,15) tensor with four
indices. Its exception path therefore uses the base smoothing time. The scoped
NNFF policy explicitly uses the selected fixed model time, as FrogPilot does,
instead of introducing a new uncertainty-dependent target. Thirty tensor cases
retain the existing valid-input model-stage outputs. The legacy helper and its
non-scoped call path remain unchanged. Twelve scope-policy cases are checked.

## Results and limits

Steady straight input: 84 error/speed/roll conditions ×40 controller frames.
Original and revised P/I/F/request agree exactly. This preserves local restoring
response under equal, unsaturated input; it does not validate road tracking.

Four independently selected straight windows total 14,913 frames (~149 s),
selected by target acceleration, active state and lack of driver/indicator/lane
change input. Selection does not require small measured tracking error.

| Window | Command band RMS, original → revised | Request saturation |
|---|---:|---:|
| 직선 48 km/h | 0.0177 → 0.0219 (+23.8%) | 0.00% → 0.00% |
| 직선 87 km/h | 0.0266 → 0.0329 (+23.5%) | 0.00% → 0.00% |
| 직선 65 km/h | 0.0180 → 0.0226 (+25.7%) | 0.00% → 0.00% |
| 직선 70 km/h | 0.0241 → 0.0342 (+42.0%) | 0.00% → 0.00% |
| 01:24 반복조향 | 0.3294 → 0.3470 (+5.3%) | 51.73% → 50.07% |
| 01:37 반복조향 | 0.4195 → 0.3803 (-9.3%) | 39.50% → 46.90% |

Command RMS is 0.4–1.2 Hz after linear detrending with a Hann window.
These are normalized command metrics, **not predicted steering-angle or vehicle
motion improvements**. Straight command-band content increases 23–42%; curve
results are mixed. An ablation retaining the original target but changing delay
handling stays near the original straight RMS. Removing the extra target filter
accounts for most of the straight command-band increase.

In 39,169 frames, revised and pinned FrogPilot NNFF under common
VM/model/gains/input have mean request difference 2.24e-07, maximum
1.22e-06. Four selected model profiles each pass 1,501-frame comparisons;
18 actual FFT cases match the pinned estimator. Nine non-target controller cases
(500 frames each), 30 custom-limit cases and 135 default clipping cases retain
the existing non-target behavior through schema/I/O adapters.

Reference: FrogPilot a22c476734514e36b196168cd39743b74f30dc01. Both controllers use
the selected target model weights; this does not establish what an unspecified
installed FrogPilot model catalog contains. Source and numeric adapters execute
real controller/NN/PID/VM code but do not validate native Cereal/CarInterface/CAN.

**Road straight-line tracking and elimination of repeated steering remain
unverified.** Recorded vehicle/model/applied-torque feedback is fixed. A changed
request against original applied torque alters integrator freeze decisions;
new EPS motion is not simulated. Common-integral plots isolate P/F differences
and are not closed-loop tests. No validated nonlinear EPS/vehicle plant or new
driving route was available.

Remaining system differences include the driving-model and NN-weight catalogs,
vehicle/sensor calibration, stored gains/steering ratio/smoothing/custom deltas,
9.81 vs 9.8 gravity precision, scalar/batch float32 rounding and defensive invalid
input handling, plus policies outside NNFF. Original recorded gains (1.7/1/1.2)
are held fixed; they are not replaced with FrogPilot defaults. Whole-system or
road equivalence must not be inferred from NNFF arithmetic parity.
