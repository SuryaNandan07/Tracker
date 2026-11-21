# Phase 2 smoothing comparison

Recommended starting point: **Humanoid_Mocap_Balanced.blend**. It improves quiet
rotation stability while retaining about 96–98% of measured wrist-speed peaks.
Use Natural if strike sharpness is more important than the additional reduction.
Cinematic is an intentionally stronger alternative, not an automatic upgrade:
its small extra aggregate jitter improvement costs approximately 7–16% of peak speed.

## Files and playback

- `C:\Epic Gamez\tracker\Humanoid_Mocap_Natural.blend`
- `C:\Epic Gamez\tracker\Humanoid_Mocap_Balanced.blend`
- `C:\Epic Gamez\tracker\Humanoid_Mocap_Cinematic.blend`

Open a file in Blender 5.1.2 and press Space over the viewport or Timeline Play.
Each has 572 source samples at their original fractional times, 60 FPS, frames
1–573, duration 9.517 seconds. Only `Character_MOCAP_TEST` has a new Action named
`MOCAP_PHASE2_<preset>_<unique suffix>`. The reference character and both rest rigs,
mesh data and weights are unchanged. Original Actions are retained, including the
previous smoothed Action. The previous `.blend` files and raw motion are untouched.

Compare at the same playback speed, view and timeline range. Inspect the hands
during pauses, then the transitions around 0.42, 2.12, 2.58, 3.37, 6.52, 7.43
and 8.0–8.37 seconds. Compare at normal speed first; slow playback can exaggerate
differences. In the Action Editor you can select the preserved previous smoothed
Action for a same-character comparison. Do not save over earlier files.

## Identical-segment comparison

| Version | Landmark residual RMS, mm | Rotation residual RMS, degrees | Wrist peak speed vs current smoothed | Largest peak-time shift |
|---|---:|---:|---:|---:|
| Current smoothed baseline | 3.566 | 0.336 | 100% | — |
| Natural | 2.972 | 0.309 | 99.2–101.2% | 17 ms |
| Balanced | 2.973 | 0.298 | 95.7–98.1% | 17 ms |
| Cinematic | 2.949 | 0.297 | 83.9–93.5% | 17 ms |

These are high-frequency **jitter proxies**, not ground-truth error. The landmark
metric uses the same 5,223 relatively quiet joint samples selected before filtering.
The rotation metric uses the same 1,159 quiet bone samples selected from the current
smoothed Action, then frozen across presets. Both measure deviation from the
adjacent samples' midpoint (spherical midpoint for rotation), with identical
sample selection for before/after. The previous report's 0.327° used a selection
based on the earlier unsmoothed Action; 0.336° is the same current animation
remeasured on this task's common mask, not evidence that its animation changed.

Wrist events are the five strongest separated speed events per hand in the current
smoothed animation, not manually annotated punches. All presets are evaluated on
those same ten events, with a ±3-sample local peak search. Natural and Balanced
have nine unchanged peak times and one 17-ms shift. Cinematic has eight unchanged
times and shifts of 16 and 17 ms. Both hands' best speed-trace alignment remains
zero samples for all presets (searched ±3 samples). A local peak check cannot
prove that every deliberate pose or direction change is unchanged.

## Filters and configuration

Settings are in `mocap/phase2_presets.json`:

| Preset | Landmark window | Quiet/fast landmark blend | Quaternion radius | Quiet/fast rotation blend |
|---|---:|---:|---:|---:|
| Natural | 11 samples | 0.92 / 0.10 | ±3 samples | 0.75 / 0.05 |
| Balanced | 15 samples | 0.97 / 0.15 | ±4 samples | 0.88 / 0.10 |
| Cinematic | 19 samples | 1.00 / 0.25 | ±5 samples | 0.97 / 0.18 |

The landmark stage fits centered quadratic polynomials at actual source times,
weighted by image-landmark visibility, floored at 0.05. Missing coordinates use
the existing time-based interpolation only in derived data and receive low weight.
The fit is bounded by each coordinate's local observed range to limit overshoot.
A common broad-motion activity estimate blends strongly toward the fit in quiet
segments and only lightly during fast activity. Its envelope protects fast-event
lead-ins and recovery; it does not explicitly label combat poses or contacts.

