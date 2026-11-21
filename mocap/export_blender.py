"""Export raw estimated world motion and an explicit Z-up conversion to strict JSON."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from .config import ROOT, RECORDINGS, DATABASE, LANDMARK_NAMES, CONNECTIONS
from .playback import resolve_recording
from .storage import load_arrays


def json_floats(array):
    """JSON has no NaN: preserve missing scalar values as null."""
    array = np.asarray(array)
    return np.where(np.isfinite(array), array.astype(object), None).tolist()


def export_recording(recording, output, recordings=RECORDINGS, database=DATABASE):
    source = resolve_recording(str(recording), recordings, database).resolve()
    npz = source/'landmarks.npz' if source.is_dir() else source
    output = Path(output).resolve()
    if output.is_relative_to(npz.parent) or output.is_relative_to(Path(recordings).resolve()):
        raise ValueError('Export outside the recordings directory; recordings are read-only inputs.')
    arrays = load_arrays(npz)
    metadata_path = npz.parent/'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    names = metadata.get('landmark_names', LANDMARK_NAMES)
    edges = metadata.get('connections', CONNECTIONS)
    if len(names) != 33 or len(set(names)) != 33:
        raise ValueError('Expected 33 unique landmark identities')
    if any(len(edge) != 2 or any(not isinstance(i, int) or not 0 <= i < 33 for i in edge) for edge in edges):
        raise ValueError('Invalid skeleton connection indices')
    raw = arrays['world_landmarks'].astype(np.float64)
    converted = raw[..., [0, 2, 1]].copy()
    converted[..., 2] *= -1
    data = {
        'format': 'mediapipe_blender_skeleton', 'version': 1,
        'source': {'npz': str(npz), 'sha256': hashlib.sha256(npz.read_bytes()).hexdigest(),
                   'metadata': metadata},
        'coordinates': {'units': 'estimated_meters', 'origin': 'MediaPipe hip midpoint',
                        'mapping': 'Blender (X,Y,Z) = MediaPipe (x,z,-y)',
                        'matrix': [[1,0,0],[0,0,1],[0,-1,0]],
                        'note': 'Visualization basis, not camera calibration. Monocular depth and body '
                                'position are estimates; no global root translation is recovered.'},
        'landmark_names': names, 'connections': edges,
        'timestamps_ms': arrays['timestamps_ms'].tolist(),
        'frame_indices': arrays['frame_indices'].tolist(),
        'valid_mask': arrays['valid_mask'].tolist(),
        'joint_valid_mask': (np.isfinite(raw).all(axis=2) & arrays['valid_mask'][:,None]).tolist(),
        'world_landmarks': json_floats(raw),
        'blender_landmarks': json_floats(converted),
        'missing_policy': 'null represents a missing scalar. Export does not fill gaps, smooth, '
                          'resample, filter confidence, or remove frames.',
    }
    for key in ('visibility', 'presence', 'world_visibility', 'world_presence'):
        if key in arrays:
            data[key] = json_floats(arrays[key])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, allow_nan=False, separators=(',', ':'))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', required=True, help='Name, ID, recording directory or NPZ path')
    parser.add_argument('--output', type=Path, default=ROOT/'exports'/'sword_combo_001.json')
    parser.add_argument('--recordings', type=Path, default=RECORDINGS)
    parser.add_argument('--database', type=Path, default=DATABASE)
    args = parser.parse_args()
    try:
        data = export_recording(args.recording, args.output, args.recordings, args.database)
        print(f'Exported {len(data["timestamps_ms"])} frames, {sum(data["valid_mask"])} valid poses: '
              f'{args.output.resolve()}')
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Export error: {exc}\nChoose a new --output filename if the export already exists.\n')


if __name__ == '__main__':
    main()
