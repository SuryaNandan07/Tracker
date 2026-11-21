"""Render two poses per saved preset, without resaving any Blender file."""
from pathlib import Path
import bpy
from mathutils import Vector

root=Path(__file__).resolve().parents[1]
for name in ('Natural','Balanced','Cinematic'):
    bpy.ops.wm.open_mainfile(filepath=str(root/f'Humanoid_Mocap_{name}.blend'))
    scene=bpy.context.scene
    camera=bpy.data.objects.new('ValidationCamera',bpy.data.cameras.new('ValidationCamera'))
    scene.collection.objects.link(camera)
    camera.location=(2,-8,2.5)
    camera.rotation_euler=(Vector((1.05,0,1))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.type='ORTHO'; camera.data.ortho_scale=4.6
    scene.camera=camera; scene.render.engine='BLENDER_WORKBENCH'
    scene.render.resolution_x=960; scene.render.resolution_y=640; scene.render.resolution_percentage=100
    scene.display.shading.light='STUDIO'; scene.display.shading.color_type='MATERIAL'
    scene.render.image_settings.file_format='PNG'
    for frame in (100,400):
        scene.frame_set(frame)
        scene.render.filepath=str(root/'exports'/'phase2'/f'{name}_{frame}.png')
        bpy.ops.render.render(write_still=True)
