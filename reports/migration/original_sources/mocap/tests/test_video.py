import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from mocap.capture import run
from mocap.database import Database
from mocap.playback import resolve_recording
from mocap.storage import load_arrays
from mocap.video import VideoClock


class ClockTests(unittest.TestCase):
    def test_source_variable_timing_and_integer_monotonicity(self):
        clock = VideoClock(60)
        output = [clock.next(t, i) for i, t in enumerate([7., 7.25, 24., 57.])]
        self.assertEqual([t for t, _ in output], [7., 7.25, 24., 57.])
        self.assertEqual([t for _, t in output], [7,8,24,57])
        self.assertEqual(clock.info['fps_timestamp_frames'], 0)

    def test_unreliable_pts_switch_permanently_to_anchored_fps(self):
        for bad in (float('nan'), float('inf'), -1., 7., 0.):
            clock = VideoClock(25)
            output = [clock.next(t, i)[0] for i, t in enumerate([7., bad, 9000.])]
            self.assertEqual(output, [7.,47.,87.])
            self.assertEqual(clock.info['fallback_start_frame'], 1)

    def test_unknown_fps_allowed_until_fallback_needed(self):
        clock = VideoClock(None)
        self.assertEqual(clock.next(0,0), (0.,0))
        self.assertEqual(clock.next(25,1), (25.,25))
        with self.assertRaisesRegex(ValueError, 'fallback-fps'):
            clock.next(25,2)

    def test_forced_fps(self):
        clock = VideoClock(25, 'fps')
        self.assertEqual([clock.next(t,i)[0] for i,t in enumerate([999.,3.,1000.])], [0.,40.,80.])


class VideoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'source.mp4'
        writer = cv2.VideoWriter(str(self.source), cv2.VideoWriter_fourcc(*'mp4v'), 25., (64,48))
        self.assertTrue(writer.isOpened(), 'MP4 fixture encoder unavailable')
        try:
            for i in range(6):
                writer.write(np.full((48,64,3), i*30, dtype=np.uint8))
        finally:
            writer.release()
        self.args = SimpleNamespace(video=self.source, model=self.root/'pose.task',
            recordings=self.root/'recordings', database=self.root/'mocap.db',
            name='video test', fallback_fps=None, timestamp_mode='auto',
            headless=True, progress=False, no_video=False)
        self.args.model.write_bytes(b'model fixture')
        self.mp = MagicMock()
        self.mp.__version__ = 'test'
        self.detector = MagicMock()
        points = [SimpleNamespace(x=.4,y=.5,z=-.1,visibility=.9,presence=.8)]*33
        present = SimpleNamespace(pose_landmarks=[points], pose_world_landmarks=[points])
        missing = SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[])
        self.detector.detect_for_video.side_effect = [present, missing, present, present, missing, present]
        self.mp.tasks.vision.PoseLandmarker.create_from_options.return_value.__enter__.return_value = self.detector

    def execute(self):
        with patch.dict('sys.modules', {'mediapipe': self.mp}), \
             patch.object(cv2, 'imshow', side_effect=AssertionError('headless GUI call')), \
             patch.object(cv2, 'waitKey', side_effect=AssertionError('headless GUI call')), \
             patch.object(cv2, 'destroyAllWindows', side_effect=AssertionError('headless GUI call')):
            run(self.args)

    def output(self):
        path = resolve_recording('video test', self.args.recordings, self.args.database)
        return path, load_arrays(path), json.loads((path/'metadata.json').read_text())

    def test_sequential_decode_reference_and_playback_compatibility(self):
        original_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.execute()
        path, arrays, metadata = self.output()
        self.assertEqual(arrays['image_landmarks'].shape, (6,33,3))
        np.testing.assert_array_equal(arrays['frame_indices'], np.arange(6))
        np.testing.assert_allclose(arrays['timestamps_ms'], np.arange(6)*40)
        np.testing.assert_array_equal(arrays['valid_mask'], [True,False,True,True,False,True])
        self.assertTrue(np.isnan(arrays['world_landmarks'][1]).all())
        self.assertAlmostEqual(float(arrays['presence'][0,0]), .8)
        self.assertEqual(self.detector.detect_for_video.call_count, 6)
        self.assertEqual([c.args[1] for c in self.detector.detect_for_video.call_args_list], [0,40,80,120,160,200])
        self.assertEqual(original_hash, hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(original_hash, hashlib.sha256((path/'reference.mp4').read_bytes()).hexdigest())
        self.assertEqual(metadata['files']['video'], 'reference.mp4')
        self.assertEqual(metadata['config']['camera']['width'], 64)
        self.assertEqual(metadata['config']['processing']['status'], 'end_of_stream')
        self.assertNotIn('first_frame_monotonic_ms', metadata)
        self.assertEqual(Database(self.args.database).lookup(metadata['id'])[0]['frame_count'], 6)

    def test_no_reference_and_forced_fallback(self):
        self.args.no_video = True
        self.args.timestamp_mode = 'fps'
        self.args.fallback_fps = 50
        self.execute()
        path, arrays, metadata = self.output()
        np.testing.assert_allclose(arrays['timestamps_ms'], np.arange(6)*20)
        self.assertIsNone(metadata['files']['video'])
        self.assertFalse((path/'reference.mp4').exists())
        self.assertEqual(metadata['config']['timing']['fps_timestamp_frames'], 6)

    def test_invalid_and_empty_file(self):
        self.args.video = self.root/'missing.webm'
        with self.assertRaises(FileNotFoundError):
            self.execute()
        self.args.video.touch()
        with self.assertRaisesRegex(ValueError, 'empty'):
            self.execute()

    def test_interrupt_saves_prefix(self):
        missing = SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[])
        self.detector.detect_for_video.side_effect = [missing, KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            self.execute()
        _, arrays, metadata = self.output()
        self.assertEqual(len(arrays['timestamps_ms']), 1)
        self.assertEqual(metadata['config']['processing']['status'], 'interrupted')

    def test_open_file_with_no_readable_frames(self):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.return_value = 25.
        cap.read.return_value = (False, None)
        with patch.object(cv2, 'VideoCapture', return_value=cap):
            with self.assertRaisesRegex(ValueError, 'No readable'):
                self.execute()
        cap.release.assert_called_once()
        self.assertFalse(self.args.recordings.exists())

    def test_unsupported_file(self):
        self.args.video = self.root/'invalid.webm'
        self.args.video.write_bytes(b'not a video')
        with self.assertRaisesRegex(ValueError, 'Cannot open video'):
            self.execute()

    def test_unreadable_middle_saves_prefix_and_releases(self):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.getBackendName.return_value = 'fake'
        def prop(key):
            if key == cv2.CAP_PROP_FPS:
                return 25.
            if key == cv2.CAP_PROP_FRAME_COUNT:
                return 6.
            return 0.
        cap.get.side_effect = prop
        cap.read.side_effect = [(True, np.zeros((48,64,3), np.uint8)), (False, None)]
        with patch.object(cv2, 'VideoCapture', return_value=cap):
            self.execute()
        cap.release.assert_called_once()
        _, arrays, metadata = self.output()
        self.assertEqual(len(arrays['timestamps_ms']), 1)
        self.assertEqual(metadata['config']['processing']['status'], 'end_of_stream_count_mismatch')


if __name__ == '__main__':
    unittest.main()
