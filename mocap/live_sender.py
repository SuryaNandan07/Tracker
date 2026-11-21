"""Stream existing MediaPipe inference to Blender; never creates a recording."""
import argparse
from pathlib import Path
import socket
import time
import uuid
import numpy as np
from .capture import create_detector, infer_frame
from .config import MODEL
from .drawing import draw_skeleton
from .live_protocol import HOST, PORT, VERSION, encode


class CausalFilter:
    def __init__(self, tau=.035, beta=2., confidence=.45):
        if not 0 <= tau <= 1 or not 0 <= beta <= 20 or not 0 <= confidence <= 1:
            raise ValueError('Invalid filter parameters')
        self.tau, self.beta, self.threshold = tau, beta, confidence
        self.points = np.zeros((33, 3))
        self.last = np.full(33, -1., dtype=float)

    def update(self, sample, timestamp):
        raw = np.asarray(sample['world_landmarks'])
        # Tasks image visibility is consistently available; world visibility may be NaN.
        score = np.nan_to_num(sample['visibility'], nan=0., posinf=0., neginf=0.)
        score = np.clip(score, 0, 1)
        valid = np.isfinite(raw).all(axis=1) & (np.abs(raw) <= 10).all(axis=1)
        valid &= (score >= self.threshold) & bool(sample['valid_mask'])
        output = [None] * 33
        for j in np.flatnonzero(valid):
            dt = timestamp - self.last[j]
            if self.last[j] < 0 or dt > .5:
                self.points[j] = raw[j]
            else:
                speed = np.linalg.norm(raw[j] - self.points[j]) / max(dt, .001)
                tau = self.tau / (1 + self.beta * speed)
                alpha = 1 if tau == 0 else -np.expm1(-max(dt, .001) / tau)
                self.points[j] += alpha * (raw[j] - self.points[j])
            self.last[j] = timestamp
            output[j] = self.points[j].tolist()
        return output, score.tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--video', type=Path, help='Optional local file for network/inference testing')
    parser.add_argument('--model', type=Path, default=MODEL)
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=480)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--tau', type=float, default=.035, help='Causal landmark smoothing seconds; 0 disables')
    parser.add_argument('--beta', type=float, default=2., help='Reduce smoothing as joint speed increases')
    parser.add_argument('--confidence', type=float, default=.45)
    parser.add_argument('--max-frames', type=int, default=0)
    parser.add_argument('--max-seconds', type=float, default=0)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.width <= 0 or args.height <= 0:
        parser.error('Use port 1024..65535 and positive dimensions')
    if args.max_frames < 0 or not np.isfinite(args.max_seconds) or args.max_seconds < 0:
        parser.error('Limits must be finite and nonnegative')
    try:
        filt = CausalFilter(args.tau, args.beta, args.confidence)
    except ValueError as exc:
        parser.error(str(exc))
    import cv2
    import mediapipe as mp
    cap = None
    sequence = detected = 0
    session = uuid.uuid4().hex
    started = time.monotonic()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, create_detector(args, mp) as detector:
            if args.video and not args.video.is_file():
                raise FileNotFoundError(args.video)
            cap = cv2.VideoCapture(str(args.video) if args.video else args.camera)
            if not cap.isOpened():
                raise RuntimeError('Cannot open camera/video; check permissions and other camera apps')
            if not args.video:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            previous_ms = -1
            last_status = started
            print(f'Sending to {HOST}:{args.port}. Ctrl+C or preview Q to stop.', flush=True)
            while not args.max_frames or sequence < args.max_frames:
                if args.max_seconds and time.monotonic() - started >= args.max_seconds:
                    break
                ok, frame = cap.read()
                if not ok:
                    if args.video:
                        break
                    raise RuntimeError('Webcam stopped delivering frames')
                stamp = time.monotonic_ns()
                timestamp_ms = max(previous_ms + 1, stamp // 1_000_000)
                previous_ms = timestamp_ms
                sample = infer_frame(detector, frame, timestamp_ms, cv2, mp)
                points, scores = filt.update(sample, stamp / 1e9)
                packet = dict(version=VERSION, session=session, sequence=sequence,
                    timestamp_ns=stamp, detected=bool(sample['valid_mask']), world=points, confidence=scores)
                sock.sendto(encode(packet), (HOST, args.port))
                sequence += 1
                detected += int(sample['valid_mask'])
                if args.preview:
                    draw_skeleton(frame, sample['image_landmarks'], sample['visibility'])
                    cv2.imshow('Live mocap - Q to stop', frame)
                    if cv2.waitKey(1) & 255 in (ord('q'), ord('Q')) or cv2.getWindowProperty('Live mocap - Q to stop', cv2.WND_PROP_VISIBLE) < 1:
                        break
                if time.monotonic() - last_status >= 2:
                    print(f'{sequence} packets, {detected} detections, {sequence/(time.monotonic()-started):.1f} Hz', flush=True)
                    last_status = time.monotonic()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Live sender: {exc}\n')
    finally:
        if cap is not None:
            cap.release()
        if args.preview:
            cv2.destroyAllWindows()
        print(f'Stopped: {sequence} packets, {detected} detected poses. No recording written.', flush=True)


if __name__ == '__main__':
    main()
