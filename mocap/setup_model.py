"""Download the official versioned MediaPipe full pose model, without overwrites."""
import argparse
import hashlib
import urllib.request
import zipfile
from pathlib import Path
from .config import MODEL, MODEL_URL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=MODEL)
    args = parser.parse_args()
    target = args.output
    if target.exists():
        print(f'Model already exists: {target} (unchanged)')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.part')
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open('xb') as f:
            while chunk := response.read(1024*1024):
                f.write(chunk)
        with zipfile.ZipFile(temporary) as bundle:
            if not {'pose_detector.tflite', 'pose_landmarks_detector.tflite'} <= set(bundle.namelist()):
                raise ValueError('Downloaded file is not a pose landmarker bundle')
        # Windows rename refuses to overwrite an existing destination.
        temporary.rename(target)
        print(f'Saved {target}\nSHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}')
    except Exception as exc:
        parser.exit(1, f'Model download failed: {exc}\nOfficial URL: {MODEL_URL}\n'
                    f'If a partial file exists, remove only {temporary} before retrying.\n')


if __name__ == '__main__':
    main()
