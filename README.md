# AI Exercise and Motion-Capture Tracker

This repository contains two related but separate projects:

1. **Exercise tracking** – YOLO/OpenCV desktop programs that detect a person's pose and count or coach squats and push-ups.
2. **Blender motion capture and retargeting** – MediaPipe/OpenCV tools that capture or process human motion, save it, preview it, export it, and apply it to a Mixamo-style humanoid in Blender.

The projects share OpenCV and pose-estimation models but have separate workflows and data formats. The exercise scripts do not write recordings to the motion-capture database, and Blender's Python environment is not the same as the project virtual environment.

---

## Project structure

```text
tracker/
├── requirements.txt                 # Common Python dependencies and YOLO exercise dependencies
├── requirements-mocap.txt           # MediaPipe motion-capture environment
├── mocap/                           # Capture, playback, storage, export and live-network packages
├── mocap/tests/                     # Automated motion-capture tests
├── blender/                         # Blender import, retargeting, smoothing and validation scripts
├── blender_projects/                # Blender project variants and experiments
├── exports/                         # Exported JSON, phase motion data and rendered previews
├── recordings/                      # Saved webcam/video captures
├── Videos/                          # Example source videos
├── pushups.py                       # Push-up form tracker
├── squarts.py                       # Squat form tracker
├── main2.py                         # Basic webcam push-up counter
├── main.py                          # Legacy/experimental MediaPipe example
├── tracker.py                       # Basic YOLO body tracker
├── 2.py                             # Basic YOLO video tracker
└── newquarts.py                     # YOLO squat or pose experiment
```

Models such as `yolov8n-pose.pt` and `yolov8s-pose.pt` are used by the exercise scripts. `face_landmarker.task` is a face model and is not used for motion capture; MediaPipe pose setup downloads `pose_landmarker_full.task` into `mocap/models/`.

---

# 1. Exercise tracking project

The exercise programs use YOLO pose estimation and OpenCV to detect body keypoints in a live webcam feed or in a local video. They estimate joints, show an annotated skeleton, track repetition stages, and provide simple form feedback.

## Supported exercises

### Squats

- Tracks left-side shoulder, hip, knee and ankle landmarks.
- Uses the knee angle to distinguish up, down and rising stages.
- Counts a repetition after reaching the bottom and rising above the up threshold.
- Reports half squats, knees too far forward, chest/torso lean and excessive depth.
- The main implementation is `squarts.py`.

### Push-ups

- Tracks right-side shoulder, elbow and wrist landmarks.
- Uses the elbow angle to determine the up and down stages.
- Counts repetitions when a sufficiently low position is followed by extension.
- Checks body alignment and may warn to raise the hips or go lower.
- The main implementations are `pushups.py` and `main2.py`.

## Exercise setup

Use Python 3.10 or 3.11 on Windows. Create a dedicated environment:

```powershell
cd 'C:\Epic Gamez\tracker'
py -3.11 -m venv .venv-exercise
.\.venv-exercise\Scripts\python.exe -m pip install --upgrade pip
.\.venv-exercise\Scripts\python.exe -m pip install -r requirements.txt
```

The first YOLO run can download model weights if a model is missing. The pose model files currently included in the project are `yolov8n-pose.pt` and `yolov8s-pose.pt`.

## Exercise starting commands

### Squat coach

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-exercise\Scripts\python.exe .\squarts.py
```

This script currently opens `How to squat correctly.webm`. To use the webcam instead, uncomment `cv2.VideoCapture(0)` and comment out the video path in the script.

### Push-up coach

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-exercise\Scripts\python.exe .\pushups.py
```

The full push-up script currently opens `male-Bodyweight-push-up-side.mp4`. Stand sideways to the camera for a side-view push-up. To use the webcam, change the `cv2.VideoCapture(...)` line to `cv2.VideoCapture(0)`.

### Simple push-up counter

```powershell
.\.venv-exercise\Scripts\python.exe .\main2.py
```

`main2.py` is a simpler webcam-oriented push-up prototype. It currently loads `yolov8n-pose.pt` and opens the webcam.

### Other experimental scripts

```powershell
.\.venv-exercise\Scripts\python.exe .\tracker.py
.\.venv-exercise\Scripts\python.exe .\2.py
.\.venv-exercise\Scripts\python.exe .\newquarts.py
```

These are experimental or early tracker implementations. Their video source and camera settings are defined near the top of each file and may need editing before use. Exit every OpenCV window with `Q`.

## Exercise controls and output

- OpenCV displays an annotated video window.
- Press `Q` to stop and release the capture.
- Green overlays indicate normal tracking/form.
- Red overlays indicate the script's form warning.
- The displayed count is updated during `DOWN`/`UP` state transitions.
- Results are shown only in the desktop window; there is no database or browser UI.

## Exercise limitations

