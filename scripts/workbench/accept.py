#!/usr/bin/env python3
"""Preview or explicitly accept a completed task without starting HTTP."""
import argparse
import json
from pathlib import Path
from server import App


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True)
    sub=p.add_subparsers(dest='action',required=True)
    preview=sub.add_parser('preview');preview.add_argument('id')
    accept=sub.add_parser('accept');accept.add_argument('id');accept.add_argument('--token',required=True);accept.add_argument('--confirmed',action='store_true')
    args=p.parse_args();app=App(args.project,recover=False)
    if args.action=='preview':return app.acceptance.prepare(args.id)
    if not args.confirmed:raise ValueError('先向用户展示清理范围并取得明确验收，再执行 --confirmed')
    task=app.acceptance.accept(args.id,args.token)
    return {'id':task['id'],'status':app.public_task(task)['status'],'acceptance':task.get('acceptance')}


if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False))
        raise SystemExit(1)
