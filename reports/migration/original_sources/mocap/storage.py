import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import LANDMARK_NAMES, CONNECTIONS, COORDINATES

SHAPES = {'image_landmarks': (33,3), 'world_landmarks': (33,3),
          'visibility': (33,), 'presence': (33,), 'world_visibility': (33,),
          'world_presence': (33,), 'timestamps_ms': (), 'frame_indices': (), 'valid_mask': ()}
REQUIRED = set(SHAPES) - {'world_visibility', 'world_presence'}


def validate(arrays):
    if not REQUIRED <= arrays.keys():
        raise ValueError(f'Missing arrays: {REQUIRED - arrays.keys()}')
    n = len(arrays['timestamps_ms'])
    if n == 0:
        raise ValueError('Recording contains no frames')
    for key, tail in SHAPES.items():
        if key in arrays and arrays[key].shape != (n,) + tail:
            raise ValueError(f'{key} must have shape {(n,) + tail}')
    t = arrays['timestamps_ms']
    if not np.isfinite(t).all() or t[0] < 0 or np.any(np.diff(t) <= 0):
        raise ValueError('Timestamps must be finite, nonnegative and strictly increasing')
    indices = arrays['frame_indices']
    if indices.dtype.kind not in 'iu' or indices[0] < 0 or np.any(np.diff(indices) <= 0):
        raise ValueError('Frame indices must be nonnegative increasing integers')
    if arrays['valid_mask'].dtype != np.bool_:
        raise ValueError('valid_mask must be boolean')
    missing = ~arrays['valid_mask']
    for key in SHAPES.keys() - {'timestamps_ms', 'frame_indices', 'valid_mask'}:
        if key in arrays:
            if arrays[key].dtype.kind != 'f' or np.isinf(arrays[key]).any():
                raise ValueError(f'{key} must contain floats or NaN, not infinity')
            if not np.isnan(arrays[key][missing]).all():
                raise ValueError(f'{key}: missing frames must contain only NaN')
    return arrays


def load_arrays(path):
    path = Path(path)
    if path.is_dir():
        path = path / 'landmarks.npz'
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    return validate(arrays)


def result_arrays(result):
    data = {key: np.full(shape, np.nan, dtype=np.float32)
            for key, shape in SHAPES.items() if shape}
    valid = (bool(result.pose_landmarks) and bool(result.pose_world_landmarks)
             and len(result.pose_landmarks[0]) == 33 and len(result.pose_world_landmarks[0]) == 33)
    if valid:
        for points, coords, vis, presence in (
            (result.pose_landmarks[0], 'image_landmarks', 'visibility', 'presence'),
            (result.pose_world_landmarks[0], 'world_landmarks', 'world_visibility', 'world_presence')):
            data[coords][:] = [[p.x, p.y, p.z] for p in points]
            for attr, key in [('visibility', vis), ('presence', presence)]:
                data[key][:] = [getattr(p, attr, None) if getattr(p, attr, None) is not None
                               else np.nan for p in points]
    data['valid_mask'] = bool(valid)
    return data


class Recording:
    def __init__(self, root, name, config):
        if not name.strip():
            raise ValueError('Recording name cannot be empty')
        self.id = uuid.uuid4().hex
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:60] or 'recording'
        self.directory = Path(root) / f'{slug}_{self.id}'
        self.directory.mkdir(parents=True, exist_ok=False)
        self.rows = []
        self.metadata = {'schema_version': 1, 'id': self.id, 'name': name,
                         'created_at': datetime.now(timezone.utc).isoformat(),
                         'config': config, 'landmark_names': LANDMARK_NAMES,
                         'connections': CONNECTIONS, 'coordinates': dict(COORDINATES)}

    def append(self, sample, timestamp_ms, frame_index):
        if not self.rows:
            self.origin_ms = timestamp_ms
        self.rows.append({**sample, 'timestamps_ms': timestamp_ms - self.origin_ms,
                          'frame_indices': frame_index})

    def save(self, database):
        arrays = {key: np.asarray([row[key] for row in self.rows], dtype=(
            np.bool_ if key == 'valid_mask' else np.int64 if key == 'frame_indices'
            else np.float64 if key == 'timestamps_ms' else np.float32)) for key in SHAPES}
        validate(arrays)
        duration = float(arrays['timestamps_ms'][-1])
        video_config = self.metadata['config'].get('video', {})
        reference = video_config.get('reference_file', 'reference.mp4')
        self.metadata.update(duration_ms=duration, frame_count=len(self.rows),
                             measured_fps=(len(self.rows)-1)*1000/duration if duration else None,
                             files={'landmarks': 'landmarks.npz', 'metadata': 'metadata.json',
                                    'video': reference if reference and (self.directory/reference).is_file() else None})
        if self.metadata['config'].get('source_type') == 'video_file':
            self.metadata['first_frame_source_ms'] = self.origin_ms
        else:
            self.metadata['first_frame_monotonic_ms'] = self.origin_ms
        # Exclusive creates prevent any accidental replacement, even on a repeated save.
        with (self.directory/'landmarks.npz').open('xb') as f:
            np.savez_compressed(f, **arrays)
        with (self.directory/'metadata.json').open('x', encoding='utf-8') as f:
            json.dump(self.metadata, f, indent=2, allow_nan=False)
        try:
            database.add(self.metadata, self.directory)
        except Exception as exc:
            print(f'WARNING: Files saved to {self.directory}, but SQLite indexing failed: {exc}')
        return self.directory
