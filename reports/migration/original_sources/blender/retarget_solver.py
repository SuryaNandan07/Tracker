"""Shared rotation solver extracted unchanged from the original experimental retarget."""
import math
from mathutils import Vector
from retarget_mixamo import body_basis, TORSO, LIMBS, PREFIX

def solve(target, data, frames, tracks):
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
    return samples
