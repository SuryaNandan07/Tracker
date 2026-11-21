# One-character experimental retarget

Open `C:\Epic Gamez\tracker\Humanoid_Mocap_Result.blend` in Blender and press
Space over the 3D viewport or click Timeline Play. The timeline is frames 1–573
at 60 FPS, covering 9.517 seconds of captured motion (572 timestamped samples).
The reference is at the origin; the animated test character is at X ≈ 2.1127.
Select `Character_MOCAP_TEST` in the Outliner, enter Pose Mode, and inspect the
new Action `MOCAP_sword_combo_001_ad35ce39` in the Action Editor if desired.

## What changed

Only in the output file, the original `Armature` was renamed
`Character_REFERENCE` and `Armature.001` was renamed `Character_MOCAP_TEST`, as
authorized. Mesh names remain `Ch44` and `Ch44.001`, each bound to its respective
armature. Both rigs and meshes were already independent; no rebinding or rest-pose
editing was needed. The reference keeps its original `mixamo.com` Action and
unchanged static T-pose. The target's old `mixamo.com.001` Action is retained as
a separate datablock; the new Action is assigned to the target alone.

The input `Humanoid_Retarget_Test.blend`, raw recordings, JSON export, existing
skeleton visualization, fitness scripts and Unity files were not modified.
No new meshes, rig bones or proportions were substituted.

## Mapping and algorithm

All mapped bone names have the `mixamorig:` prefix:

| Target bones | MediaPipe landmarks |
|---|---|
| Hips | Left/right hip axis and hip-to-shoulder midpoint direction |
| Spine, Spine1, Spine2 | Orientation blend from hip frame to shoulder frame |
| LeftArm, RightArm | Shoulder → elbow (11→13, 12→14) |
| LeftForeArm, RightForeArm | Elbow → wrist (13→15, 14→16) |
| LeftUpLeg, RightUpLeg | Hip → knee (23→25, 24→26) |
| LeftLeg, RightLeg | Knee → ankle (25→27, 26→28) |

The exported `(x,z,-y)` Blender coordinate basis is converted through the
armature object's inverse rotation. Torso orientations use anatomical hip and
shoulder axes, corrected against the rig's rest-pose body basis. Limb rotations
use the shortest swing from the inherited rest orientation to the tracked segment
direction. Parent-space quaternion rotations account for the rig's original rest
matrices. All bone lengths, translations and scales retain the rest rig's values.
Object transforms and hip translation stay fixed: no walking trajectory is inferred
from hip-centered data. Unmapped head, hands, feet, fingers and shoulder bones
inherit parent motion but receive no independent animation curves.

Keyframe times are `1 + timestamp_ms * 60 / 1000`, including fractional frames.
There are 48 quaternion component curves (12 mapped bones × 4 components), with
572 keys on each. Quaternion signs are made continuous; F-curves are linear.
Missing samples at source rows 174 and 431 are interpolated in timestamp space.
Segments shorter than 2.5 cm are treated as degenerate and hold prior orientation.
Temporal quaternion smoothing uses a 35-ms time constant and a 720°/s angular-rate
limit to suppress flips. These choices add some lag and soften fast movements.

## Validation actually performed in Blender 5.1.2

- Evaluated all 572 saved sample times; reference pose matrices remained unchanged.
- Compared reference evaluated mesh vertices at six times; they were identical.
- Compared reference rest rig, object transforms, mesh geometry/weights/material
  assignments and original Action keyframes before/after: unchanged, excluding the
  authorized object rename.
- Compared target rest rig, mesh geometry and weights before/after: unchanged.
- Checked finite target bone matrices and fixed bone lengths at every sample.
  Largest numerical length deviation was 0.000262 armature units (~0.00000262 m).
- Target mesh vertices move by up to approximately 1.026 m between sampled poses,
  confirming actual skinned deformation rather than animation of bones alone.
- Reopened the saved `.blend` in a new Blender process; verified independent rigs,
  mesh bindings, correct Action ownership, 48 × 572 keys and changing target poses.
- Verified the input file's SHA256 remained unchanged.
- Rendered and visually inspected frames 100 and 400. Previews are saved as
  `exports/retarget_preview_100.png` and `exports/retarget_preview_400.png`.

Interactive Play was not manually exercised, but Blender animation evaluation,
skinning and rendering were executed successfully. The reference remains static
with its original Action. Detailed metrics are in `retarget_validation.json`.

## Known limitations

This is an experimental motion transfer, not production-quality animation.
The largest unsmoothed proposed rotation step was about 168°. The angular limiter
engaged 1,358 times across all 12 bones/572 samples, and two degenerate segment
orientations were held. These are diagnostics of the proposed retarget rotations,
not a count of independently confirmed tracking failures. Low-confidence valid
landmarks are retained; occlusion and monocular depth errors can still affect poses.

Single segment directions do not resolve anatomical twist. Forearm/upper-arm roll,
shoulder deformation, and elbow orientation may need manual cleanup. No hand/fist,
weapon, head, foot-orientation or finger capture is implemented. No IK/contact
constraints are used; expect foot sliding/floating and possible limb intersections.
Stationary hips mean no reconstructed body travel or squat-height translation.

The reproducible script is `blender/retarget_mixamo.py`. It expects the confirmed
input object names and refuses to overwrite an existing result. To make another
variant, choose a new output filename in the script. Run against the original
input, not the already-renamed result. `check_retarget_result.py` reopens/checks
the result and writes preview images, without resaving the `.blend`.
