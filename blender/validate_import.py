"""Run with Blender --background --factory-startup --python-exit-code 1 --python this_file."""
import argparse
import math
from pathlib import Path
import runpy
import sys

import bpy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default=str(Path(__file__).resolve().parents[1]/'exports'/'sword_combo_001.json'))
    parser.add_argument('--blend-output', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.blend_output and args.blend_output.exists():
        raise FileExistsError(f'Refusing to overwrite {args.blend_output}')
    module = runpy.run_path(str(Path(__file__).with_name('import_mocap.py')))
    original_scene = bpy.context.scene
    original_objects = set(original_scene.objects)
    data = module['load_motion'](args.json)
    frames, tracks = module['prepare_tracks'](data, 60)
    scene = module['import_motion'](args.json, 60)
    assert original_scene != scene and set(original_scene.objects) == original_objects
    joints = sorted((o for o in scene.objects if 'joint_index' in o), key=lambda o:o['joint_index'])
    links = [o for o in scene.objects if o.type == 'CURVE']
    assert len(joints) == 33 and len(links) == len(data['connections'])
    assert scene.frame_end == math.ceil(frames[-1])
    bpy.context.window.scene = scene
    for index, frame in enumerate(frames):
        scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        graph = bpy.context.evaluated_depsgraph_get()
        for j, obj in enumerate(joints):
            if tracks[j] is not None:
                actual = obj.evaluated_get(graph).matrix_world.translation
                assert max(abs(a-b) for a,b in zip(actual, tracks[j][index])) < 1e-4, (index,j,actual)
        for link in links:
            evaluated = link.evaluated_get(graph)
            for endpoint in (0,1):
                # Three world-location driver variables per curve endpoint.
                driver = next(c.driver for c in link.data.animation_data.drivers
                              if c.data_path == f'splines[0].points[{endpoint}].co' and c.array_index == 0)
                target = driver.variables[0].targets[0].id
                expected = target.evaluated_get(graph).matrix_world.translation
                actual = evaluated.data.splines[0].points[endpoint].co
                assert max(abs(actual[k]-expected[k]) for k in range(3)) < 1e-4, (index,link.name,endpoint,tuple(actual),tuple(expected))
            assert all(curve.driver.is_valid for curve in link.data.animation_data.drivers)
    scene.frame_set(1)
    print(f'PASS Blender {bpy.app.version_string}: {len(frames)} evaluated sample times, '
          '33 markers, all connection endpoints, valid drivers, original scene preserved.')
    if args.blend_output:
        args.blend_output.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(args.blend_output.resolve()))


if __name__ == '__main__':
    main()
