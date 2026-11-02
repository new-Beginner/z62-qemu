"""QMP transport that preserves partial replies across a read timeout.

Every command is sent once with an ID. A timed-out command is never replayed;
its late reply is skipped when the next command is observed. Guest state and
QEMU lifecycle are untouched by transport recovery.
"""
from collections import deque
import hashlib
import json
from pathlib import Path
import socket
import threading
import time

VERSION = '2026.10.29-qmp-r1'
LIMIT = 8 * 1024 * 1024


class QmpClient:
    def __init__(self, port, timeout=5):
        if timeout <= 0:
            raise ValueError('Positive QMP timeout required')
        self.timeout = timeout
        self.sock = socket.create_connection(('127.0.0.1',port),timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.next_id = 0
        self.closed = False
        self.timed_out_requests = self.late_replies = 0
        self.events = deque(maxlen=32)
        try:
            greeting = self._receive(time.monotonic()+timeout)
            if 'QMP' not in greeting:
                raise ValueError('Missing QMP greeting')
            self.command('qmp_capabilities')
        except BaseException:
            self.close()
            raise

    def _receive(self, deadline):
        while True:
            newline = self.buffer.find(b'\n')
            if newline >= 0:
                line = bytes(self.buffer[:newline])
                del self.buffer[:newline+1]
                if len(line) > LIMIT:
                    raise ValueError('QMP reply exceeds byte limit')
                message = json.loads(line)
                if not isinstance(message,dict):
                    raise ValueError('QMP reply must be an object')
                return message
            if len(self.buffer) > LIMIT:
                raise ValueError('Unterminated QMP reply exceeds byte limit')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('QMP reply deadline exceeded')
            self.sock.settimeout(remaining)
            data = self.sock.recv(65536)
            if not data:
                raise ConnectionError('Machine monitor disconnected')
            self.buffer.extend(data)

    def command(self, name, arguments=None, *, timeout=None):
        budget = self.timeout if timeout is None else timeout
        if budget <= 0:
            raise ValueError('Positive QMP timeout required')
        with self.lock:
            if self.closed:
                raise ConnectionError('QMP transport is closed')
            self.next_id += 1
            identifier = self.next_id
            request = {'execute':name,'id':identifier}
            if arguments is not None:
                request['arguments'] = arguments
            data = json.dumps(request).encode('utf-8')+b'\n'
            if len(data) > LIMIT:
                raise ValueError('QMP request exceeds byte limit')
            # Send timeout is distinct: a partial request cannot be safely
            # continued/replayed. Read timeout leaves framing bytes intact.
            self.sock.settimeout(self.timeout)
            deadline = time.monotonic()+budget
            try:
                self.sock.sendall(data)
            except OSError:
                self.sock.close()
                self.closed = True
                raise
            try:
                while True:
                    reply = self._receive(deadline)
                    if 'event' in reply:
                        self.events.append(reply)
                        continue
                    if 'id' not in reply:
                        raise ValueError('QMP reply has no request ID')
                    if reply['id'] != identifier:
                        self.late_replies += 1
                        continue
                    if 'error' in reply:
                        raise RuntimeError(reply['error'].get('desc','Machine monitor error'))
                    if 'return' not in reply:
                        raise ValueError('QMP reply has no result')
                    return reply['return']
            except TimeoutError as exc:
                self.timed_out_requests += 1
                raise TimeoutError(f'QMP {name} request {identifier} timed out; execution outcome unknown') from exc
            except (ConnectionError,ValueError):
                self.sock.close()
                self.closed = True
                raise

    def diagnostics(self):
        return {'version':VERSION,'timed_out_requests':self.timed_out_requests,
                'late_replies':self.late_replies,'replayed_commands':0,'closed':self.closed}

    def close(self):
        with self.lock:
            if not self.closed:
                self.sock.close()
                self.closed = True


def apply_console(source):
    """Replace only the pinned old QMP class in an isolated host source tree."""
    old = '''class QmpClient:
    def __init__(self, port):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=5)
        self.file = self.sock.makefile('rwb')
        self.read()
        self.command('qmp_capabilities')

    def read(self):
        while True:
            line = self.file.readline()
            if not line:
                raise ConnectionError('Machine monitor disconnected')
            message = json.loads(line)
            if 'event' not in message:
                return message

    def command(self, name, arguments=None):
        request = dict(execute=name)
        if arguments is not None:
            request['arguments'] = arguments
        self.file.write(json.dumps(request).encode() + b'\\n')
        self.file.flush()
        reply = self.read()
        if 'error' in reply:
            raise RuntimeError(reply['error'].get('desc', 'Machine monitor error'))
        return reply['return']

    def close(self):
        self.file.close()
        self.sock.close()
'''
    from reference_updates import replace_once
    path = source/'tools/web_console.py'
    text = replace_once(path.read_text(encoding='utf-8'),old,
                        'from tools.z62_qmp_transport import QmpClient\n')
    path.write_text(text,encoding='utf-8',newline='\n')
    (source/'tools/z62_qmp_transport.py').write_bytes(Path(__file__).read_bytes())


def identity():
    return {'version':VERSION,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