- Side-view assumptions are used for push-ups and most angle calculations.
- YOLO keypoints and 2D camera angles are sensitive to crop, lighting and occlusion.
- The scripts do not use calibrated biomechanics or 3D ground-truth measurements.
- Mirror flips, multiple people and poor camera placement can affect landmark selection.
- A recording reaching the last frame ends the script.
- Form feedback is heuristic and should not replace coaching or medical advice.

---

# 2. Motion capture and Blender project

The motion-capture project records or processes a person's movement with MediaPipe Pose Landmarker, saves all 33 MediaPipe landmarks, and provides offline playback and Blender tools.

## Capture workflow

```text
Webcam or MP4
      ↓
MediaPipe Pose Landmarker
      ↓
NPZ landmarks + JSON metadata + SQLite index
      ↓
Playback / Blender JSON export / smoothing / retargeting
```

Typical capabilities include:

- Webcam or local-video capture.
- Headless video processing.
- 33-joint image and world landmark storage.
- Missing-pose preservation instead of deleting frames or writing zero coordinates.
- Source-reference video copies.
- Source-frame timestamp preservation and fallback FPS timing.
- Offline playback that does not require MediaPipe or a webcam.
- Skeleton JSON export for Blender.
- Experimental humanoid retargeting, smoothing and live UDP streaming.

For detailed motion-capture behavior and validation, see [mocap/README.md](mocap/README.md).

## Motion-capture setup

A Python 3.11 environment is recommended and verified by the existing documentation.

```powershell
cd 'C:\Epic Gamez\tracker'
py -3.11 -m venv .venv-mocap
.\.venv-mocap\Scripts\python.exe -m pip install --upgrade pip
.\.venv-mocap\Scripts\python.exe -m pip install -r requirements-mocap.txt
.\.venv-mocap\Scripts\python.exe -m mocap.setup_model
```

Install and open Blender 5.1 or another recent Blender 4/5 release. Blender's built-in Python is used by Blender scripts; do not install MediaPipe or NumPy into Blender.

Only one OpenCV wheel should be installed in a Python environment. Do not combine `opencv-contrib-python` with `opencv-python` or a headless OpenCV wheel.

## Motion-capture starting commands

### Capture from the webcam

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.capture --name sword_attack_001
```

- `R` starts a take.
- `S` saves the active take.
- `Q` or window close saves a nonempty take and closes resources.
- Use `--camera 1` to select another camera.
- Use `--no-video` to skip recording the reference MP4.

### Process an existing video

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.capture --video 'Videos\fighting.webm' --name sword_combo_001
```

For unattended processing:

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.capture --video 'Videos\fighting.webm' --name sword_combo_001 --headless --progress
```

### Play a saved recording

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.playback --recording sword_combo_001
```

Playback controls are:

- `Space` – pause/resume
- `R` – restart
- `Q` – exit

Use `--inspect` for a terminal summary:

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.playback --recording sword_combo_001 --inspect
```

A recording can be selected by name, UUID, recording directory or NPZ path. Names select the newest matching take and report ambiguous matches.

### Export a recording for Blender

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.export_blender --recording sword_combo_001 --output 'exports\sword_combo_001.json'
```

The export contains world and Blender-converted coordinates, timestamps, frame indices, valid masks, confidence scores and source metadata.

### Import skeleton data in Blender

1. Open the prepared `exports/sword_combo_001.blend`, or open Blender and create a scene.
2. Open `blender/import_mocap.py` in Blender's Scripting workspace.
3. Set `JSON_PATH` to `C:\Epic Gamez\tracker\exports\sword_combo_001.json` if needed.
4. Run the script.
5. Press `Space` or use the Timeline to play the generated skeleton scene.

The importer creates a separate scene and collection; it does not overwrite existing Blender scenes or `.blend` files.

For a command-line Blender import/validation check:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe' --background --factory-startup --python-exit-code 1 --python 'C:\Epic Gamez\tracker\blender\validate_import.py'
```

## Retargeted Blender projects

Existing project files can be opened directly:

```text
Humanoid_Mocap_Result.blend       # Initial experimental retarget
Humanoid_Mocap_Smoothed.blend     # Jitter-reduced retarget
Humanoid_Mocap_Natural.blend      # Natural Phase 2 preset
Humanoid_Mocap_Balanced.blend     # Recommended balanced preset
Humanoid_Mocap_Cinematic.blend    # Stronger cinematic smoothing preset
Humanoid_Retarget_Test.blend      # Retarget source/test scene
```

Open a file in Blender and press `Space` over the viewport or use Timeline Play.
The Balanced preset is the recommended starting point for quiet-motion stability. These presets are experimental and do not reconstruct accurate feet, hands, weapon motion or body travel.

For retargeting details, see [blender/RETARGET_README.md](blender/RETARGET_README.md). For smoothing details, see [blender/SMOOTHING_README.md](blender/SMOOTHING_README.md) and [blender/PHASE2_README.md](blender/PHASE2_README.md).

## Live Blender motion

A live camera-to-Blender prototype sends pose packets over UDP from Python to Blender:

1. Open `blender_projects/experiments/Humanoid_Live_Mocap.blend` in Blender 5.1.
2. In Blender's Scripting workspace, open and run `LIVE_MOCAP_START.py`, or run `blender/live_receiver.py`.
3. In PowerShell, start the sender:

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.live_sender --camera 0 --preview
```

