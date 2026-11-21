"""Small localhost wire protocol. Standard library only, also imported by Blender."""
import json
import math

HOST = '127.0.0.1'
PORT = 50123
MAX_PACKET = 32768
VERSION = 1


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def decode(payload):
    if len(payload) > MAX_PACKET:
        raise ValueError('Packet too large')
    try:
        p = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ValueError('Invalid JSON') from exc
    if not isinstance(p, dict) or p.get('version') != VERSION:
        raise ValueError('Unsupported packet')
    if not isinstance(p.get('session'), str) or not 1 <= len(p['session']) <= 64:
        raise ValueError('Invalid session')
    for key in ('sequence', 'timestamp_ns'):
        if type(p.get(key)) is not int or not 0 <= p[key] < 2**63:
            raise ValueError('Invalid sequence/timestamp')
    if type(p.get('detected')) is not bool:
        raise ValueError('Invalid detection flag')
    points, confidence = p.get('world'), p.get('confidence')
    if not isinstance(points, list) or len(points) != 33:
        raise ValueError('Expected 33 joints')
    if not isinstance(confidence, list) or len(confidence) != 33:
        raise ValueError('Expected 33 confidence values')
    for point, score in zip(points, confidence):
        if not number(score) or not 0 <= score <= 1:
            raise ValueError('Invalid confidence')
        if point is not None and (not isinstance(point, list) or len(point) != 3 or
                not all(number(v) and abs(v) <= 10 for v in point)):
            raise ValueError('Invalid world coordinates')
        if not p['detected'] and point is not None:
            raise ValueError('Missing detection must not contain coordinates')
    return p


def encode(packet):
    payload = json.dumps(packet, allow_nan=False, separators=(',', ':')).encode('utf-8')
    decode(payload)
    return payload


class PacketGate:
    """Reject stale, reordered and retired-session packets before touching a rig."""
    def __init__(self):
        self.session = None
        self.sequence = -1
        self.timestamp_ns = -1
        self.retired = set()

    def accept(self, packet, now_ns):
        age = (now_ns - packet['timestamp_ns']) / 1e9
        if not -.1 <= age <= .5 or packet['session'] in self.retired:
            return False
        if packet['session'] != self.session:
            if self.session is not None:
                self.retired.add(self.session)
            self.session = packet['session']
            self.sequence = self.timestamp_ns = -1
        if packet['sequence'] <= self.sequence or packet['timestamp_ns'] <= self.timestamp_ns:
            return False
        self.sequence, self.timestamp_ns = packet['sequence'], packet['timestamp_ns']
        return True
