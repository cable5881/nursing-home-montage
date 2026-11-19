"""Temporary authenticated companion for adding management without restarting a busy HTTP service.

New launches serve these endpoints directly. This companion exits when its parent launch changes.
"""
import argparse
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from server import App, read, write
from management import Management


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);args=parser.parse_args()
    app=App(args.project,recover=False)
    record=read(app.data/'server.json');port=record['port'];origin=f'http://127.0.0.1:{port}'
    token=parse_qs(urlsplit(record['url']).query)['access'][0]
    manager=Management(app,read,write)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def valid(self):
            return self.headers.get('Host')==f'127.0.0.1:{port+1}' and self.headers.get('Origin')==origin
        def reply(self,status,value):
            data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
            if self.headers.get('Origin')==origin:
                self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Access-Control-Allow-Credentials','true')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/json; charset=utf-8');self.end_headers();self.wfile.write(data)
        def do_OPTIONS(self):
            if not self.valid(): return self.reply(403,{'error':'本地来源无效'})
            self.send_response(204);self.send_header('Access-Control-Allow-Origin',origin);self.send_header('Access-Control-Allow-Credentials','true');self.send_header('Access-Control-Allow-Headers','Content-Type');self.send_header('Access-Control-Allow-Methods','GET,POST');self.end_headers()
        def auth(self):
            expected=f'montage_session_{port}={token}'
            return self.valid() and any(secrets.compare_digest(p.strip(),expected) for p in self.headers.get('Cookie','').split(';'))
        def do_GET(self):
            if not self.auth(): return self.reply(403,{'error':'请从工作台操作'})
            if self.path!='/api/manage/state': return self.reply(404,{'error':'页面不存在'})
            self.reply(200,manager.state())
        def do_POST(self):
            if not self.auth(): return self.reply(403,{'error':'请从工作台操作'})
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('请求格式错误')
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=100000: raise ValueError('输入过长')
                action=self.path.removeprefix('/api/manage/')
                if self.path!='/api/manage/'+action: raise ValueError('操作不存在')
                self.reply(200,manager.dispatch(action,json.loads(self.rfile.read(length))))
            except (ValueError,KeyError,TypeError) as e: self.reply(400,{'error':str(e)})

    server=ThreadingHTTPServer(('127.0.0.1',port+1),Handler);server.daemon_threads=True
    def monitor():
        while read(app.data/'server.json',{}).get('launchId')==record.get('launchId'):
            time.sleep(5)
        server.shutdown()
    threading.Thread(target=monitor,daemon=True).start()
    print(json.dumps({'port':port+1,'managementOnly':True}),flush=True)
    server.serve_forever()


if __name__=='__main__': main()
