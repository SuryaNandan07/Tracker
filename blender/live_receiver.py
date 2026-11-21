"""Main-thread, target-only live Mixamo control. No keyframes or Action edits."""
import atexit
from collections import deque
import math
from pathlib import Path
import socket
import sys
import time
import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT/'blender'):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
from mocap.live_protocol import HOST, PORT, MAX_PACKET, decode, PacketGate
from retarget_mixamo import body_basis, TORSO, LIMBS, PREFIX

KEY = '_tracker_live_mocap'
ARMS = {n: pair for n, pair in LIMBS.items() if n in ('LeftArm','LeftForeArm','RightArm','RightForeArm')}
MAPPED = [PREFIX+n for n in [*TORSO, *ARMS]]


def validate_scene():
    ref = bpy.data.objects.get('Character_REFERENCE')
    target = bpy.data.objects.get('Character_MOCAP_TEST')
    if not ref or not target or ref.type != 'ARMATURE' or target.type != 'ARMATURE':
        raise ValueError('Expected verified Character_REFERENCE and Character_MOCAP_TEST armatures')
    if ref.data == target.data or target.data.users != 1:
        raise ValueError('Target armature data must be independent')
    meshes = [o for o in bpy.data.objects if o.type == 'MESH' and
              any(m.type == 'ARMATURE' and m.object == target for m in o.modifiers)]
    reference_meshes = [o for o in bpy.data.objects if o.type == 'MESH' and
              any(m.type == 'ARMATURE' and m.object == ref for m in o.modifiers)]
    if not meshes or not reference_meshes or any(a.data == b.data for a in meshes for b in reference_meshes):
        raise ValueError('Expected independent target/reference meshes with armature bindings')
    if target.constraints or any(p.constraints for p in target.pose.bones):
        raise ValueError('Constrained target rig is not supported by the live prototype')
    if target.animation_data and target.animation_data.drivers:
        raise ValueError('Target animation drivers require separate review')
    needed = MAPPED + [PREFIX+'LeftUpLeg', PREFIX+'RightUpLeg', PREFIX+'Neck']
    if any(n not in target.data.bones for n in needed):
        raise ValueError('Expected existing mixamorig bone mapping')
    if target.parent or any(abs(s-1) > 1e-4 for s in target.matrix_world.to_scale().normalized() * math.sqrt(3)):
        raise ValueError('Parented or nonuniformly scaled armatures need a separate calibration')
    return ref, target


