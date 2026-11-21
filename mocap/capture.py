"""Record webcam motion or extract a local video using the same pose pipeline."""
import argparse
import hashlib
import math
import time
from pathlib import Path

from .config import MODEL, RECORDINGS, DATABASE
from .database import Database
from .storage import Recording, result_arrays
from .drawing import draw_skeleton


def create_detector(args, mp):
    """Shared Tasks configuration for webcam and sequential file inference."""
    if not args.model.is_file():
        raise FileNotFoundError(f'Pose model missing: {args.model}. Run python -m mocap.setup_model')
    if 'face' in args.model.name.lower():
        raise ValueError('A face landmarker is not a pose model. Run python -m mocap.setup_model')
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5)
    return mp.tasks.vision.PoseLandmarker.create_from_options(options)


def model_metadata(args, mp):
    return {'path': str(args.model.resolve()),
            'sha256': hashlib.sha256(args.model.read_bytes()).hexdigest(),
            'mediapipe_version': mp.__version__, 'running_mode': 'VIDEO',
            'num_poses': 1, 'detection_confidence': .5,
            'presence_confidence': .5, 'tracking_confidence': .5}


def infer_frame(detector, frame, timestamp_ms, cv2, mp):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = detector.detect_for_video(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)
    return result_arrays(result)


def run(args):
    if getattr(args, 'video', None) is not None:
        from .video import run_video
        return run_video(args)
    import cv2
    import mediapipe as mp
    db = Database(args.database)
    cap = None
    writer = None
    recording = None

    def finish():
        nonlocal writer, recording
        if writer is not None:
            writer.release()
            writer = None
        if recording is not None:
            completed = recording
            recording = None
            if completed.rows:
                try:
                    print(f'Saved: {completed.save(db)}', flush=True)
                except Exception:
                    print(f'Save failed; any partial files remain at {completed.directory}', flush=True)
                    raise
            else:
                print(f'No frames recorded; empty take directory: {completed.directory}')

    try:
        with create_detector(args, mp) as detector:
            cap = cv2.VideoCapture(args.camera)
            if not cap.isOpened():
                raise RuntimeError(f'Cannot open webcam {args.camera}. Check camera permissions and other apps.')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            reported_fps = float(cap.get(cv2.CAP_PROP_FPS))
            reported_fps = reported_fps if math.isfinite(reported_fps) and reported_fps > 0 else None
            video_fps = args.video_fps or reported_fps or 30.0
            model_info = model_metadata(args, mp)
            start = time.perf_counter_ns()
            last_inference_ms = -1
            frame_index = 0
            print('Ready: R = record, S = stop/save, Q = save/exit. Focus the preview window.', flush=True)
            while True:
                ok, frame = cap.read()
                acquired_ms = (time.perf_counter_ns() - start) / 1e6
                if not ok:
                    raise RuntimeError('Webcam stopped delivering frames; saving the current take.')
                inference_ms = max(last_inference_ms + 1, int(acquired_ms))
                last_inference_ms = inference_ms
                sample = infer_frame(detector, frame, inference_ms, cv2, mp)
                if recording is not None:
                    recording.append(sample, acquired_ms, frame_index)
                    if writer is not None:
                        writer.write(frame)
                preview = frame.copy()
                draw_skeleton(preview, sample['image_landmarks'], sample['visibility'])
                status = 'READY'
                if recording is not None:
                    duration = recording.rows[-1]['timestamps_ms']/1000 if recording.rows else 0
                    status = f'REC {duration:.1f}s | {len(recording.rows)} frames'
                pose_status = 'pose detected' if sample['valid_mask'] else 'NO POSE'
                cv2.putText(preview, f'{status} | {pose_status}', (15,30), cv2.FONT_HERSHEY_SIMPLEX, .65, (0,230,255), 2)
                cv2.putText(preview, 'R record | S save | Q exit', (15,60), cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 1)
                cv2.imshow('Mocap capture', preview)
                key = cv2.waitKey(1) & 0xff
                if key in (ord('q'), ord('Q')) or cv2.getWindowProperty('Mocap capture', cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key in (ord('s'), ord('S')):
                    finish()
                if key in (ord('r'), ord('R')) and recording is None:
                    h, w = frame.shape[:2]
                    config = {'capture_source': f'webcam:{args.camera}',
                              'camera': {'index': args.camera, 'width': w, 'height': h,
                                         'requested_width': args.width, 'requested_height': args.height,
                                         'reported_fps': reported_fps, 'backend': cap.getBackendName()},
                              'model': model_info,
                              'video': {'enabled': not args.no_video, 'fps': video_fps,
                                        'codec': 'mp4v', 'timing': 'constant FPS; frame i maps to NPZ row i'},
                              'opencv_version': cv2.__version__, 'mirrored': False,
                              'session_monotonic_origin_ns': start}
                    recording = Recording(args.recordings, args.name, config)
                    if not args.no_video:
                        writer = cv2.VideoWriter(str(recording.directory/'reference.mp4'),
                                                 cv2.VideoWriter_fourcc(*'mp4v'), video_fps, (w,h))
                        if not writer.isOpened():
                            raise RuntimeError('MP4 writer failed to open. Try --no-video.')
                    print(f'Recording: {recording.directory.name}', flush=True)
                frame_index += 1
    finally:
        # Release hardware even if saving fails (for example, disk full).
        try:
            finish()
        finally:
            if cap is not None:
                cap.release()
            cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--model', type=Path, default=MODEL)
    parser.add_argument('--recordings', type=Path, default=RECORDINGS)
    parser.add_argument('--database', type=Path, default=DATABASE)
    parser.add_argument('--no-video', action='store_true')
    parser.add_argument('--video-fps', type=float)
    parser.add_argument('--video', type=Path, help='Local video; automatically process and save all decoded frames')
    parser.add_argument('--headless', action='store_true', help='Video mode: no preview or GUI calls')
    parser.add_argument('--progress', action='store_true', help='Video mode: periodic terminal progress')
    parser.add_argument('--fallback-fps', type=float, help='Video timestamp fallback FPS; defaults to source FPS')
    parser.add_argument('--timestamp-mode', choices=('auto', 'fps'), default='auto',
                        help='Video: prefer source timestamps, or force FPS-derived timing')
    args = parser.parse_args()
    if args.width <= 0 or args.height <= 0 or not args.name.strip():
        parser.error('Width/height must be positive and name must not be empty')
    if args.video_fps is not None and (not math.isfinite(args.video_fps) or args.video_fps <= 0):
        parser.error('--video-fps must be finite and positive')
    if args.fallback_fps is not None and (not math.isfinite(args.fallback_fps) or args.fallback_fps <= 0):
        parser.error('--fallback-fps must be finite and positive')
    if args.video is None and (args.headless or args.progress or args.fallback_fps is not None or args.timestamp_mode != 'auto'):
        parser.error('--headless, --progress, --fallback-fps and --timestamp-mode require --video')
    if args.video is not None and args.video_fps is not None:
        parser.error('--video-fps is webcam-only; use --fallback-fps for video timestamps')
    try:
        run(args)
    except KeyboardInterrupt:
        print('Capture interrupted; cleanup completed.')
    except ModuleNotFoundError as exc:
        parser.exit(1, f'Capture dependency error: {exc}\nInstall dependencies with python -m pip install -r requirements-mocap.txt\n')
    except Exception as exc:
        parser.exit(1, f'Capture error: {exc}\n')


if __name__ == '__main__':
    main()
