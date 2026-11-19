#!/usr/bin/env python3
"""Collect the same public delivery files in no-page mode, without starting HTTP."""
import argparse
import json
from pathlib import Path
from server import App


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,required=True);p.add_argument('task')
    args=p.parse_args();app=App(args.project,recover=False);task=app.task(args.task)
    public=app.public_task(task)
    if public['status'] not in ('awaiting_acceptance','accepted'):
        raise ValueError('请等待制作及执行者回收完成后交付')
    products=[]
    for result in public['results']:
        if not result.get('video'):continue
        index=result['index']
        products.append({'index':index,'title':result['title'],**{kind:str(app.edits.media(task['id'],index,kind)) for kind in ('video','cover','package')}})
    return {'taskId':task['id'],'status':public['status'],'httpStarted':False,'products':products,'instruction':'交付这里的发布包；引擎内部编辑 HTML 不额外交付。用户验收前不清理中间资产。'}


if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False));raise SystemExit(1)
