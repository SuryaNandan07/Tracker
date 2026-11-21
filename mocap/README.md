# Phase 1 motion capture

Experimental Blender skeleton visualization is available separately: see
[`../blender/README.md`](../blender/README.md) for the JSON exporter and standalone
Blender import script. It does not change capture/playback or implement retargeting.

Independent of the older fitness scripts. No Unity or Blender integration is included.

## Ready-to-run commands (PowerShell, project root)

```powershell
cd 'C:\Epic Gamez\tracker'
.\.venv-mocap\Scripts\python.exe -m mocap.capture --name sword_attack_001
.\.venv-mocap\Scripts\python.exe -m mocap.playback --recording sword_attack_001
```

Focus the camera window: **R** starts a take on the next frame; **S** saves;
**Q**, closing the window, Ctrl+C, or a camera failure saves a nonempty active take
and releases resources. R during recording does nothing. You can record several
takes in one session. Stand far enough away that your full body is visible.
Add `--camera 1` for another camera or `--no-video` to disable the reference MP4.
Playback: **Space** pauses/resumes, **R** restarts, **Q** exits. At the end it
holds the last frame. Missing poses display a blank skeleton frame and NO POSE.

In PyCharm choose the existing interpreter
`C:\Epic Gamez\tracker\.venv-mocap\Scripts\python.exe`.
Create Python run configurations using **Module name** `mocap.capture` or
`mocap.playback`, working directory `C:\Epic Gamez\tracker`, and the arguments
above. Do not use “Script path” on the package files; their relative imports
require module execution. Once this interpreter is active, plain
`python -m mocap.capture --name sword_attack_001` works too.

## Extract motion from an existing video

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.capture --video "Videos\fighting.webm" --name sword_combo_001
.\.venv-mocap\Scripts\python.exe -m mocap.playback --recording sword_combo_001
```

Video mode starts immediately, processes each decoded frame sequentially with the
same one-person MediaPipe pipeline, and saves automatically at the end. No R/S key
presses are needed. The preview shows the skeleton, frame count and source time;
Q or closing the preview saves the processed prefix. Preview is fitted to the
screen; input frames are not resized by this adapter. Processing runs as fast as
inference permits, rather than playing at the video's frame rate.

For unattended processing with no windows or GUI calls:

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.capture --video "Videos\fighting.webm" --name sword_combo_001 --headless --progress
```

`--progress` prints updates about every two seconds. `--no-video` omits the
reference copy. `--camera`, `--width` and `--height` apply only to webcam mode;
video mode preserves the decoded source dimensions. No new dependencies are needed.

Video timing uses OpenCV `CAP_PROP_POS_MSEC` after each successful frame read.
Finite, nonnegative, strictly increasing timestamps are accepted, including variable
frame intervals and a nonzero first timestamp. NPZ timestamps subtract the first
saved timestamp so playback starts at zero. JSON retains `first_frame_source_ms`.
Inference speed never affects saved motion timing. The separate integer timestamp
passed to MediaPipe is raised to the previous integer + 1 when necessary; the
floating-point NPZ timestamps are not quantized to match it.

