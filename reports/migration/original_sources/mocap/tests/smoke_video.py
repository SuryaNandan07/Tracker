"""Optional real-model smoke test on an existing video; outputs live only in temp storage."""
import argparse
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True)
    args = parser.parse_args()
    import cv2
    import mediapipe as mp
    from mocap.config import MODEL
    from mocap.storage import Recording, result_arrays, load_arrays
    from mocap.database import Database
    from mocap.drawing import draw_skeleton

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1)
    with tempfile.TemporaryDirectory() as temp, mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
        root = Path(temp)
        take = Recording(root, 'integration_smoke', {})
        cap = cv2.VideoCapture(str(args.video))
        writer = None
        try:
            assert cap.isOpened(), 'Cannot open input video'
            for i in range(12):
                ok, frame = cap.read()
                assert ok, 'Input needs at least 12 frames'
                if writer is None:
                    h, w = frame.shape[:2]
                    writer = cv2.VideoWriter(str(take.directory/'reference.mp4'),
                                             cv2.VideoWriter_fourcc(*'mp4v'), 30, (w,h))
                    assert writer.isOpened(), 'MP4 encoder unavailable'
                result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)), i*34)
                sample = result_arrays(result)
                take.append(sample, i*34, i)
                writer.write(frame)
                draw_skeleton(frame.copy(), sample['image_landmarks'], sample['visibility'])
        finally:
            cap.release()
            if writer is not None:
                writer.release()
        take.save(Database(root/'smoke.db'))
        arrays = load_arrays(take.directory)
        assert len(arrays['timestamps_ms']) == 12
        video = cv2.VideoCapture(str(take.directory/'reference.mp4'))
        count = 0
        try:
            while video.read()[0]:
                count += 1
        finally:
            video.release()
        assert count == 12, f'Expected 12 reference frames, got {count}'
        assert arrays['valid_mask'].any(), 'No person detected in test video'
        print(f'PASS: 12 frames, {arrays["valid_mask"].sum()} detected poses; '
              'real inference, drawing, MP4 encode/decode, NPZ and SQLite.')


if __name__ == '__main__':
    main()
