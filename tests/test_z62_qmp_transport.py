"""Real local TCP tests for timeout framing and exactly-once command sends."""
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from z62_qmp_transport import QmpClient, apply_console


class QmpTransportTests(unittest.TestCase):
    def server(self, handler):
        listener=socket.socket()
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        listener.settimeout(3)
        errors=[]
        seen=[]
        def worker():
            try:
                with listener.accept()[0] as conn:
                    conn.settimeout(3)
                    file=conn.makefile('rb')
                    def read():
                        msg=json.loads(file.readline())
                        seen.append(msg)
                        return msg
                    def send(msg): conn.sendall(json.dumps(msg).encode()+b'\n')
                    send({'QMP':{'version':{'qemu':{'major':10}}}})
                    caps=read()
                    send({'return':{},'id':caps['id']})
                    handler(conn,read,send)
                    file.close()
            except BaseException as exc:
                errors.append(exc)
            finally:
                listener.close()
        thread=threading.Thread(target=worker,daemon=True)
        thread.start()
        def finish():
            thread.join(4)
            self.assertFalse(thread.is_alive(),'test server did not exit')
            self.assertEqual(errors,[])
        self.addCleanup(finish)
        return listener.getsockname()[1],seen

    def test_partial_late_reply_survives_timeout_without_replaying_stop(self):
        def handler(conn,read,send):
            first=read()
            reply=json.dumps({'return':{'old':True},'id':first['id']}).encode()+b'\n'
            conn.sendall(reply[:13])
            time.sleep(.15)
            second=read()
            conn.sendall(reply[13:])
            send({'event':'STOP','data':{}})
            send({'return':{'running':False},'id':second['id']})
        port,seen=self.server(handler)
        client=QmpClient(port,timeout=1)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(TimeoutError,'execution outcome unknown'):
            client.command('stop',timeout=.04)
        self.assertTrue(client.buffer)
        self.assertFalse(client.closed)
        self.assertEqual(client.command('query-status'),{'running':False})
        self.assertEqual([r['execute'] for r in seen],['qmp_capabilities','stop','query-status'])
        self.assertEqual(client.timed_out_requests,1)
        self.assertEqual(client.late_replies,1)
        self.assertEqual(len(client.events),1)

    def test_server_error_does_not_poison_next_query(self):
        def handler(conn,read,send):
            req=read();send({'error':{'desc':'controlled failure'},'id':req['id']})
            req=read();send({'return':123,'id':req['id']})
        port,_=self.server(handler)
        client=QmpClient(port)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(RuntimeError,'controlled failure'): client.command('bad')
        self.assertEqual(client.command('query-good'),123)

    def test_request_ids_serialize_concurrent_callers(self):
        def handler(conn,read,send):
            for _ in range(2):
                req=read();send({'return':req['execute'],'id':req['id']})
        port,seen=self.server(handler)
        client=QmpClient(port)
        self.addCleanup(client.close)
        result={}
        def call(name): result[name]=client.command(name)
        threads=[threading.Thread(target=call,args=(name,)) for name in ('query-a','query-b')]
        for t in threads:t.start()
        for t in threads:t.join(2)
        self.assertEqual(result,{'query-a':'query-a','query-b':'query-b'})
        self.assertEqual([r['id'] for r in seen],[1,2,3])

    def test_missing_reply_id_is_rejected_instead_of_misattributed(self):
        def handler(conn,read,send): read();send({'return':{'unidentified':True}})
        port,_=self.server(handler)
        client=QmpClient(port)
        self.addCleanup(client.close)
        with self.assertRaisesRegex(ValueError,'no request ID'): client.command('query-status')
        self.assertTrue(client.closed)

    def test_staging_replaces_only_monitor_class(self):
        with tempfile.TemporaryDirectory() as temp:
            stage=Path(temp)
            (stage/'tools').mkdir()
            source=ROOT/'third_party/z62-qemu/tools/web_console.py'
            shutil.copyfile(source,stage/'tools/web_console.py')
            apply_console(stage)
            text=(stage/'tools/web_console.py').read_text(encoding='utf-8')
            self.assertIn('from tools.z62_qmp_transport import QmpClient',text)
            self.assertNotIn('class QmpClient:',text)
            self.assertEqual(text.split('def free_port():',1)[1],
                             source.read_text(encoding='utf-8').split('def free_port():',1)[1])
            compile(text,'staged-monitor','exec')


if __name__=='__main__': unittest.main()
