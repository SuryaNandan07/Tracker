"""Replay saved landmarks only. This module never imports MediaPipe."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .config import RECORDINGS, DATABASE
from .database import Database
from .storage import load_arrays
from .drawing import draw_skeleton


def resolve_recording(value, root=RECORDINGS, database=DATABASE):
    direct = Path(value)
    if direct.exists():
        return direct
    child = Path(root) / value
    if child.exists():
        return child
    # Files are the source of truth: support moved projects and missing SQLite indexes.
    matches = []
    for metadata_path in Path(root).glob('*/metadata.json'):
        try:
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if value in (metadata.get('name'), metadata.get('id')):
                matches.append((metadata['created_at'], metadata_path.parent))
        except (OSError, ValueError, KeyError):
            continue
    if matches:
        matches.sort(key=lambda item: item[0], reverse=True)
        if len(matches) > 1:
            print(f'{len(matches)} takes share this name; using newest. Use a directory or ID for another take.')
        return matches[0][1]
    if Path(database).is_file():
        rows = Database(database).lookup(value)
        if rows and Path(rows[0]['directory']).is_dir():
            return Path(rows[0]['directory'])
    raise FileNotFoundError(f'Recording not found: {value}. Supply a name, ID, directory or .npz path.')


def play(arrays, width=960, height=540):
    import cv2
    timestamps = arrays['timestamps_ms']
    n = len(timestamps)
    i = 0
    paused = False
    origin = time.perf_counter()
    try:
        while True:
            canvas = np.zeros((height,width,3), dtype=np.uint8)
            if arrays['valid_mask'][i]:
                draw_skeleton(canvas, arrays['image_landmarks'][i], arrays['visibility'][i])
            label = 'PAUSED' if paused else 'PLAYING'
            missing = '' if arrays['valid_mask'][i] else ' | NO POSE'
            if i == n-1:
                label = 'END - R to replay'
            cv2.putText(canvas, f'{label}{missing} | frame {i+1}/{n} | {timestamps[i]:.1f} ms',
                        (15,30), cv2.FONT_HERSHEY_SIMPLEX, .6, (255,255,255), 1)
            cv2.putText(canvas, 'Space: pause/resume | R: replay | Q: exit', (15,55),
                        cv2.FONT_HERSHEY_SIMPLEX, .55, (255,255,255), 1)
            cv2.imshow('Mocap playback', canvas)
            key = cv2.waitKey(1) & 0xff
            now = time.perf_counter()
            if key in (ord('q'), ord('Q')) or cv2.getWindowProperty('Mocap playback', cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord(' '):
                if paused:
                    origin += now - paused_at
                else:
                    paused_at = now
                paused = not paused
            elif key in (ord('r'), ord('R')):
                i, paused, origin = 0, False, now
            elif not paused and i < n-1:
                due = (timestamps[i+1] - timestamps[0])/1000
                if now - origin >= due:
                    i += 1  # Display every saved frame; never silently skip missing frames.
            time.sleep(.003)
    finally:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', required=True)
    parser.add_argument('--recordings', type=Path, default=RECORDINGS)
    parser.add_argument('--database', type=Path, default=DATABASE)
    parser.add_argument('--inspect', action='store_true', help='Validate and summarize without opening a window')
    args = parser.parse_args()
    try:
        path = resolve_recording(args.recording, args.recordings, args.database)
        arrays = load_arrays(path)
        print(f'Loaded {path}\n{len(arrays["timestamps_ms"])} frames; '
              f'{arrays["timestamps_ms"][-1]:.1f} ms; {arrays["valid_mask"].sum()} valid poses')
        if not args.inspect:
            width, height = 960, 540
            metadata_path = (path if path.is_dir() else path.parent)/'metadata.json'
            if metadata_path.exists():
                camera = json.loads(metadata_path.read_text(encoding='utf-8')).get('config', {}).get('camera', {})
                w, h = camera.get('width', width), camera.get('height', height)
                if w > 0 and h > 0:
                    scale = min(960/w, 720/h)
                    width, height = max(1, round(w*scale)), max(1, round(h*scale))
            play(arrays, width, height)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        parser.exit(1, f'Playback error: {exc}\n')


if __name__ == '__main__':
    main()
