import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mocap.database import Database
from mocap.export_blender import export_recording
from mocap.storage import Recording, result_arrays

SCRIPT = Path(__file__).resolve().parents[2]/'blender'/'import_mocap.py'
spec = importlib.util.spec_from_file_location('blender_import_test', SCRIPT)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)  # Must work without Blender, NumPy in Blender, or inference.


class BlenderExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        take = Recording(self.root/'recordings', 'test', {})
        for i, timestamp in enumerate((100., 125., 200.)):
            points = [SimpleNamespace(x=float(i),y=2.,z=3.,visibility=.8,presence=.9)]*33
            result = SimpleNamespace(pose_landmarks=[points], pose_world_landmarks=[points])
            if i == 1:
                result = SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[])
            take.append(result_arrays(result), timestamp, i+10)
        take.save(Database(self.root/'db.sqlite'))
        self.source = take.directory
        self.output = self.root/'export.json'

    def export(self):
        return export_recording(self.source, self.output, self.root/'recordings', self.root/'db.sqlite')

    def test_export_preserves_frames_identity_time_missing_and_source(self):
        before = {p.name:hashlib.sha256(p.read_bytes()).digest() for p in self.source.iterdir()}
        self.export()
        data = importer.load_motion(self.output)
        self.assertEqual(data['timestamps_ms'], [0.,25.,100.])
        self.assertEqual(data['frame_indices'], [10,11,12])
        self.assertEqual(len(data['landmark_names']), 33)
        self.assertEqual(data['valid_mask'], [True,False,True])
        self.assertEqual(data['world_landmarks'][0][0], [0.,2.,3.])
        self.assertEqual(data['blender_landmarks'][0][0], [0.,3.,-2.])
        self.assertEqual(data['blender_landmarks'][1][0], [None,None,None])
        self.assertFalse(data['joint_valid_mask'][1][0])
        self.assertAlmostEqual(data['world_presence'][0][0], .9)
        # Metadata prose may contain the word NaN; the strict loader above rejects numeric NaN tokens.
        self.assertIsNone(data['world_presence'][1][0])
        self.assertEqual(before, {p.name:hashlib.sha256(p.read_bytes()).digest() for p in self.source.iterdir()})

    def test_no_overwrites_or_exports_into_recordings(self):
        self.export()
        with self.assertRaises(FileExistsError):
            self.export()
        with self.assertRaises(ValueError):
            export_recording(self.source, self.source/'new.json')

    def test_interpolation_uses_time_not_row_number(self):
        self.export()
        data = importer.load_motion(self.output)
        frames, tracks = importer.prepare_tracks(data, 60)
        self.assertEqual(frames, [1.,2.5,7.])
        self.assertEqual(tracks[0][1], (.5,3.,-2.))
        self.assertEqual(tracks[0][2], (2.,3.,-2.))
        self.assertIsNone(data['blender_landmarks'][1][0][0])

    def test_leading_trailing_holds_and_never_observed_joint(self):
        self.export()
        data = importer.load_motion(self.output)
        data['joint_valid_mask'][0][0] = False
        data['joint_valid_mask'][2][1] = False
        for row in data['joint_valid_mask']:
            row[2] = False
        _, tracks = importer.prepare_tracks(data)
        self.assertEqual(tracks[0][0], tracks[0][2])
        self.assertEqual(tracks[1][2], tracks[1][0])
        self.assertIsNone(tracks[2])
        data['valid_mask'] = [False]*3
        with self.assertRaisesRegex(ValueError, 'No usable'):
            importer.prepare_tracks(data)

    def test_invalid_timestamps_rejected_before_scene_creation(self):
        data = self.export()
        data['timestamps_ms'] = [0,0,100]
        self.output.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'strictly'):
            importer.load_motion(self.output)


if __name__ == '__main__':
    unittest.main()
