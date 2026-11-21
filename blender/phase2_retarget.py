"""Re-solve the existing retarget with filtered landmarks; preserve original Action."""
import hashlib
import argparse
import json
import math
from pathlib import Path
import sys
import uuid
import bpy
from mathutils import Quaternion

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'blender'))
from retarget_solver import solve
from retarget_mixamo import rig_snapshot, action_snapshot, digest, evaluated_mesh, matrix


def angle(a,b):
    return 2*math.acos(min(1,abs(a.dot(b))))


def rms(values):
    return math.sqrt(sum(v*v for v in values)/len(values))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--preset',required=True,choices=['Natural','Balanced','Cinematic'])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--motion-dir',type=Path,default=ROOT/'exports'/'phase2')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    output=args.output or ROOT/f'Humanoid_Mocap_{args.preset}.blend'
    if output.exists(): raise FileExistsError(output)
    report_path=(output.with_suffix('.validation.json') if args.output else
                 ROOT/'blender'/f'phase2_{args.preset}_validation.json')
    if report_path.exists(): raise FileExistsError(report_path)
    source=Path(bpy.data.filepath); source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    data=json.loads((args.motion_dir/f'{args.preset}.json').read_text())
    cfg=data['config']
    args.rotation_quiet=cfg['rotation_quiet']; args.rotation_fast=cfg['rotation_fast']
    target=bpy.data.objects['Character_MOCAP_TEST']; ref=bpy.data.objects['Character_REFERENCE']
    mesh=bpy.data.objects['Ch44.001']; refmesh=bpy.data.objects['Ch44']
    scene=bpy.context.scene; scene.frame_set(1)
    rig_before=rig_snapshot(target,mesh); ref_before=rig_snapshot(ref,refmesh)
    ref_pose=[matrix(p.matrix) for p in ref.pose.bones]; ref_vertices=evaluated_mesh(refmesh)
    old=target.animation_data.action; old_hash=digest(action_snapshot(old))
    ref_action=ref.animation_data.action; ref_action_hash=digest(action_snapshot(ref_action))
    frames=data['frames']; tracks=list(map(list,zip(*data['points'])))
    original_curves={ (c.data_path,c.array_index):c for l in old.layers for s in l.strips for b in s.channelbags for c in b.fcurves}
    samples=solve(target,data,frames,tracks)
    stats={}; filtered={}
    for name,values in samples.items():
        path=f'pose.bones["{name}"].rotation_quaternion'
        original=[Quaternion([original_curves[path,a].evaluate(f) for a in range(4)]).normalized() for f in frames]
        # Offline symmetric spherical averaging: no causal delay; retain most fast rotation.
        speeds=[angle(original[max(0,i-1)],original[min(len(frames)-1,i+1)]) for i in range(len(frames))]
        ordered=sorted(speeds); quiet=ordered[int(len(speeds)*.35)]; fast=max(ordered[int(len(speeds)*.85)],quiet+1e-6)
        result=[]
        for i,q in enumerate(values):
            activity=max(speeds[max(0,i-2):i+3]); weight=max(0,min(1,(activity-quiet)/(fast-quiet)))
            radius=cfg['rotation_radius']
            total=[0.,0.,0.,0.]
            sigma=radius/2
            for j in range(max(0,i-radius),min(len(values),i+radius+1)):
                other=values[j].copy()
                if q.dot(other)<0: other.negate()
                delta=(data['timestamps_ms'][j]-data['timestamps_ms'][i])/1000*60
                w=math.exp(-.5*(delta/sigma)**2)
                for axis in range(4): total[axis]+=other[axis]*w
            average=Quaternion(total).normalized()
            new=q.slerp(average,args.rotation_quiet*(1-weight)+args.rotation_fast*weight).normalized()
            if result and new.dot(result[-1])<0: new.negate()
            result.append(new)
        indices=[i for i in range(2,len(frames)-2) if max(speeds[i-2:i+3])<=quiet]
        if not indices: indices=[min(range(1,len(frames)-1),key=lambda i:speeds[i])]
        # Geodesic deviation from neighbors' midpoint: high-frequency rotation residual.
        residual=lambda qs:[math.degrees(angle(qs[i],qs[i-1].slerp(qs[i+1],.5))) for i in indices]
        before,after=rms(residual(original)),rms(residual(result))
        stats[name]={'quiet_samples':len(indices),'residual_rms_deg_before':before,'residual_rms_deg_after':after,
            'max_step_deg_before':max(math.degrees(angle(a,b)) for a,b in zip(original,original[1:])),
            'max_step_deg_after':max(math.degrees(angle(a,b)) for a,b in zip(result,result[1:])),
            'minimum_adjacent_dot':min(a.dot(b) for a,b in zip(result,result[1:]))}
        assert stats[name]['minimum_adjacent_dot']>0
        assert stats[name]['max_step_deg_after']<90
        filtered[name]=result
    old.use_fake_user=True
    action=bpy.data.actions.new('MOCAP_PHASE2_'+args.preset+'_' +uuid.uuid4().hex[:8])
    slot=action.slots.new('OBJECT',target.name)
    curves=action.layers.new('Smoothed').strips.new(type='KEYFRAME').channelbag(slot,ensure=True).fcurves
    target.animation_data.action=action; target.animation_data.action_slot=slot
    for name,values in filtered.items():
        for axis in range(4):
            c=curves.new(data_path=f'pose.bones["{name}"].rotation_quaternion',index=axis)
            c.keyframe_points.add(len(frames))
            for k,f,q in zip(c.keyframe_points,frames,values): k.co=(f,q[axis]); k.interpolation='LINEAR'
            c.extrapolation='CONSTANT'; c.update()
    for frame in frames:
        scene.frame_set(math.floor(frame),subframe=frame%1)
        assert [matrix(p.matrix) for p in ref.pose.bones]==ref_pose
        assert all(math.isfinite(v) for p in target.pose.bones for row in p.matrix for v in row)
    scene.frame_set(1)
    assert evaluated_mesh(refmesh)==ref_vertices
    assert rig_snapshot(ref,refmesh)==ref_before and rig_snapshot(target,mesh)==rig_before
    assert digest(action_snapshot(old))==old_hash
    assert digest(action_snapshot(ref_action))==ref_action_hash
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
    report={'preset':args.preset,'landmarks':data['metrics'],'rotation_bones':stats,'source_hash':source_hash,
        'original_action':old.name,'new_action':action.name,'reference_unchanged':True,
        'rigs_meshes_weights_unchanged':True,'original_action_keyframes_unchanged':True,
        'samples':len(frames),'range':[scene.frame_start,scene.frame_end],
        'parameters':cfg,'quaternion_filter':f'Centered hemisphere-aligned Gaussian quaternion mean radius {cfg["rotation_radius"]}; quiet/fast blend {args.rotation_quiet}/{args.rotation_fast}',
        'limitations':'Motion-derived quiet masks and speed peaks are proxies, not ground-truth labels for stationary poses/punches.'}
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    with report_path.open('x') as stream: json.dump(report,stream,indent=2)
    print('PRESET SAVED',args.preset,json.dumps(stats))


if __name__=='__main__': main()