If a timestamp is missing/nonfinite, negative, repeated or decreasing, all remaining
frames use a fixed `1000/FPS` interval anchored at the last accepted timestamp
(or zero if the first timestamp is invalid). FPS comes from the file's reported rate,
overridden by `--fallback-fps`. There is no silent 30-FPS guess. If no valid rate is
available when fallback is needed, processing stops with setup instructions and
saves any processed prefix. To override timestamps that appear increasing but are
known to be incorrect, force FPS timing explicitly:

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.capture --video "Videos\fighting.webm" --name sword_combo_fps --headless --timestamp-mode fps --fallback-fps 60
```

`--fallback-fps 60` alone still prefers valid source timestamps. In forced FPS mode,
frame zero is at zero and subsequent frames advance by 1000/60 ms. JSON
`config.timing` records the selected mode, rate, fallback start/reason, source/FPS
frame counts, and integer inference-time adjustments. Automatic reliability checks
cannot detect every incorrect timestamp; FPS fallback approximates timing for VFR
files and cannot reconstruct missing original presentation timestamps.

The reference is a **byte-for-byte copy** of the entire original file, named
`reference.webm`, `reference.mp4`, or the corresponding source extension. Original
resolution, codec, timing and audio are preserved; the source is opened read-only.
The file path is recorded in the existing `files.video` field. A cancelled or failed
take still contains a full source copy but only the decoded prefix of landmarks;
`config.processing.status` distinguishes cancellation, interruption, errors,
end-of-stream, and end-of-stream with a frame-count mismatch. Every take uses a
new UUID directory.

Missing poses keep NaNs and False validity flags, just like webcam recordings.
Invalid paths, empty files and unsupported/corrupt inputs produce terminal errors.
At the first failed read, processing stops instead of seeking past/skipping damage.
If the decoded frame count differs from OpenCV's reported count, a warning reports
unverified completeness and saves the decoded frames with status
`end_of_stream_count_mismatch`. Count mismatch alone is not a fatal error because
the reported count may be estimated; it does not prove that frames were lost.
OpenCV cannot always distinguish EOF from
a decode error, and frame counts can be approximate, particularly for VFR video;
an end-of-stream status is not proof of an undamaged input. Decoder-internal frame
loss cannot be reliably detected by this API. No unreadable frames are invented.

NPZ arrays and SQLite schema are unchanged. The JSON retains its existing structure
and adds video source, timing and processing details. Old webcam recordings still
load unchanged; the playback module needs no modifications or MediaPipe inference.

## Setup on a fresh machine

Tested with Python 3.11.9, MediaPipe 0.10.35, NumPy 2.4.6, and OpenCV contrib
4.14.0.94. SQLite, JSON and unittest are part of Python. Only one OpenCV wheel
should be installed in this environment; do not also add opencv-python or a
headless wheel. MediaPipe brings some additional dependencies, including Matplotlib.

```powershell
py -3.11 -m venv .venv-mocap
.\.venv-mocap\Scripts\python.exe -m pip install -r requirements-mocap.txt
.\.venv-mocap\Scripts\python.exe -m mocap.setup_model
```

The downloader retrieves Google's versioned **full pose** model, verifies its
bundle members, and refuses overwrites. It is already downloaded for this workspace.
`face_landmarker.task` is not usable for pose capture. `--model PATH` can select
another compatible pose model. Setup/model errors print actionable messages.

Official reference: [MediaPipe Pose Landmarker Python guide](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python).
Model URL: <https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task>.
Downloaded SHA256: `5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1`.

## Saved data and portability

Defaults resolve relative to the package's parent, independent of the launch directory.
Each take is `recordings/<safe-name>_<uuid>/`, containing `landmarks.npz`,
`metadata.json`, and, by default, unannotated `reference.mp4` for webcam takes
or the original-format reference copy for file input.
`mocap.db` indexes ID, name, creation time, duration, count, directory, and the
full metadata JSON (camera, frame rates, model path/hash/version, configuration,
and relative file paths). These are created as needed. Reusing a name creates a
new take. Playback by name chooses the newest matching take and announces ambiguity.
Use a full UUID, directory, or NPZ path to select a specific recording.

```powershell
.\.venv-mocap\Scripts\python.exe -m mocap.playback --recording sword_attack_001 --inspect
```

Playback validates NPZ using `allow_pickle=False` and never imports MediaPipe.
It works without a model, without a webcam, and without SQLite if the recording
files exist. Both CLIs accept `--recordings PATH` and `--database PATH`.
Copy `mocap/`, `requirements-mocap.txt`, and your recordings into a new project
to move the pipeline; recreate the virtual environment rather than copying it.
Metadata file paths are relative; stale absolute SQLite paths are not required
for name/ID resolution in the new recordings directory.

NPZ schema (N = captured/processed frames):

| Array | Shape | Type |
|---|---|---|
| image_landmarks, world_landmarks | N × 33 × 3 | float32 |
| visibility, presence | N × 33 | float32, image result scores |
| world_visibility, world_presence | N × 33 | float32, world result scores |
| timestamps_ms | N | float64 |
| frame_indices | N | int64, capture-session frame indices |
| valid_mask | N | bool |

No detection means False and NaN coordinates/scores, never zeros or deleted rows.
Unavailable per-joint values are NaN. Low-confidence predictions remain untouched;
only visualization hides points below 0.3 visibility. JSON records all 33 landmark
names, joint connections, schema version, configuration and coordinate conventions.

Image coordinates are unmirrored: x increases right, y down, normalized by image
width/height; predictions may extend outside [0,1]. Image z is hip-relative depth
with smaller values nearer the camera, approximately on the x scale, not meters.
World coordinates are raw MediaPipe meter estimates centered between the hips.
They are not calibrated global positions; no axis conversion to Blender/Unity is
applied. Preserve this distinction for later reconstruction/retargeting.

Webcam capture uses synchronous Tasks VIDEO mode with one pose so every processed camera
frame receives a result. Acquisition time is sampled immediately after `read()`
and before inference using a monotonic clock. Saved timestamps start at zero at
the first recorded frame. MediaPipe gets strictly increasing integer milliseconds;
the original floating timestamps are preserved independently. JSON includes the
session monotonic origin and UTC creation time. These are not camera hardware
timestamps and do not yet provide synchronization across devices.

The webcam MP4 stores one unannotated frame per NPZ row at a constant encoder FPS (camera
reported FPS, falling back to 30; override with `--video-fps`). It may play faster
than real time when inference is slow. NPZ timestamps are the timing authority;
skeleton playback uses them and preserves every frame in order. Metadata includes
measured processed FPS and encoder FPS. Playback preserves camera aspect ratio
when metadata is present; an NPZ alone uses a 16:9 canvas.

## Verification and manual acceptance

Verified on 2026-10-11: **21/21 automated tests passed** in the isolated environment.
The earlier environment `pip check` found no broken requirements (no dependencies
were changed for video support). The original real-model smoke test passed with
**12/12 detected poses** and 12 successfully decoded reference-video frames.
CLI help was also checked. Live webcam/UI acceptance remains unverified.

The actual `Videos/fighting.webm` was also processed headlessly with real MediaPipe:
572 decoded frames, 570 valid poses, two missing-pose frames, 1080×1920 resolution,
and 9517 ms from first to last landmark frame. All saved frame indices are consecutive;
all 572 timestamps came from source PTS without fallback. Reference-copy hashes match
the source, NPZ loads through existing playback, and SQLite contains the frame count.
An independent `ffprobe -count_frames` check confirmed **572** video frames. OpenCV's
reported total of 574 is approximate for this file; the resulting count-mismatch
warning is expected. FFprobe was used only for verification and is not a dependency.
The initial validation take and final take have separate UUIDs; lookup by name selects
the newest. Earlier takes were not overwritten.

```powershell
.\.venv-mocap\Scripts\python.exe -m unittest discover -s mocap/tests -v
.\.venv-mocap\Scripts\python.exe -m pip check
.\.venv-mocap\Scripts\python.exe -m mocap.tests.smoke_video --video male-Bodyweight-push-up-side.mp4
```

The unit tests cover NPZ shapes, exact timestamps and indices, NaNs, unavailable
scores, SQLite lookup, metadata, collision-safe saves, invalid input rejection,
model-independent playback loading, capture controls, and camera-failure cleanup.
Video tests generate a six-frame MP4, decode it through the production file adapter
with deterministic inference results, and check frame order, timestamps, missing
poses, confidence values, reference-copy equality, source immutability, SQLite and
playback compatibility, forced fallback, and absence of GUI calls in headless mode.
Additional tests cover VFR timestamp preservation, integer inference monotonicity,
unreliable timestamps, unknown FPS, invalid/empty/unsupported files and early read failure.
The optional smoke test runs real inference on 12 frames of an existing video,
draws skeletons, writes/decodes an MP4, and round-trips NPZ/SQLite in temporary
storage. It does not modify the source video or create permanent recordings.

Manual webcam acceptance (still required):

1. Run capture in PyCharm or PowerShell. Check skeleton alignment and full-body framing.
2. Press R, move for 5–10 seconds, briefly leave the frame, then press S.
3. Record another take with the same name. Confirm two different directories exist.
4. Press Q. Confirm another app can now open the webcam.
5. Replay a saved take; check movement, elapsed timing and blank missing-pose frames.
6. Test Space, R and Q. Use `--inspect` to inspect count, duration and valid poses.
7. Open reference.mp4 and compare frame order; its constant-FPS duration can differ.
8. Try quitting during a take and confirm it is saved and resources are released.

If the camera fails, close other camera apps and enable Windows camera access for
desktop apps; try `--camera 1`. Codec failure can be bypassed with `--no-video`.
The Codex sandbox blocked a Matplotlib DLL via application control; import and
the real smoke test succeeded outside the sandbox. This was a sandbox-specific
test limitation, not a dependency-resolution error.

## Limits and next steps

Live webcam recording and interactive preview/playback have not been manually
verified here. Monocular estimates can jitter or confuse occluded limbs and do
not capture detailed fingers, weapons, global root motion, or accurate joint rotations.
Camera-driver frames lost between reads cannot be recovered; read failure ends
the take. All processed frames, including no-pose results, are retained.
Memory use grows with take duration because landmark rows are buffered until save;
use short cinematic takes. Hard termination/power failure can lose buffered landmarks
or leave a partial MP4; this phase has no crash-recovery journal. Save I/O failures
report the partial directory. SQLite failures leave JSON/NPZ available for playback.

Next: complete webcam acceptance, inspect real motion quality and timing, then plan
smoothing, calibration and Blender retargeting as a separate phase. Two-camera
synchronization, reconstruction, smoothing/interpolation, bone corrections, FBX
and Unity integration are deliberately not implemented.

## Files and inspection findings

Created `mocap/{__init__,config,capture,storage,database,playback,drawing,setup_model}.py`,
this README, `mocap/tests/`, `requirements-mocap.txt`, `.gitignore`, the downloaded
model, and the isolated `.venv-mocap`. Recordings and the database are runtime outputs.
The ignore file excludes virtual environments, recordings, database files and model
downloads from version control.

Existing scripts use YOLO; `main.py` also contains a commented legacy MediaPipe
Solutions example. Importing the old scripts would execute their tracking loops,
so the new package reuses the OpenCV capture/display pattern without importing them.
The old `.venv` references Python 3.14.6 under another user's inaccessible path;
its package metadata lists MediaPipe 0.10.35 and both OpenCV distributions. It was
left untouched. No existing scripts/assets were changed, and no Unity folder was accessed.

Video-input extension: modified `capture.py` (CLI and shared inference helpers),
`storage.py` (reference extension and source-time metadata), and this README;
added `video.py` (input adapter/timing) and `tests/test_video.py`. Playback, database
schema, fitness scripts, old recordings, and Unity files are unchanged.
