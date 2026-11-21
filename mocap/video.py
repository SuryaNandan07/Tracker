"""Sequential video input adapter for the existing capture/storage pipeline."""
import math
import shutil
import time
from pathlib import Path

from .capture import create_detector, infer_frame, model_metadata
from .database import Database
from .drawing import draw_skeleton
from .storage import Recording


def positive(value):
    return value if math.isfinite(value) and value > 0 else None


class VideoClock:
    """Use increasing source PTS, permanently switching to anchored FPS on failure."""
    def __init__(self, fps, mode='auto'):
        self.fps = positive(fps) if fps is not None else None
        self.previous = None
        self.previous_inference = -1
        self.fallback = mode == 'fps'
        self.info = {'requested_mode': mode, 'fallback_fps': self.fps,
                     'source_timestamp_frames': 0, 'fps_timestamp_frames': 0,
                     'fallback_start_frame': 0 if self.fallback else None,
                     'fallback_reason': 'forced FPS mode' if self.fallback else None,
                     'inference_timestamp_adjustments': 0}

    def next(self, raw_ms, index):
        if not self.fallback and (not math.isfinite(raw_ms) or raw_ms < 0 or
                                 (self.previous is not None and raw_ms <= self.previous)):
            self.fallback = True
            self.info.update(fallback_start_frame=index,
                             fallback_reason='nonfinite, negative, repeated or decreasing source timestamp')
        if self.fallback:
            if self.fps is None:
                raise ValueError('Video timestamps are unavailable/unreliable and source FPS is unknown. '
                                 'Supply --fallback-fps with the correct source rate.')
            timestamp = 0.0 if self.previous is None else self.previous + 1000.0/self.fps
            self.info['fps_timestamp_frames'] += 1
        else:
            timestamp = float(raw_ms)
            self.info['source_timestamp_frames'] += 1
        self.previous = timestamp
        inference = max(self.previous_inference+1, int(timestamp))
        self.info['inference_timestamp_adjustments'] += int(inference != int(timestamp))
        self.previous_inference = inference
        return timestamp, inference


def run_video(args):
    source = Path(args.video).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Video file not found: {source}')
    if source.stat().st_size == 0:
        raise ValueError(f'Video file is empty: {source}')
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(str(source))
    recording = None
    status = 'error'
    error = None
    count = 0
    try:
        if not cap.isOpened():
            raise ValueError(f'Cannot open video: {source}. The container or codec may be unsupported or damaged.')
        fps = positive(float(cap.get(cv2.CAP_PROP_FPS)))
        frame_count = positive(float(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        expected = int(frame_count) if frame_count is not None else None
        clock = VideoClock(args.fallback_fps or fps, args.timestamp_mode)
        db = Database(args.database)
        with create_detector(args, mp) as detector:
            print(f'Processing {source} ({expected or "unknown"} reported frames). '
                  'Sequential processing; no frame skipping.', flush=True)
            last_progress = time.monotonic()
            while True:
                ok, frame = cap.read()
                if not ok or frame is None or frame.size == 0:
                    if count == 0:
                        raise ValueError('No readable video frames. Check for an empty/damaged file or unsupported codec.')
                    if expected is not None and count != expected:
                        status = 'end_of_stream_count_mismatch'
                        print(f'WARNING: Decoder returned {count} frames; container reported {expected}. '
                              'This may be an approximate frame count or an early decode failure. '
                              'All readable frames are saved; completeness is unverified.', flush=True)
                    else:
                        status = 'end_of_stream'
                    break
                timestamp, inference_ms = clock.next(float(cap.get(cv2.CAP_PROP_POS_MSEC)), count)
                if recording is None:
                    h, w = frame.shape[:2]
                    config = {'source_type': 'video_file', 'capture_source': str(source),
                              'camera': {'width': w, 'height': h, 'reported_fps': fps,
                                         'backend': cap.getBackendName()},
                              'source_video': {'path': str(source), 'size_bytes': source.stat().st_size,
                                               'reported_frame_count': expected},
                              'model': model_metadata(args, mp), 'timing': clock.info,
                              'video': {'enabled': not args.no_video, 'reference_file': None,
                                        'timing': 'byte-for-byte full source copy, including original timestamps/audio'},
                              'opencv_version': cv2.__version__, 'mirrored': False}
                    recording = Recording(args.recordings, args.name, config)
                    recording.metadata['coordinates']['time'] = (
                        'timestamps_ms: source CAP_PROP_POS_MSEC minus the first saved timestamp. '
                        'On invalid/non-increasing source time, remaining frames advance by 1000/fallback_fps '
                        'from the last good timestamp. Forced FPS starts at zero. See config.timing. '
                        'Not inference wall time or camera acquisition time.')
                    if not args.no_video:
                        reference = 'reference' + source.suffix.lower()
                        # New UUID directory and exclusive creation: source/previous takes never overwritten.
                        with source.open('rb') as src, (recording.directory/reference).open('xb') as dst:
                            shutil.copyfileobj(src, dst)
                        config['video']['reference_file'] = reference
                sample = infer_frame(detector, frame, inference_ms, cv2, mp)
                recording.append(sample, timestamp, count)
                count += 1
                if args.progress and (count == 1 or time.monotonic()-last_progress >= 2):
                    print(f'Processed {count}/{expected or "?"} frames | source {timestamp/1000:.2f}s', flush=True)
                    last_progress = time.monotonic()
                if not args.headless:
                    # Resize only the preview; inference and reference keep source resolution.
                    h, w = frame.shape[:2]
                    scale = min(1.0, 960/w, 720/h)
                    preview = cv2.resize(frame, (max(1, round(w*scale)), max(1, round(h*scale))))
                    draw_skeleton(preview, sample['image_landmarks'], sample['visibility'])
                    label = 'pose' if sample['valid_mask'] else 'NO POSE'
                    cv2.putText(preview, f'{count}/{expected or "?"} | {timestamp/1000:.2f}s | {label}',
                                (10,25), cv2.FONT_HERSHEY_SIMPLEX, .5, (0,230,255), 1)
                    cv2.putText(preview, 'Q: save prefix and exit', (10,48), cv2.FONT_HERSHEY_SIMPLEX,
                                .5, (255,255,255), 1)
                    cv2.imshow('Mocap video', preview)
                    key = cv2.waitKey(1) & 0xff
                    if key in (ord('q'), ord('Q')) or cv2.getWindowProperty('Mocap video', cv2.WND_PROP_VISIBLE) < 1:
                        status = 'cancelled'
                        break
    except KeyboardInterrupt:
        status = 'interrupted'
        raise
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        cap.release()
        try:
            if not args.headless:
                cv2.destroyAllWindows()
        finally:
            if recording is not None and recording.rows:
                recording.metadata['config']['processing'] = {
                    'status': status, 'decoded_frames_saved': count, 'error': error,
                    'end_detection': 'OpenCV read failure; EOF and decode errors cannot always be distinguished'}
                print(f'Saved {count} frames ({status}): {recording.save(db)}', flush=True)
                if clock.info['fps_timestamp_frames']:
                    print(f'Timing fallback: {clock.info}', flush=True)
            elif recording is not None:
                print(f'No landmarks saved. Partial reference files may remain at {recording.directory}', flush=True)
