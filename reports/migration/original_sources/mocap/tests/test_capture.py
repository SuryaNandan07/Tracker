"""Exercise capture controls and cleanup using a deterministic fake camera/runtime."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

from mocap.capture import run
from mocap.storage import load_arrays


class CaptureTests(unittest.TestCase):
    def exercise(self, keys, fail_read=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root/'pose.task'
            model.write_bytes(b'test fixture')
            camera = MagicMock()
            camera.isOpened.return_value = True
            camera.get.return_value = 30.0
            camera.getBackendName.return_value = 'fake'
            frame = np.zeros((48,64,3), dtype=np.uint8)
            camera.read.side_effect = [(True, frame)] * len(keys) + [(False, None)]
            cv = MagicMock()
            cv.__version__ = 'test'
            cv.VideoCapture.return_value = camera
            cv.cvtColor.return_value = frame
            cv.waitKey.side_effect = keys
            cv.getWindowProperty.return_value = 1
            detector = MagicMock()
            detector.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[], pose_world_landmarks=[])
            mp = MagicMock()
            mp.__version__ = 'test'
            mp.tasks.vision.PoseLandmarker.create_from_options.return_value.__enter__.return_value = detector
            args = SimpleNamespace(model=model, database=root/'mocap.db', camera=0,
                width=64, height=48, video_fps=None, no_video=True,
                recordings=root/'recordings', name='test take')
            with patch.dict('sys.modules', {'cv2': cv, 'mediapipe': mp}):
                if fail_read:
                    with self.assertRaisesRegex(RuntimeError, 'stopped delivering'):
                        run(args)
                else:
                    run(args)
            camera.release.assert_called_once()
            cv.destroyAllWindows.assert_called_once()
            files = list((root/'recordings').glob('*/landmarks.npz'))
            self.assertEqual(len(files), 1)
            arrays = load_arrays(files[0])
            self.assertEqual(len(arrays['timestamps_ms']), 2)
            self.assertFalse(arrays['valid_mask'].any())
            self.assertTrue(np.isnan(arrays['image_landmarks']).all())

    def test_r_s_q_save_and_cleanup(self):
        self.exercise([ord('r'), -1, ord('s'), ord('q')])

    def test_camera_disconnect_saves_and_releases(self):
        self.exercise([ord('r'), -1, -1], fail_read=True)


if __name__ == '__main__':
    unittest.main()
