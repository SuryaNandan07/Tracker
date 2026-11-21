# Experimental Blender skeleton viewer

This is a 33-joint motion visualization, not an armature or retargeting system.
The existing capture, recordings, database, fitness scripts and Unity project are
not changed. The exporter needs the existing mocap environment; the importer runs
inside Blender using Blender's Python and standard library only.

## 1. Export the recording

From PowerShell:

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.export_blender --recording sword_combo_001 --output "exports\sword_combo_001.json"
```

The JSON has already been generated at
`C:\Epic Gamez\tracker\exports\sword_combo_001.json` for the current recording.
The exporter refuses to overwrite existing exports; choose a different `--output`
name for another run and update `JSON_PATH` in the Blender script. If several takes
share a name, the newest is selected with a message; a recording UUID or full
directory/NPZ path selects an exact take.

The current take is `7589f764fb134df8a20c4ab130f26cf4`: 572 samples, 570 detected
poses, missing detections at zero-based rows 174 and 431, and 9517 ms from first to
last sample. Its source is `Videos/fighting.webm`; source timing and confidence
values come directly from the saved recording, with no new inference.

## 2. Import in Blender

The prepared scene is also available directly at
`C:\Epic Gamez\tracker\exports\sword_combo_001.blend`. Open it and press Play;
the instructions below are for rebuilding the scene from JSON.

1. Open Blender (the script targets Blender 4.x and 5.x; use a recent release).
2. Switch to the **Scripting** workspace.
3. In the Text Editor choose **Text → Open**, then open
   `C:\Epic Gamez\tracker\blender\import_mocap.py`.
4. Check the settings near the top:

   ```python
   JSON_PATH = r'C:\Epic Gamez\tracker\exports\sword_combo_001.json'
   FPS = 60
   SHOW_JOINT_NAMES = False
   ```

5. Click **Run Script** (the triangle button in the Text Editor).
6. Switch to **Layout**. The active scene is now `Mocap_sword_combo_001`.
   Click the Timeline's **Play** button or press Space with the pointer over the
   3D viewport. The range is set automatically to cover the source duration.
7. Orbit with the middle mouse button to inspect depth. Numpad 1 restores a front
   view; select the joints in the Outliner and use Numpad `.` / **View → Frame
   Selected** if necessary. Use Solid shading with Color set to Material.
8. Save a `.blend` file manually if you want to keep the imported scene.

Each run creates a **new scene**, collection and animation; it never clears your
existing scene or saves over a `.blend` file. The script adjusts viewport framing
and solid shading for easier inspection. Existing scenes can be selected again
using Blender's Scene selector. Remove unwanted experimental scenes manually.

Left joints are blue, right joints orange, and central joints/connections yellow.
Markers are named with their original index and landmark name. They have custom
properties for joint identity and missing-sample count. Set `SHOW_JOINT_NAMES`
before running if you want labels. Missing whole-pose samples are marked on the
Timeline (rounded to the nearest display frame); the JSON retains exact times.
Connections are beveled curves whose endpoint drivers follow the animated markers.
They are visual links, not fixed-length anatomical bones. There are no cameras,
lights, textures or render/export setup because the purpose is viewport inspection.

## Coordinates and limitations

The exporter uses **world_landmarks**, not the normalized image landmarks. These
are MediaPipe's monocular estimates in meters with a hip-midpoint origin. Their
depth/scale are approximate, and they do not recover where the person travels in
the room. Expect the skeleton to move mostly in place. Occlusion, fast actions,
camera cuts, changing subjects and uncertain depth can cause visible jitter or
unphysical limb motion. Hands/weapons are not reconstructed in detail.

The explicit visualization basis conversion is:

```text
Blender X =  MediaPipe x
Blender Y =  MediaPipe z
Blender Z = -MediaPipe y
```

This is a rotation about X by -90 degrees, with determinant +1 (no reflection).
The assumed MediaPipe camera-style axes are x right, y down and depth z; the
Blender display is Z-up, with depth along Y. This is a display convention, not a
calibrated camera-to-world transformation. There is no automatic floor alignment,
scaling, recentering, or root translation beyond MediaPipe's existing hip origin.
The hips remain around Blender's origin, so the feet can sit below its grid.

JSON stores both original world coordinates and converted Blender coordinates,
all timestamps/frame indices, the original joint ordering/connections, frame and
joint validity flags, available visibility/presence arrays, source metadata and
an NPZ hash. Missing scalar values are standard JSON `null`, never zero or NaN
tokens. No valid samples are discarded or confidence-filtered by the exporter.
Source recordings remain the raw authority and are opened read-only.

## Timing and missing data

Each saved sample gets a keyframe at:

```text
Blender frame = 1 + (timestamp_ms - first_timestamp_ms) × FPS / 1000
```

Fractional frame positions are kept, so unequal source intervals are retained.
FPS defaults to 60 but changing it changes frame numbering, not motion duration.
Blender evaluates at its display frame rate; the script does not claim each sample
will appear as a distinct displayed frame. The last timeline frame is rounded up,
adding at most one frame of final hold. Frame 572.02 is the final sample of this
recording at 60 FPS; the end frame is therefore 573.

Only the **importer's preview tracks** fill missing values. For each joint:

- Complete valid samples retain their converted positions exactly.
- Interior gaps interpolate linearly between the nearest valid samples using
  timestamp distances (not row numbers).
- Leading/trailing gaps hold the nearest observed position.
- A joint never observed is created but hidden, along with its connections.

All animation F-curves use LINEAR interpolation and constant extrapolation to
avoid default Bezier overshoot. The raw JSON is never filled or rewritten.
This prevents jumps to zero on missing frames; it cannot remove jumps already in
valid detections. Long gaps are also interpolated and can invent implausible motion;
this is an explicitly experimental visualization, not reconstructed ground truth.
An entirely missing recording is rejected before creating a Blender scene.

## Validation

Verified in the existing `.venv-mocap`: **26/26 tests passed**, including the five
new export/import-data tests and all prior capture/storage/video tests. The real
JSON export was compared with every source world-coordinate, confidence, timestamp,
frame-index and validity array; values and missing information match. Its 33
preview tracks contain 572 finite positions each and use 35 skeleton links.
Blender 5.1.2 was subsequently found and tested directly in background mode.
`validate_import.py` imported the scene and evaluated all 572 sample times,
checking 33 marker positions and every endpoint of all 35 connections within
0.0001 meters (0.1 mm), driver validity, timeline length, and preservation of the
original scene. It saved the prepared `exports/sword_combo_001.blend` file.

To repeat the Blender execution test (without writing a scene file):

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python-exit-code 1 --python 'C:\Epic Gamez\tracker\blender\validate_import.py'
```

