"""Reopen-result verification and temporary preview rendering; never saves the blend."""
import hashlib
import json
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'blender'/'retarget_validation.json').read_text())
assert hashlib.sha256(Path(report['source']).read_bytes()).hexdigest()==report['source_sha256']
scene=bpy.context.scene
ref=bpy.data.objects['Character_REFERENCE']; target=bpy.data.objects['Character_MOCAP_TEST']
assert ref.data!=target.data
assert bpy.data.objects['Ch44'].parent==ref and bpy.data.objects['Ch44.001'].parent==target
assert ref.animation_data.action.name=='mixamo.com'
assert target.animation_data.action.name==report['action']
assert target.animation_data.action.users==1
action=target.animation_data.action
curves=[c for l in action.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
assert len(curves)==48 and all(len(c.keyframe_points)==572 for c in curves)
scene.frame_set(1)
before=[p.matrix.copy() for p in ref.pose.bones]
target_before=[p.matrix.copy() for p in target.pose.bones]
scene.frame_set(300)
assert all(a==p.matrix for a,p in zip(before,ref.pose.bones))
assert any(a!=p.matrix for a,p in zip(target_before,target.pose.bones))
print('REOPEN PASSED: independent rigs/bindings; reference static; target-only action; 48 quaternion curves x 572 keys; source hash unchanged.')
camera_data=bpy.data.cameras.new('ValidationCamera')
camera=bpy.data.objects.new('ValidationCamera',camera_data)
scene.collection.objects.link(camera)
camera.location=(2,-8,2.5)
camera.rotation_euler=(Vector((1.05,0,1))-camera.location).to_track_quat('-Z','Y').to_euler()
camera_data.type='ORTHO'; camera_data.ortho_scale=4.6
scene.camera=camera
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=960; scene.render.resolution_y=640; scene.render.resolution_percentage=100
scene.display.shading.light='STUDIO'; scene.display.shading.color_type='MATERIAL'
scene.display.shading.show_shadows=True
scene.render.image_settings.file_format='PNG'
for frame in (100,400):
    scene.frame_set(frame)
    scene.render.filepath=str(ROOT/'exports'/f'retarget_preview_{frame}.png')
    bpy.ops.render.render(write_still=True)
