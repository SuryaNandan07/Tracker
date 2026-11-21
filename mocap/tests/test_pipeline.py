import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mocap.database import Database
from mocap.storage import Recording, load_arrays, result_arrays, validate
from mocap.playback import resolve_recording


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root/'mocap.db')

    def make_take(self):
        points = [SimpleNamespace(x=.4, y=.5, z=-.1, visibility=.9, presence=None) for _ in range(33)]
        detected = result_arrays(SimpleNamespace(pose_landmarks=[points], pose_world_landmarks=[points]))
        detected['image_landmarks'][5] = np.nan
        missing = result_arrays(SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[]))
        take = Recording(self.root/'recordings', 'sword_attack_001', {'camera': {'width':1280, 'height':720}})
        for i, (timestamp, sample) in enumerate([(1000., detected), (1033.25, missing), (1110.75, detected)]):
            take.append(sample, timestamp, i+8)
        take.save(self.db)
        return take

    def test_roundtrip_shapes_timing_and_missing_values(self):
        take = self.make_take()
        arrays = load_arrays(take.directory)
        self.assertEqual(arrays['image_landmarks'].shape, (3,33,3))
        self.assertEqual(arrays['world_landmarks'].shape, (3,33,3))
        self.assertEqual(arrays['presence'].shape, (3,33))
        np.testing.assert_array_equal(arrays['timestamps_ms'], [0,33.25,110.75])
        np.testing.assert_array_equal(arrays['frame_indices'], [8,9,10])
        np.testing.assert_array_equal(arrays['valid_mask'], [True,False,True])
        self.assertTrue(np.isnan(arrays['image_landmarks'][1]).all())
        self.assertTrue(np.isnan(arrays['image_landmarks'][0,5]).all())
        self.assertTrue(np.isnan(arrays['presence']).all())
        self.assertAlmostEqual(float(arrays['world_landmarks'][0,0,2]), -.1)

    def test_sqlite_lookup_and_json(self):
        take = self.make_take()
        row = self.db.lookup(take.id)[0]
        self.assertEqual(row['frame_count'], 3)
        self.assertEqual(row['duration_ms'], 110.75)
        self.assertEqual(self.db.lookup('sword_attack_001')[0]['id'], take.id)
        metadata = json.loads((take.directory/'metadata.json').read_text())
        self.assertEqual(len(metadata['landmark_names']), 33)
        self.assertIn('world', metadata['coordinates'])

    def test_unique_directories_and_no_overwrite(self):
        first, second = self.make_take(), self.make_take()
        self.assertNotEqual(first.directory, second.directory)
        with self.assertRaises(FileExistsError):
            first.save(self.db)
        self.assertEqual(len(self.db.lookup(first.metadata['name'])), 2)

    def test_resolve_without_database(self):
        take = self.make_take()
        self.assertEqual(resolve_recording(take.id, self.root/'recordings', self.root/'absent.db'), take.directory)
        self.assertEqual(resolve_recording('sword_attack_001', self.root/'recordings', self.root/'absent.db'), take.directory)

    def test_playback_loading_with_mediapipe_import_blocked(self):
        take = self.make_take()
        code = '''import sys, importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('mediapipe'):
            raise AssertionError('Playback attempted MediaPipe import')
sys.meta_path.insert(0, Block())
from mocap.playback import load_arrays
assert len(load_arrays(sys.argv[1])['timestamps_ms']) == 3
assert 'mediapipe' not in sys.modules
'''
        subprocess.run([sys.executable, '-c', code, str(take.directory)], check=True,
                       cwd=Path(__file__).resolve().parents[2])

    def test_reject_wrong_shapes_and_bad_timestamps(self):
        arrays = load_arrays(self.make_take().directory)
        broken = dict(arrays, image_landmarks=np.zeros((3,32,3)))
        with self.assertRaises(ValueError):
            validate(broken)
        for timestamps in ([0,0,1], [0,np.nan,3], [0,2,1]):
            with self.assertRaises(ValueError):
                validate(dict(arrays, timestamps_ms=np.array(timestamps)))

    def test_reject_zero_filled_missing_frame(self):
        arrays = load_arrays(self.make_take().directory)
        arrays['image_landmarks'][1] = 0
        with self.assertRaises(ValueError):
            validate(arrays)

    def test_empty_take_and_incomplete_result(self):
        take = Recording(self.root, 'empty', {})
        with self.assertRaises(ValueError):
            take.save(self.db)
        sample = result_arrays(SimpleNamespace(pose_landmarks=[[object()]], pose_world_landmarks=[]))
        self.assertFalse(sample['valid_mask'])
        self.assertTrue(np.isnan(sample['world_landmarks']).all())


if __name__ == '__main__':
    unittest.main()