class Receiver:
    def __init__(self, port, smoothing, confidence):
        self.ref, self.target = validate_scene()
        self.port = port
        self.set_smoothing(smoothing)
        if not 0 <= confidence <= 1:
            raise ValueError('Confidence must be between 0 and 1')
        self.confidence = confidence
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No SO_REUSEADDR: a second receiver must fail rather than share packets.
            self.socket.bind((HOST, port))
            self.socket.setblocking(False)
        except Exception:
            self.socket.close()
            raise
        self.gate = PacketGate()
        self.bad = self.accepted = self.updated = 0
        self.last_packet = self.last_pose = None
        self.update_times = deque()
        self.state = 'waiting'
        self.error = None
        self.previous = {}
        self.previous_time = None
        self.saved = {p.name: (p.rotation_mode, p.location.copy(), p.rotation_quaternion.copy(),
            p.rotation_euler.copy(), tuple(p.rotation_axis_angle), p.scale.copy()) for p in self.target.pose.bones}
        anim = self.target.animation_data
        self.action = anim.action if anim else None
        self.slot = anim.action_slot if anim else None
        self.nla = [(track, track.mute) for track in anim.nla_tracks] if anim else []
        self.rest = {b.name: b.matrix_local.to_quaternion() for b in self.target.data.bones}
        bones = self.target.data.bones
        self.rest_basis = body_basis(bones[PREFIX+'LeftUpLeg'].head_local,
            bones[PREFIX+'RightUpLeg'].head_local,
            bones[PREFIX+'Neck'].head_local-bones[PREFIX+'Hips'].head_local)
        self.inverse_rotation = self.target.matrix_world.to_quaternion().inverted()
        # Detach only the target's reference to its Action. Do not edit Action data/fake-user flags.
        if anim:
            anim.action = None
            for track, _ in self.nla:
                track.mute = True
        self.active = True

    def set_smoothing(self, seconds):
        if not math.isfinite(seconds) or not 0 <= seconds <= .5:
            raise ValueError('Rotation smoothing seconds must be in [0, .5]')
        self.smoothing = seconds

    def apply(self, packet):
        points = [self.inverse_rotation @ Vector((p[0],p[2],-p[1]))
                  if p is not None and score >= self.confidence else None
                  for p, score in zip(packet['world'], packet['confidence'])]
        if not packet['detected'] or any(points[j] is None for j in (11,12,23,24)):
            self.state = 'holding: missing torso'
            return False
        up = (points[11]+points[12]-points[23]-points[24])*.5
        if up.length < .08 or (points[11]-points[12]).length < .05 or (points[23]-points[24]).length < .05:
            self.state = 'holding: degenerate torso'
            return False
        try:
            pelvis = body_basis(points[23], points[24], up).to_quaternion()
            chest = body_basis(points[11], points[12], up).to_quaternion()
        except ValueError:
            self.state = 'holding: degenerate torso'
            return False
        stamp = packet['timestamp_ns']/1e9
        dt = min(.1, max(.001, stamp-self.previous_time)) if self.previous_time is not None else 1/30
        desired = {PREFIX+n: (pelvis.slerp(chest,k/3).to_matrix() @
            self.rest_basis.transposed() @ self.rest[PREFIX+n].to_matrix()).to_quaternion()
            for k,n in enumerate(TORSO)}
        current = {}
        assignments = {}
        for bone in self.target.data.bones:
            name = bone.name
            parent = bone.parent
            base = current[parent.name] @ self.rest[parent.name].inverted() @ self.rest[name] if parent else self.rest[name]
            pose = self.target.pose.bones[name]
            q = desired.get(name, base @ pose.matrix_basis.to_quaternion())
            short = name.removeprefix(PREFIX)
            if short in ARMS:
                a,b = ARMS[short]
                if points[a] is not None and points[b] is not None and (points[b]-points[a]).length >= .025:
                    direction = (points[b]-points[a]).normalized()
                    q = (base @ Vector((0,1,0))).rotation_difference(direction) @ base
                else:
                    q = base @ pose.matrix_basis.to_quaternion()
            if name in MAPPED:
                old = self.previous.get(name, base @ pose.matrix_basis.to_quaternion())
                if old.dot(q) < 0:
                    q.negate()
                angle = 2*math.acos(min(1., max(0., old.dot(q))))
                # Causal smoothing, lighter during fast motion; bounded reacquisition.
                tau = self.smoothing / (1 + angle/max(dt,.001))
                alpha = 1 if tau == 0 else -math.expm1(-dt/tau)
                if angle > 1e-6:
                    alpha = min(alpha, math.radians(720)*dt/angle)
                q = old.slerp(q, alpha).normalized()
                local = (base.inverted() @ q).normalized()
                if local.dot(pose.rotation_quaternion) < 0:
                    local.negate()
                assignments[name] = local
                self.previous[name] = q.copy()
            current[name] = q
        for name, q in assignments.items():
            pose = self.target.pose.bones[name]
            pose.rotation_mode = 'QUATERNION'
            pose.rotation_quaternion = q
        self.previous_time = stamp
        self.target.update_tag()
        self.state = 'live'
        return True

    def tick(self):
        if not self.active:
            return None
        try:
            if bpy.context.screen and bpy.context.screen.is_animation_playing:
                self.error = 'Timeline playback started: live receiver stopped to avoid animation conflicts'
                stop()
                return None
            latest = None
            deadline = time.monotonic() + .003
            for _ in range(128):
                if time.monotonic() >= deadline:
                    break
                try:
                    payload, address = self.socket.recvfrom(MAX_PACKET+1)
                except BlockingIOError:
                    break
                try:
                    packet = decode(payload)
                    if address[0] != HOST or not self.gate.accept(packet, time.monotonic_ns()):
                        self.bad += 1
                        continue
                    latest = packet
                    self.accepted += 1
                    self.last_packet = time.monotonic()
                except ValueError:
                    self.bad += 1
            if latest and self.apply(latest):
                self.updated += 1
                self.last_pose = time.monotonic()
                self.update_times.append(self.last_pose)
            if self.last_packet is not None and time.monotonic()-self.last_packet > .5:
                self.state = 'holding: disconnected'
            while self.update_times and time.monotonic()-self.update_times[0] > 2:
                self.update_times.popleft()
            return 1/60
        except Exception as exc:
            self.error = repr(exc)
            print('Live mocap stopped:', self.error)
            stop()
            return None

    def close(self):
        if not self.active:
            return
        self.active = False
        self.socket.close()
        anim = self.target.animation_data
        if anim:
            anim.action = self.action
            if self.action and self.slot:
                anim.action_slot = self.slot
            for track, mute in self.nla:
                track.mute = mute
        for name, saved in self.saved.items():
            p = self.target.pose.bones[name]
            mode, loc, quat, euler, axis, scale = saved
            p.rotation_mode = mode
            p.location, p.rotation_quaternion, p.rotation_euler = loc, quat, euler
            p.rotation_axis_angle, p.scale = axis, scale
        self.target.update_tag()
        self.state = 'stopped; original pose and Action restored'


@persistent
def cleanup_before_file_change(*_):
    stop()


def start(port=PORT, smoothing=.035, confidence=.45):
    if bpy.context.screen and bpy.context.screen.is_animation_playing:
        raise RuntimeError('Pause the Timeline before starting live control')
    stop()
    receiver = Receiver(port, smoothing, confidence)
    bpy.app.driver_namespace[KEY] = receiver
    receiver.callback = receiver.tick
    bpy.app.timers.register(receiver.callback, first_interval=0., persistent=False)
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.save_pre):
        if cleanup_before_file_change not in handlers:
            handlers.append(cleanup_before_file_change)
    print(f'Live receiver ready on {HOST}:{port}; Timeline should remain paused')
    return receiver


def stop():
    receiver = bpy.app.driver_namespace.get(KEY)
    if receiver:
        if hasattr(receiver, 'callback') and bpy.app.timers.is_registered(receiver.callback):
            bpy.app.timers.unregister(receiver.callback)
        receiver.close()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.save_pre):
        if cleanup_before_file_change in handlers:
            handlers.remove(cleanup_before_file_change)


def restore():
    stop()


def set_smoothing(seconds=.035):
    receiver = bpy.app.driver_namespace.get(KEY)
    if receiver is None:
        raise RuntimeError('Start receiver first')
    receiver.set_smoothing(seconds)


def status():
    r = bpy.app.driver_namespace.get(KEY)
    if r is None:
        return {'state': 'not started'}
    return dict(state=r.state, active=r.active, packets=r.accepted, updates=r.updated,
        rejected=r.bad, update_hz=sum(time.monotonic()-t <= 2 for t in r.update_times)/2,
        pose_age_s=None if r.last_pose is None else round(time.monotonic()-r.last_pose,3),
        smoothing_seconds=r.smoothing, error=r.error)


atexit.register(stop)

if __name__ == '__main__':
    start()