Press `Q` in the sender preview or `Ctrl+C` in the terminal to stop. The receiver listens on `127.0.0.1:50123` only. It holds the last pose when detection or packets are missing.

See [blender/LIVE_MOCAP_README.md](blender/LIVE_MOCAP_README.md) for controls, protocol behavior and validation limits.

## Saved motion data

A capture take is stored in `recordings/<safe-name>_<uuid>/` and normally contains:

- `landmarks.npz` – image and world landmarks, visibility, presence, timestamps and valid masks.
- `metadata.json` – source, timing, camera, model, processing and coordinate metadata.
- `reference.mp4` or an original-format reference copy.

The SQLite database `mocap.db` indexes recordings and full metadata. Playback and UUID lookups can use the recording files even if the database is unavailable. Relative metadata paths make copied recording directories portable.

### NPZ landmark arrays

| Array | Shape | Meaning |
|---|---:|---|
| `image_landmarks` | N × 33 × 3 | Normalized image coordinates; z is relative depth |
| `world_landmarks` | N × 33 × 3 | MediaPipe world estimates in meters |
| `visibility` | N × 33 | Landmark visibility scores |
| `presence` | N × 33 | Landmark presence scores |
| `world_visibility` | N × 33 | World visibility scores |
| `world_presence` | N × 33 | World presence scores |
| `timestamps_ms` | N | Capture/playback timestamp in milliseconds |
| `frame_indices` | N | Camera/video frame indices |
| `valid_mask` | N × 33 | Whether each joint is available |

No pose or unavailable joint is written as zero coordinates. Missing detections keep `NaN` coordinates and `False` validity flags.

---

## Coordinate conventions

MediaPipe image coordinates use x increasing right and y increasing down. World landmarks are monocular hip-centered meter estimates, not calibrated room coordinates or tracked global translation.

For Blender visualization, the project converts coordinates using:

```text
Blender X = MediaPipe x
Blender Y = MediaPipe z
Blender Z = -MediaPipe y
```

This is a display-space conversion, not a calibrated camera rig transformation. The Blender importer and retargeter do not infer accurate walking paths, floor contact or 3D scene depth.

---

## Tests

Run the automated motion-capture suite with the mocap environment:

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m unittest discover -s mocap/tests -v
.\.venv-mocap\Scripts\python.exe -m pip check
```

The tests cover capture, NPZ/SQLite storage, metadata, timestamp handling, missing poses, playback, video inputs, JSON export, smoothing, live protocol behavior and Blender integration scripts.

Optional real-media smoke tests can exercise capture and inference; use existing source videos and temporary output paths so permanent recordings are not changed.

---

## Dependencies

- **Python**: 3.11 recommended.
- **NumPy**: array calculations and motion data.
- **OpenCV**: camera capture, video decode and preview windows.
- **Ultralytics YOLO**: exercise pose detection.
- **MediaPipe**: 33-landmark motion-capture pose inference.
- **SQLite**: standard Python database support for recording indexes.
- **Blender 4.x or 5.x**: skeleton viewing and humanoid retargeting.
- **Matplotlib**: may be brought in by MediaPipe-related dependencies.

Install the exercise project with `requirements.txt` and the motion-capture project with `requirements-mocap.txt`.

---

## Known limitations

- Exercise counts and form feedback are heuristic 2D estimates.
- Pose keypoints depend on camera angle, lighting and occlusion.
- MediaPipe monocular depth and world coordinates are approximate.
- Retargeted motion may slide, float or produce twisted limbs.
- No accurate hand/finger/weapon, foot-contact, head, eye or global locomotion reconstruction is implemented.
- Live capture is a prototype and is not a medically, biomechanically or scientifically validated system.
- The repository includes experimental scripts and several Blender file variants; use new output paths instead of overwriting checked project files.

## License and safety

No explicit license file is currently included; do not redistribute this repository or third-party models and videos unless you have the necessary rights. Exercise feedback is not medical advice. Stop if a user experiences pain or dizziness.

## Detailed documentation

- [Motion-capture package](mocap/README.md)
- [Blender skeleton viewer](blender/README.md)
- [Offline retargeting](blender/RETARGET_README.md)
- [Offline smoothing](blender/SMOOTHING_README.md)
- [Phase 2 smoothing presets](blender/PHASE2_README.md)
- [Live Blender mocap](blender/LIVE_MOCAP_README.md)
