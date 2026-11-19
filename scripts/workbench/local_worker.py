"""Detached, single-item local cover renderer; survives HTTP service restarts."""
import argparse
import os
from pathlib import Path
from server import App,read,write

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,required=True);parser.add_argument('--item',required=True);parser.add_argument('--lease',required=True);args=parser.parse_args()
    app=App(args.project,recover=False)
    row=app.queue.accept(args.item,args.lease,'local-'+str(os.getpid()))
    folder=app.edits.root/row['taskId']/str(row['index']);operation=read(folder/'operation.json')
    if not operation or operation.get('id')!=row['id']:
        operation={**row['operation'],'sequence':row['sequence']}
        write(folder/'operation.json',operation)
    original=app.edits.checked
    def checked(*a,**kw):
        if app.queue.item(args.item)['status']=='stopping':raise ValueError('已取消首帧更新，原版本保留')
        result=original(*a,**kw)
        if app.queue.item(args.item)['status']=='stopping':raise ValueError('已取消首帧更新，原版本保留')
        return result
    app.edits.checked=checked
    app.queue.cover_state(row,'running','正在更新视频首帧…')
    app.edits._render(row['taskId'],row['index'],Path(row['sourceVideo']),Path(row['output']),folder,operation)
    operation=read(folder/'operation.json',{})
    state='completed' if operation.get('status')=='completed' else 'failed'
    app.queue.local_finish(args.item,args.lease,state,operation.get('message','首帧更新中断'))

if __name__=='__main__':main()
