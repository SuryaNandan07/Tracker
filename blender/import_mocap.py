"""Open in Blender's Text Editor and Run Script. No NumPy/MediaPipe required."""
import bisect
import json
import math
from pathlib import Path

# Edit these three values, then press Run Script in Blender's Scripting workspace.
JSON_PATH = r'C:\Epic Gamez\tracker\exports\sword_combo_001.json'
FPS = 60
SHOW_JOINT_NAMES = False


def load_motion(path):
    def reject_constant(value):
        raise ValueError(f'Nonstandard JSON number: {value}')
    data = json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject_constant)
    if data.get('format') != 'mediapipe_blender_skeleton' or data.get('version') != 1:
        raise ValueError('Expected mocap.export_blender JSON version 1')
    names, times = data['landmark_names'], data['timestamps_ms']
    if len(names) != 33 or len(set(names)) != 33 or not times:
        raise ValueError('Expected 33 unique joints and at least one frame')
    if any(not isinstance(t, (int,float)) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError('Invalid timestamps')
    if any(b <= a for a,b in zip(times, times[1:])):
        raise ValueError('Timestamps must increase strictly')
    n = len(times)
    for key in ('blender_landmarks', 'joint_valid_mask', 'valid_mask', 'frame_indices'):
        if len(data[key]) != n:
            raise ValueError(f'{key}: frame count mismatch')
    for i, row in enumerate(data['blender_landmarks']):
        if len(row) != 33 or len(data['joint_valid_mask'][i]) != 33:
            raise ValueError('Expected 33 joints per frame')
        for joint, point in enumerate(row):
            if len(point) != 3 or any(v is not None and
                    (not isinstance(v, (int,float)) or not math.isfinite(v)) for v in point):
                raise ValueError('Coordinates must be finite triples or null')
            if data['joint_valid_mask'][i][joint] and (not data['valid_mask'][i] or None in point):
                raise ValueError('Validity flags disagree with coordinates')
    for edge in data['connections']:
        if len(edge) != 2 or any(not isinstance(i,int) or not 0 <= i < 33 for i in edge):
            raise ValueError('Invalid skeleton connection')
    return data


def prepare_tracks(data, fps=60):
    """Pure Python preview interpolation. Exported raw samples remain unchanged."""
    if not isinstance(fps, int) or isinstance(fps, bool) or not 1 <= fps <= 240:
        raise ValueError('FPS must be an integer from 1 to 240')
    times = data['timestamps_ms']
    frames = [1+(t-times[0])*fps/1000 for t in times]
    tracks = []
    for joint in range(33):
        known = [i for i in range(len(times)) if data['valid_mask'][i] and data['joint_valid_mask'][i][joint]]
        if not known:
            tracks.append(None)  # Still create its marker, but hide it and incident edges.
            continue
        values = []
        for i, t in enumerate(times):
            insertion = bisect.bisect_left(known, i)
            if insertion < len(known) and known[insertion] == i:
                values.append(tuple(data['blender_landmarks'][i][joint]))
                continue
            left = known[max(0, insertion-1)]
            right = known[min(insertion, len(known)-1)]
            a, b = data['blender_landmarks'][left][joint], data['blender_landmarks'][right][joint]
            weight = (t-times[left])/(times[right]-times[left]) if left != right else 0
            values.append(tuple(x+(y-x)*weight for x,y in zip(a,b)))
        tracks.append(values)
    if all(track is None for track in tracks):
        raise ValueError('No usable world landmarks; there is no skeleton to animate')
    return frames, tracks


def add_location_animation(bpy, obj, frames, values):
    """Direct linear curves support legacy actions and Blender 4.4+/5.x slots."""
    action = bpy.data.actions.new(obj.name + '_motion')
    animation = obj.animation_data_create()
    if bpy.app.version >= (4,4,0):
        slot = action.slots.new('OBJECT', obj.name)
        strip = action.layers.new('Motion').strips.new(type='KEYFRAME')
        curves = strip.channelbag(slot, ensure=True).fcurves
        animation.action = action
        animation.action_slot = slot
    else:
        curves = action.fcurves
        animation.action = action
    for axis in range(3):
        curve = curves.new(data_path='location', index=axis)
        curve.keyframe_points.add(len(frames))
        for key, frame, point in zip(curve.keyframe_points, frames, values):
            key.co = (frame, point[axis])
            key.interpolation = 'LINEAR'
        curve.extrapolation = 'CONSTANT'
        curve.update()


def import_motion(path=JSON_PATH, fps=FPS):
    data = load_motion(path)
    frames, tracks = prepare_tracks(data, fps)
    import bpy
    import bmesh
    from mathutils import Quaternion

    # A dedicated new scene keeps existing objects, timeline and render settings intact.
    scene = bpy.data.scenes.new('Mocap_' + Path(path).stem)
    collection = bpy.data.collections.new('MediaPipe Skeleton')
    scene.collection.children.link(collection)
    scene.render.fps = fps
    scene.render.fps_base = 1.0
    scene.frame_start, scene.frame_end = 1, max(1, math.ceil(frames[-1]))
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene['source_json'] = str(Path(path).resolve())
    scene['missing_policy'] = 'Time-linear per-joint gap fill; leading/trailing hold; never-observed joints hidden'
    scene['warning'] = 'Estimated hip-centered monocular motion, no calibrated depth/global root motion'

    colors = {'left': (.15,.65,1.,1.), 'right': (1.,.3,.1,1.), 'center': (.95,.8,.15,1.)}
    materials = {}
    for side, color in colors.items():
        mat = bpy.data.materials.new('Mocap_' + side)
        mat.diffuse_color = color
        materials[side] = mat
    mesh = bpy.data.meshes.new('JointMarker')
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=.018)
    bm.to_mesh(mesh)
    bm.free()
    joints = []
    for j, name in enumerate(data['landmark_names']):
        marker = bpy.data.objects.new(f'{j:02d}_{name}', mesh.copy())
        collection.objects.link(marker)
        side = 'left' if name.startswith('left_') else 'right' if name.startswith('right_') else 'center'
        marker.data.materials.append(materials[side])
        marker.color = colors[side]
        marker.show_name = SHOW_JOINT_NAMES
        marker['joint_index'] = j
        marker['landmark_name'] = name
        marker['missing_samples'] = sum(not (v and row[j]) for v,row in zip(data['valid_mask'], data['joint_valid_mask']))
        if tracks[j] is None:
            marker.hide_viewport = marker.hide_render = True
        else:
            add_location_animation(bpy, marker, frames, tracks[j])
        joints.append(marker)

    for a,b in data['connections']:
        curve = bpy.data.curves.new(f'Link_{a:02d}_{b:02d}', type='CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth, curve.bevel_resolution = .006, 1
        spline = curve.splines.new('POLY')
        spline.points.add(1)
        for endpoint, joint in enumerate((a,b)):
            spline.points[endpoint].co = (0,0,0,1)
            for axis, component in enumerate(('X','Y','Z')):
                driver = curve.driver_add(f'splines[0].points[{endpoint}].co', axis).driver
                driver.type = 'AVERAGE'
                var = driver.variables.new()
                var.name, var.type = 'joint', 'TRANSFORMS'
                var.targets[0].id = joints[joint]
                var.targets[0].transform_type = 'LOC_' + component
                var.targets[0].transform_space = 'WORLD_SPACE'
        edge = bpy.data.objects.new(curve.name, curve)
        collection.objects.link(edge)
        curve.materials.append(materials['center'])
        if tracks[a] is None or tracks[b] is None:
            edge.hide_viewport = edge.hide_render = True

    for i, valid in enumerate(data['valid_mask']):
        if not valid:
            scene.timeline_markers.new(f'Missing pose: source {data["frame_indices"][i]} (preview interpolated)',
                                       frame=round(frames[i]))
    scene.frame_set(1)
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
        # Front orthographic view: Blender +X right, +Z up, depth along +Y.
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    space.shading.type = 'SOLID'
                    space.shading.color_type = 'MATERIAL'
                    space.region_3d.view_rotation = Quaternion((1,0,0), math.pi/2)
                    space.region_3d.view_perspective = 'ORTHO'
                    space.region_3d.view_location = (0,0,0)
                    space.region_3d.view_distance = 3.5
        bpy.context.view_layer.objects.active = joints[0]
        for joint in joints:
            joint.select_set(True)
    print(f'Mocap imported: {len(frames)} samples, 33 markers, {len(data["connections"])} links. '
          f'Scene {scene.name}; press Play in the Timeline. Duration {(frames[-1]-1)/fps:.3f}s.')
    return scene


if __name__ == '__main__':
    import_motion()