The original rest-pose-aware rotation solver and its existing 35-ms causal filter
and angular safety limiter are reused unchanged. Additional rotation smoothing
is a centered Gaussian mean of hemisphere-aligned quaternions, normalized and
blended spherically toward the center sample. Gaussian distances use timestamp
offsets; sigma is half the configured radius. Fast rotations get a much smaller
blend. Output signs are made continuous, and keys retain their original times.

No Euler-angle averaging, global root movement, bone scaling, foot locks or IK
is introduced. Legs and torso benefit from quiet-segment smoothing, but this is
not foot-contact reconstruction. Confidence weighting can reduce contamination
from uncertain samples; it cannot identify an incorrect but confident estimate.

The current metric improvement plateaus at the landmark stage; Cinematic does
not meaningfully outperform Balanced there. Cinematic's right forearm quiet
rotation residual actually increases from 0.424° to 0.436°, despite the small
overall improvement. Natural's selected peak speed can increase by up to 1.2%.
Presets trade sharpness for continuity rather than improving every joint equally.

## Executed validation

- All three files created, saved, and reopened in separate Blender 5.1.2 processes.
- Reference pose matrices checked at all 572 sample times during creation;
  reference evaluated mesh checked at six times for each reopened preset.
- Reference transforms, rest geometry/weights and original Action keyframes
  compared unchanged. Target rest rig/mesh/weights also compared unchanged.
- Original Actions retained; keyframes checked unchanged in reopened files.
- Target evaluated mesh changes across poses (maximum sampled vertex displacements
  approximately 1.033, 1.038 and 1.048 m). Finite transforms at all samples.
- Quaternion hemispheres continuous; maximum adjacent local rotation steps are
  23.49°, 22.33° and 19.47° respectively. No newly introduced large flips detected.
  This threshold check is not an anatomical guarantee against limb twist.
- Source `Humanoid_Mocap_Smoothed.blend` hash checked unchanged for every preset.
- 32 Python tests pass, including constant-motion preservation, input immutability,
  weaker fast-motion correction and low-confidence outlier influence.
- Rendered frames 100 and 400 for each preset; inspected frame 400 for all three
  and frame 100 for Balanced. Reference remains in T-pose and the target poses
  are recognizable. Static renders do not establish perceived trembling in playback.

Interactive playback has not been manually judged here. Your visual comparison
is the final test of strike impact, especially for Cinematic. Remaining issues
include monocular depth error, imperfect limb twist, foot sliding/floating and
the inherited root-position limitation. Longer filters may soften or anticipate
transitions despite their centered formulation; no claim of zero lag everywhere.

Detailed outputs: `blender/phase2_<preset>_checked.json` and
`blender/phase2_comparison.json`. PNG pose checks and derived landmarks are in
`exports/phase2/`; no derived coordinates replace raw recording values.

## Reproduce or tune

NumPy processing uses `.venv-mocap`; Blender does not need SciPy. For a fresh
output directory, after editing or copying the configuration:

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.phase2_motion --presets mocap\phase2_presets.json --output-dir exports\phase2_variant
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background 'C:\Epic Gamez\tracker\Humanoid_Mocap_Smoothed.blend' --python-exit-code 1 --python 'C:\Epic Gamez\tracker\blender\phase2_retarget.py' -- --preset Balanced --motion-dir 'C:\Epic Gamez\tracker\exports\phase2_variant' --output 'C:\Epic Gamez\tracker\Humanoid_Mocap_Balanced_Variant.blend'
```

All output files must be new; scripts refuse replacement. The common solver and
earlier scripts are unchanged. New implementation files are `phase2_motion.py`,
`phase2_presets.json`, `phase2_retarget.py`, `phase2_compare.py`, `phase2_preview.py`
and `mocap/tests/test_phase2.py`.
