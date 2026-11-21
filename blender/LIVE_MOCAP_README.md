# Live webcam Mixamo experiment

Open **`C:\Epic Gamez\tracker\blender_projects\experiments\Humanoid_Live_Mocap.blend`** in Blender 5.1.2.

The interrupted migration did not relocate the existing projects or exports. This
experiment was created from `C:\Epic Gamez\tracker\Humanoid_Mocap_Result.blend`.
The existing Python package, models, recordings, SQLite database and offline
scripts remain in their original locations. Only this new experiment uses the
`blender_projects\experiments` directory. No existing project was overwritten.

## Start in Blender

1. Open the new file. Keep the Timeline **paused**: live updates do not require Play.
2. In the **Scripting** workspace, select `LIVE_MOCAP_START.py` from the Text Editor's
   text dropdown and click **Run Script** (Alt+P with the mouse over that editor).
3. Return to the Layout workspace to watch the character. The receiver listens on
   `127.0.0.1:50123`. It does not run automatically when the file opens.
4. Start the Python sender below. Stand far enough away for **both shoulders,
   elbows, wrists and hips** to be visible. A seated close-up may not provide a
   reliable torso. Use good lighting and avoid occluding the arms.

If the embedded starter is unavailable, open
`C:\Epic Gamez\tracker\blender\live_receiver.py` in Blender's Text Editor and Run Script.
Do not install MediaPipe or NumPy inside Blender.

## Run the sender from PowerShell

```powershell
Set-Location 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.live_sender --camera 0 --preview
```

For PyCharm, create a **Python** Run Configuration:

- Interpreter: `C:\Epic Gamez\tracker\.venv-mocap\Scripts\python.exe`
- Run target: **Module name** `mocap.live_sender` (not the script path)
- Parameters: `--camera 0 --preview`
- Working directory: `C:\Epic Gamez\tracker`

Press Q in the webcam preview or Ctrl+C in the terminal to release the camera.
Without `--preview` it runs without OpenCV windows. It never writes a recording.
Close other apps using the camera if it cannot be opened. Another camera can be
selected with `--camera 1`.

## Controls

In Blender's Python Console (Shift+F4 over an editor):

```python
import live_receiver as live
live.status()                  # state, accepted/rejected packets, updates, recent Hz, pose age
live.set_smoothing(0.035)       # quaternion smoothing time in seconds; 0..0.5
live.stop()                    # unregister timer, close socket, restore pose and original Action
live.restore()                 # same safe stop-and-restore operation
live.start()                   # restart; repeated starts clean up the previous receiver
```

Run the starter at least once before using those imports in the Console. Return
an editor to 3D View with Shift+F5. Status is queried on demand; no add-on UI is installed.
`update_hz` counts applied poses over the last two seconds, so startup readings
need two seconds to settle. It is not an end-to-end latency measurement.

Alternative port and threshold (use matching `--port 50124` in the sender):

```python
live.start(port=50124, smoothing=0.035, confidence=0.45)
```

For less landmark smoothing use `--tau 0.02`; stronger quiet-motion filtering can
use `--tau 0.06`. The default `--tau 0.035 --beta 2 --confidence 0.45` is conservative.
Both sender and receiver reduce smoothing during fast motion. Larger smoothing
values can introduce lag. Keep defaults for the initial trial.

If the sender stops, the character holds its last accepted pose. Use `live.stop()`
to restore it. Missing torso landmarks hold the whole pose; missing arm endpoints
hold that arm's local orientation while valid parent motion can continue.

## Safety and implementation

- Sender reuses `mocap.capture.create_detector`, `infer_frame`, the existing pose
  model and `result_arrays` pipeline. It captures sequential OpenCV webcam frames
  and exports MediaPipe's 33 **estimated world** landmarks and visibility scores.
- Protocol is bounded JSON over UDP, exclusively on loopback. It includes a session
  ID, sequence number and acquisition timestamp from the host monotonic clock.
  Missing/low-confidence joints use JSON `null`, never NaN/Infinity. Missing
  detections send an explicit heartbeat without pose coordinates.
