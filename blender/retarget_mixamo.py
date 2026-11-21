"""Target-only experimental Mixamo retarget. Run in Blender background on the input file."""
import hashlib
import json
import math
from pathlib import Path
import runpy
import uuid

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'Humanoid_Mocap_Result.blend'
REPORT = ROOT/'blender'/'retarget_validation.json'
LIMBS = {'LeftArm': (11,13), 'LeftForeArm': (13,15),
         'RightArm': (12,14), 'RightForeArm': (14,16),
         'LeftUpLeg': (23,25), 'LeftLeg': (25,27),
         'RightUpLeg': (24,26), 'RightLeg': (26,28)}
TORSO = ['Hips','Spine','Spine1','Spine2']
PREFIX = 'mixamorig:'


def digest(value):
    return hashlib.sha256(repr(value).encode()).hexdigest()


def matrix(m):
    return tuple(tuple(row) for row in m)


def action_snapshot(action):
    return [(c.data_path,c.array_index,[(tuple(k.co),k.interpolation,tuple(k.handle_left),tuple(k.handle_right))
              for k in c.keyframe_points]) for layer in action.layers for strip in layer.strips
            for bag in strip.channelbags for c in bag.fcurves]


def rig_snapshot(rig, mesh):
    return digest((matrix(rig.matrix_world), matrix(mesh.matrix_world),
        [(b.name,b.parent.name if b.parent else None,matrix(b.matrix_local),b.length) for b in rig.data.bones],
        [(tuple(v.co),[(g.group,g.weight) for g in v.groups]) for v in mesh.data.vertices],
        [tuple(p.vertices) for p in mesh.data.polygons],
        [(m.name,m.type) for m in mesh.modifiers], [m.name if m else None for m in mesh.data.materials]))


def evaluated_mesh(mesh):
    obj=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return [tuple(obj.matrix_world @ v.co) for v in obj.data.vertices]


def body_basis(left, right, up):
    x=(left-right).normalized()
    y=(up-x*up.dot(x)).normalized()
    if x.length < .5 or y.length < .5:
        raise ValueError('Degenerate torso orientation')
    return Matrix((x,y,x.cross(y).normalized())).transposed()