An optional `-- --blend-output "PATH.blend"` saves the validated scene to a new
filename; the validation script refuses to overwrite an existing file.

Run the tests with the mocap interpreter:

```powershell
.\.venv-mocap\Scripts\python.exe -m unittest discover -s mocap/tests -v
```

Tests cover strict JSON/null conversion, coordinate conversion, frame identity and
timestamps, confidence preservation, source immutability, overwrite prevention,
fractional keyframe timing, time-weighted gap filling, leading/trailing holds,
never-observed joints and invalid timing. The importer data-loading/interpolation
functions can be tested without importing `bpy`.

**Blender scene creation, animation evaluation and curve drivers were tested in
Blender 5.1.2. Interactive viewport playback has not been manually verified.** The action code uses
legacy F-curves on Blender 4.0–4.3 and slotted actions on 4.4+/5.x. The first manual
acceptance check is: 33 colored markers plus connections appear, the timeline plays
for about 9.52 seconds, and the two missing detections cause no jump to the origin.

Reference documentation:
[MediaPipe Pose](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker),
[Blender animation API](https://docs.blender.org/api/main/info_quickstart.html#animation),
[Blender slotted actions](https://developer.blender.org/docs/release_notes/4.4/upgrading/slotted_actions/).

No retargeting, FBX, multi-camera features, Blender add-on interface or character
rigging is included. Inspect the estimated motion first before planning those steps.