- Coordinates convert once in Blender: `(X,Y,Z) = (x,z,-y)`. World landmarks are
  hip-centered estimates, not calibrated global motion or accurate depth.
- Sender smoothing is a causal adaptive exponential filter. Its time constant is
  reduced by estimated speed; a joint returning after >0.5 seconds starts fresh.
- Receiver reuses the offline `body_basis`, `TORSO`, `LIMBS`, and `PREFIX` mapping.
  It solves rest-relative rotations incrementally, retains quaternion hemisphere
  continuity, applies causal adaptive slerp and a 720 degrees/second reacquisition
  limit. No future frames or offline Savitzky-Golay windows are used.
- Eight mapped bones: `mixamorig:Hips`, `Spine`, `Spine1`, `Spine2`, `LeftArm`,
  `LeftForeArm`, `RightArm`, `RightForeArm`. Hips rotate but their translation and
  the armature object transform remain fixed. Legs/hands/head are not independently driven.
- Socket reads are nonblocking and bounded to 128 datagrams / approximately 3 ms
  per timer invocation. The latest accepted packet is applied; reordered, stale
  (>0.5 seconds), malformed and retired-session packets are rejected. There is
  no worker thread touching Blender data. Timers request 60 Hz; Blender load and
  detector speed determine actual rate.
- Only target pose rotations are written. The target Action is temporarily
  detached and its NLA tracks muted, then restored. No keyframes, Action edits,
  rest-pose edits, weight changes or mesh rebinding occur. Shared armature data,
  shared reference/target meshes, constraints and target drivers are rejected.
- Stop, file load, and save handlers restore the original target pose/Action and
  close the socket. Saving while live **stops live mode**; it does not bake the pose.
  Opening another project also stops the receiver. Process exit closes the socket.
  Starting Timeline playback stops the receiver to prevent competing animation.

## Validation performed

Blender 5.1.2 background tests used real localhost UDP packets derived from the
existing recording: 143 target pose updates, mesh deformation, invariant reference
pose/mesh, fixed root transform, unchanged rest rigs and all existing Action
keyframes, exact pose/Action restoration, three repeated start/stop cycles, socket
reuse, registered-timer cleanup, file-change handler cleanup and exception cleanup.
The new file was saved and reopened successfully. The measured maximum manual
receiver tick was about 2.23 ms in that test, excluding viewport rendering and
camera/inference latency; this is not an interactive frame-rate claim.

The actual MediaPipe sender processed 30 fighting-video frames with 30 detections
and delivered all 30 packets to an independent UDP listener. A brief actual webcam
test delivered 30 packets, but **no person was detected**. Camera access and missing-
pose handling passed; raising arms in front of the camera remains to be verified.

Automated protocol/filter tests and the existing regression suite cover recording,
playback, export and offline smoothing. Reports are new files under
`C:\Epic Gamez\tracker\reports\live_*.json`.

**Not verified:** interactive Blender viewport responsiveness, subjective latency,
or a person controlling the character with the webcam. No claim of visual live
success is made. Background timer callbacks were invoked on Blender's main thread;
the interactive event loop still needs your trial.

Expect monocular depth noise, occlusion holds, some limb roll/twist ambiguity,
and clipping during crossed-arm motions. There is no calibrated twist, IK, foot
contact, root locomotion, recording/baking or multi-camera support in this prototype.

## Repeatable tests

```powershell
.\.venv-mocap\Scripts\python.exe -B -m unittest discover -s mocap/tests -v
```

`mocap.tests.live_sender_smoke`, `blender/validate_live.py` and
`blender/validate_live_lifecycle.py` refuse to replace their existing report/project
outputs. To repeat integration tests, use reviewed new output names in copies of
the validation scripts. Do not delete prior outputs just to rerun them.

The embedded starter depends on this project staying at its current path and on
the external `blender/live_receiver.py`, `blender/retarget_mixamo.py` and
`mocap/live_protocol.py` files. Update the starter if a future approved migration
moves the project. Existing Blender experiments have not been relocated.
