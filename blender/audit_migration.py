"""Read-only Blender dependency and animation audit; never saves a project."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def inspect(path):
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False, use_scripts=False)
    dependencies = []
    for collection in ('images', 'libraries', 'movieclips', 'sounds', 'fonts', 'cache_files', 'volumes'):
        for item in getattr(bpy.data, collection, []):
            raw = getattr(item, 'filepath', '')
            packed = bool(getattr(item, 'packed_file', None) or getattr(item, 'packed_files', []))
            if raw and raw != '<builtin>':
                resolved = bpy.path.abspath(raw, library=getattr(item, 'library', None))
                dependencies.append(dict(kind=collection, name=item.name, path=raw,
                    resolved=resolved, packed=packed, exists=Path(resolved).exists()))
    actions = {}
    for action in bpy.data.actions:
        curves = [c for layer in action.layers for strip in layer.strips
                  for bag in getattr(strip, 'channelbags', []) for c in bag.fcurves]
        values = [(c.data_path, c.array_index, [(tuple(k.co), k.interpolation) for k in c.keyframe_points]) for c in curves]
        actions[action.name] = dict(curves=len(curves), keys=sum(len(c.keyframe_points) for c in curves), digest=digest(values))
    objects = {o.name: dict(type=o.type, data=o.data.name if o.data else None,
        parent=o.parent.name if o.parent else None,
        action=o.animation_data.action.name if o.animation_data and o.animation_data.action else None,
        transform=[list(row) for row in o.matrix_world]) for o in bpy.data.objects}
    samples = {}
    for scene in bpy.data.scenes:
        bpy.context.window.scene = scene
        for frame in sorted(set([scene.frame_start, (scene.frame_start+scene.frame_end)//2, scene.frame_end])):
            scene.frame_set(frame)
            graph = bpy.context.evaluated_depsgraph_get()
            state = {}
            for o in scene.objects:
                if o.type == 'ARMATURE':
                    state[o.name] = [[list(row) for row in p.matrix] for p in o.pose.bones]
                elif o.type == 'MESH':
                    evaluated = o.evaluated_get(graph)
                    mesh = evaluated.to_mesh()
                    state[o.name] = [tuple(v.co) for v in mesh.vertices]
                    evaluated.to_mesh_clear()
            samples[f'{scene.name}:{frame}'] = digest(state)
    return dict(version=bpy.app.version_string, dependencies=dependencies, actions=actions,
        objects=objects, samples=samples,
        scenes={s.name: [s.frame_start,s.frame_end,s.render.fps,s.render.fps_base] for s in bpy.data.scenes},
        texts={t.name: t.as_string() for t in bpy.data.texts})

parser = argparse.ArgumentParser()
parser.add_argument('--paths', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
result = {}
for path in json.loads(args.paths.read_text()):
    print('AUDIT', path, flush=True)
    result[path] = inspect(Path(path))
with args.output.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2)
print('PASS audited', len(result), 'projects/backups', flush=True)