def main():
    if OUTPUT.exists():
        raise FileExistsError(f'Refusing to overwrite {OUTPUT}')
    source_path=Path(bpy.data.filepath)
    source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
    ref=bpy.data.objects['Armature']; target=bpy.data.objects['Armature.001']
    refmesh=bpy.data.objects['Ch44']; mesh=bpy.data.objects['Ch44.001']
    assert ref.type==target.type=='ARMATURE'
    assert refmesh.parent==ref and mesh.parent==target
    assert any(m.type=='ARMATURE' and m.object==target for m in mesh.modifiers)
    assert not ref.constraints and not target.constraints
    assert not any(p.constraints for p in target.pose.bones)
    scene=bpy.context.scene
    scene.frame_set(1)
    ref_hash=rig_snapshot(ref,refmesh); target_hash=rig_snapshot(target,mesh)
    ref_action=ref.animation_data.action
    ref_action_hash=digest(action_snapshot(ref_action))
    ref_vertices=evaluated_mesh(refmesh)
    ref_poses=[matrix(p.matrix) for p in ref.pose.bones]
    # Only target data is copied if linked; never mutate reference datablocks.
    if target.data==ref.data:
        target.data=target.data.copy()
    if mesh.data==refmesh.data:
        mesh.data=mesh.data.copy()
    assert target.data!=ref.data and mesh.data!=refmesh.data
    ref.name='Character_REFERENCE'; target.name='Character_MOCAP_TEST'
    original_target_action=target.animation_data.action
    original_target_action.use_fake_user=True
    target.animation_data_clear()
    for p in target.pose.bones:
        p.matrix_basis=Matrix.Identity(4)
        p.rotation_mode='QUATERNION'
    helper=runpy.run_path(str(ROOT/'blender'/'import_mocap.py'))
    data=helper['load_motion'](ROOT/'exports'/'sword_combo_001.json')
    frames,tracks=helper['prepare_tracks'](data,60)
    for j in (11,12,13,14,15,16,23,24,25,26,27,28):
        assert tracks[j] is not None
    rest={b.name:b.matrix_local.to_quaternion() for b in target.data.bones}
    rot=target.matrix_world.to_quaternion().to_matrix()
    inv=rot.transposed()
    bones=target.data.bones
    rest_basis=body_basis(bones[PREFIX+'LeftUpLeg'].head_local,
        bones[PREFIX+'RightUpLeg'].head_local,
        bones[PREFIX+'Neck'].head_local-bones[PREFIX+'Hips'].head_local)
    names=TORSO+list(LIMBS)
    samples={PREFIX+n:[] for n in names}
    previous={}; limited=0; degenerate=0; max_input_delta=0
    for i,frame in enumerate(frames):
        points=[inv @ Vector(track[i]) if track is not None else None for track in tracks]
        up=(points[11]+points[12]-points[23]-points[24])*.5
        pelvis=body_basis(points[23],points[24],up)
        chest=body_basis(points[11],points[12],up)
        desired={}
        for k,name in enumerate(TORSO):
            basis=pelvis.to_quaternion().slerp(chest.to_quaternion(),k/3).to_matrix()
            desired[PREFIX+name]=(basis @ rest_basis.transposed() @ rest[PREFIX+name].to_matrix()).to_quaternion()
        current={}
        dt=(data['timestamps_ms'][i]-data['timestamps_ms'][i-1])/1000 if i else 0
        for bone in bones:
            name=bone.name; short=name.removeprefix(PREFIX)
            parent=bone.parent
            base=current[parent.name] @ rest[parent.name].inverted() @ rest[name] if parent else rest[name]
            if short in LIMBS:
                a,b=LIMBS[short]; direction=points[b]-points[a]
                if direction.length < .025:
                    desired[name]=previous.get(name,base); degenerate+=1
                else:
                    desired[name]=(base @ Vector((0,1,0))).rotation_difference(direction.normalized()) @ base
            q=desired.get(name,base)
            if name in samples:
                if name in previous:
                    old=previous[name]
                    if q.dot(old)<0: q.negate()
                    angle=old.rotation_difference(q).angle
                    max_input_delta=max(max_input_delta,math.degrees(angle))
                    fraction=1-math.exp(-dt/.035)
                    limit=math.radians(720)*dt
                    if angle>limit:
                        limited+=1
                        fraction=min(fraction,limit/angle)
                    q=old.slerp(q,fraction)
                previous[name]=q.copy()
                local=base.inverted() @ q
                if samples[name] and local.dot(samples[name][-1])<0: local.negate()
                samples[name].append(local.copy())
            current[name]=q
    action=bpy.data.actions.new('MOCAP_sword_combo_001_'+uuid.uuid4().hex[:8])
    slot=action.slots.new('OBJECT',target.name)
    curves=action.layers.new('Retarget').strips.new(type='KEYFRAME').channelbag(slot,ensure=True).fcurves
    anim=target.animation_data_create(); anim.action=action; anim.action_slot=slot
    for name,values in samples.items():
        for axis in range(4):
            curve=curves.new(data_path=f'pose.bones["{name}"].rotation_quaternion',index=axis)
            curve.keyframe_points.add(len(frames))
            for key,frame,q in zip(curve.keyframe_points,frames,values):
                key.co=(frame,q[axis]); key.interpolation='LINEAR'
            curve.extrapolation='CONSTANT'; curve.update()
    scene.render.fps=60; scene.render.fps_base=1
    scene.frame_start=1; scene.frame_end=math.ceil(frames[-1])
    # Confirm reference poses and geometry remain static and identical at all samples.
    mesh_start=None; movement=0; max_length_error=0
    for i,frame in enumerate(frames):
        scene.frame_set(math.floor(frame),subframe=frame%1)
        assert ref.animation_data.action==ref_action
        assert [matrix(p.matrix) for p in ref.pose.bones]==ref_poses, ('Reference moved',i)
        for p in target.pose.bones:
            max_length_error=max(max_length_error,abs((p.tail-p.head).length-p.bone.length))
            assert all(math.isfinite(v) for row in p.matrix for v in row)
        if i in (0,100,200,300,400,571):
            assert evaluated_mesh(refmesh)==ref_vertices, ('Reference mesh changed',i)
            positions=evaluated_mesh(mesh)
            if mesh_start is None: mesh_start=positions
            else: movement=max(movement,max((Vector(a)-Vector(b)).length for a,b in zip(positions,mesh_start)))
    scene.frame_set(1)
    assert rig_snapshot(ref,refmesh)==ref_hash
    assert rig_snapshot(target,mesh)==target_hash
    assert digest(action_snapshot(ref_action))==ref_action_hash
    assert movement>.05 and max_length_error<.001
    assert action.users==1 and target.animation_data.action!=ref_action
    assert hashlib.sha256(source_path.read_bytes()).hexdigest()==source_hash
    # Select only the target and frame both characters without moving either.
    for obj in bpy.context.selected_objects: obj.select_set(False)
    target.select_set(True); bpy.context.view_layer.objects.active=target
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_location=(1,0,1)
                area.spaces.active.region_3d.view_distance=6
    report={'source':str(source_path),'source_sha256':source_hash,'output':str(OUTPUT),
        'reference':'Character_REFERENCE / Ch44','target':'Character_MOCAP_TEST / Ch44.001',
        'action':action.name,'mapped_bones':list(samples),'sample_count':len(frames),
        'fps':60,'range':[1,scene.frame_end],'last_sample_frame':frames[-1],
        'duration_seconds':data['timestamps_ms'][-1]/1000,'missing_rows':[i for i,v in enumerate(data['valid_mask']) if not v],
        'reference_geometry_rest_transforms_action_unchanged':True,'reference_static_all_samples':True,
        'target_rest_mesh_weights_unchanged':True,'target_mesh_max_displacement_m':movement,
        'maximum_bone_length_error_armature_units':max_length_error,
        'degenerate_segments_held':degenerate,'angular_rate_limit_events':limited,
        'largest_unsmoothed_rotation_step_deg':max_input_delta,
        'root_translation':'Object transform and root location held fixed; rotations only',
        'filter':'Missing-joint time interpolation; quaternion smoothing tau=35ms; 720 deg/s angular limit',
        'limitations':['Estimated monocular depth','Minimal-swing limb twist, no calibrated roll',
                      'No foot contacts/IK: foot sliding possible','Hands/feet/head not independently tracked',
                      'Temporal filtering introduces lag; low-confidence valid estimates retained']}
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
    REPORT.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('RETARGET VALIDATED',json.dumps(report))


if __name__=='__main__':
    main()
