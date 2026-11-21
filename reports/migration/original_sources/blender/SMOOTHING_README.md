# Motion-adaptive jitter reduction

Open `C:\Epic Gamez\tracker\Humanoid_Mocap_Smoothed.blend` and press Space over
the viewport or click Timeline Play. Only `Character_MOCAP_TEST` uses the new
`MOCAP_SMOOTH_sword_combo_ef771c1f` Action. Timing remains 60 FPS, frames 1–573,
572 timestamped samples over 9.517 seconds. `Character_REFERENCE` is unchanged.

The original `Humanoid_Mocap_Result.blend` was not modified (SHA256 checked).
The original target Action is retained unedited inside the new file as
`MOCAP_sword_combo_001_ad35ce39` with a fake user so it survives saving. Select
the target, open the Action Editor and switch between these Actions to compare.
Do not save over the original project. Rig rest matrices, proportions, mesh data,
weights and transforms are unchanged. No raw NPZ, source JSON, original capture
script, fitness script or Unity file was changed.

## Diagnosis and algorithm

Noise exists in the raw world landmark trajectories and in the resulting local
rotation curves, despite the earlier causal 35-ms rotation filter. The positional
noise is an upstream contributor; bone-direction calculations can carry it into
rotation. These measurements do not independently quantify how much noise each
stage creates, and there is no ground-truth motion capture for comparison.

The new landmark filter uses NumPy in `.venv-mocap` (no SciPy installation needed):

1. Load the original export and interpolate missing joint positions in timestamp
   space exactly as the existing viewer does. Work only on a derived copy.
2. Fit a centered quadratic polynomial over nine neighboring samples for each
   coordinate. This is Savitzky–Golay-style local least squares, using actual
   timestamp offsets so nonuniform intervals are supported. At boundaries use
   the nearest available nine-sample window. Nine samples span about 133 ms.
3. Estimate motion speed from that fit. For each joint, speeds below its 35th
   percentile get 85% filtered / 15% original coordinates; speeds above its 85th
   percentile get only 15% filtered / 85% original coordinates. Blend continuously
   in between. A two-sample activity envelope protects fast-event transitions.

The existing rest-pose-aware rotation solver is extracted unchanged into
`retarget_solver.py` and run on these derived landmarks. Its 35-ms causal filter
and angular safety limit remain in place; the new centered filters do not add
another one-way filter delay.

A light quaternion-aware stage further suppresses residual trembling: centered
spherical averaging over ±2 samples, neighbor weights 0.5 at ±1 and 0.2 at ±2.
Quiet motion blends 65% toward the spherical average; fast rotation blends only
10%. Quaternion hemispheres are aligned before interpolation, output quaternions
are normalized, and adjacent signs remain continuous. A new independent Action
receives linear quaternion-component keys at the unchanged fractional frame times.
Offline centered filtering can use future samples and slightly anticipate/change
transitions; it is not a live-stream filter or a guarantee of zero event shift.

## Measured results

| Measurement | Before | After |
|---|---:|---:|
| Quiet landmark high-frequency residual RMS | 12.451 mm | 3.566 mm |
| Quiet rotation residual RMS, weighted across mapped bones | 0.518° | 0.327° |
| Left forearm quiet rotation residual RMS | 0.742° | 0.454° |
| Right forearm quiet rotation residual RMS | 0.846° | 0.412° |

These are **jitter proxies**, not absolute pose error. Landmark residual is distance
from the adjacent samples' midpoint, on 5,223 relatively quiet joint-samples
selected from broad fitted velocity. Rotation residual is the geodesic angular
distance from neighbors' spherical midpoint, on contiguous quiet selections from
the original Action (same selections used before/after). Individual mapped bones
show approximately 12–51% lower quiet rotation residual. Full per-bone data and
the exact event measurements are in `smoothing_validation.json`.

Fast-motion checks use the five strongest separated wrist-speed events per hand,
not manually labeled punches. On the raw landmark trajectories, all ten peaks
retain their timestamp and about 91–94% of their original speed. On the **evaluated
Blender wrist trajectories**, nine peaks retain their timestamp and one moves
17 ms later. Speeds retain 94.1–99.96% of the previous retarget's peaks. Both wrist
speed traces have their best tested alignment at zero lag (tested ±3 samples).
This indicates limited added slowing, but is not proof that every strike is ideal.

## Validation performed

- All 29 Python tests pass, including new polynomial-preservation, noise-reduction,
  input-immutability and invalid-window checks.
- Blender 5.1.2 evaluated all 572 sample times with finite target transforms;
  reference pose matrices stayed unchanged.
- Reference geometry, transforms and Action keyframes compared unchanged;
  target rest rig, mesh and weights compared unchanged.
- Original target Action keyframes compared unchanged and retained separately.
- Every adjacent quaternion dot product is positive; no hemisphere discontinuity.
  Largest new local angular step is about 22.88°, versus 24.48° before. No large
  new rotation flips were detected. One forearm's maximum increases slightly
  (21.95° to 22.25°), while its quiet jitter decreases substantially.
- Reopened `Humanoid_Mocap_Smoothed.blend` in a separate Blender process and
  compared evaluated original/new wrist trajectories across the full recording.
- Original input `.blend` hash remains unchanged.

Interactive playback was not manually judged. The checks are numerical Blender
evaluation rather than a claim that every movement looks natural. The remaining
subjective check is to play both Actions in the viewport and assess strike impact.

## Configuration and reproducibility

Create a new variant without replacing any existing outputs:

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.smooth_motion --window 9 --strength 0.85 --fast-strength 0.15 --output exports\sword_combo_variant.json
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background 'C:\Epic Gamez\tracker\Humanoid_Mocap_Result.blend' --python-exit-code 1 --python 'C:\Epic Gamez\tracker\blender\smooth_retarget.py' -- --motion 'C:\Epic Gamez\tracker\exports\sword_combo_variant.json' --output 'C:\Epic Gamez\tracker\Humanoid_Mocap_Smoothed_Variant.blend' --rotation-quiet 0.65 --rotation-fast 0.10
```

Both export and save commands refuse existing output filenames. Reduce `--strength`
or `--window` if holds feel too soft; reduce `--fast-strength` and `--rotation-fast`
toward zero to retain more strike detail. Use an odd window ≥3. These settings
cannot correct erroneous depth, missing contacts, systematic pose errors or limb
twist. Foot sliding, root-position limitations and the original tracking errors
remain. No rig edits, retargeting expansion or new motion-reconstruction features
are included.
