# WIP-FR steering follow-up on nnff_fix

Compared `leehyuk1108/carrotpilot` fix_pls
`32d0aa0e06b0520935738c30f204d97e33a521a9` and WIP-FR
`2e6994315a72fd9053d0681efcee1ae1cc8eba6f` against TurboCE nnff_fix
`fabd5d303da2f807441f58a9580b5eedd0e55137`.

The steering code additions after fix_pls are in `97fdfa1cec30d97cacfb6e9b4c6f4143b51e2868`
and `d15e5b69838fc2ebe9ae9d024101492df8f149a3`; `2e699431` refines the
interpretation of their replay evidence. The branches diverge, so importing
these commits wholesale would replace existing target-branch work.

## Audit and selective port

| WIP-FR change | nnff_fix disposition |
| --- | --- |
| Conditional integration without trimming the existing integral at saturation | Already implemented by NNFFPIDController |
| Future NN inputs follow valid lateral delay | Already implemented, with manual-delay policy and invalid-input guards retained |
| Calibrated orientation/pitch available before controller evaluation | Already implemented |
| Roll-compensated acceleration band of roll*g +/- 3 m/s² | Already implemented; port the upstream roll-aware regression cases |
| No extra linear friction error in the normal full-NNFF path | Missing: port the scoped guard from 97fdfa1c |
| No friction in the short/missing-model fallback feedforward | Already implemented |

The production change applies only to full NNFF on Traverse, Trailblazer,
Trailblazer CC and Trax. A model's `friction_override` flag no longer adds
linear friction to the PID error in this scope. Other cars retain their
model-requested override. The NN model's own friction-related input is retained.

WIP-FR retains a 0.1 s control-stage target filter and uses lateral delay alone
as its desired-jerk horizon. These are existing policy differences, not missing
new fixes: retain nnff_fix's selected model smoothing, target-filter bypass and
delay-plus-model-smoothing jerk horizon described in
[the follow-up verification](nnff_straight_verification_20261112.md).
The two branches' replay results do not establish which policy drives better.

No gains, model weights, vehicle geometry, steering timing/limits, safety code,
NNFFLite behavior or longitudinal features are imported or retuned. FCW, display
and Navdy additions are outside this requested NNFF/steering backport.

## Verification

- New forced-override regression: before the production fix, the four scoped
  car cases fail and the non-scoped Equinox case passes. After the fix, all five
  pass. Nonzero friction makes the missing compensation guard observable even
  when the selected model would not request an override by default.
- 64 controller/model-selection, PID and target-pipeline cases pass with the
  existing memory schema/I/O adapter, executing production controller, NN weights
  and PID math. This includes the additional roll-aware upstream cases.
- Native controller tests could not collect in this Ubuntu environment because
  `openpilot.cereal` is unavailable. Adapter checks do not validate native
  Cereal/CarInterface/CAN integration.
- `git diff --check` passes. No vehicle install, parameter change or road test.

This is a scoped source backport, not evidence that steering oscillation or
straight-line tracking has improved in a closed-loop vehicle.
