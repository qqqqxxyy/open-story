"""Independent migration helper; public creative CLI contracts remain unchanged."""
import argparse
from pathlib import Path
import json
from script.cli.bootstrap import bootstrap
from .convert import plan
from .import_service import install
from .verify import verify
from .policy import apply_policy


def main():
    parser=argparse.ArgumentParser(description='Read-only plan, transactional import and scoped migration checks')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan');p.add_argument('--source',required=True);p.add_argument('--branches',nargs='+',required=True)
    p.add_argument('--default-branch',required=True);p.add_argument('--output',required=True)
    p.add_argument('--policy');p.add_argument('--legacy-source')
    p=sub.add_parser('import');p.add_argument('--plan',required=True);p.add_argument('--target',required=True)
    p=sub.add_parser('verify');p.add_argument('--plan',required=True);p.add_argument('--config',required=True)
    p.add_argument('--output',required=True);p.add_argument('--no-opening',action='store_true')
    args=parser.parse_args();bootstrap(logging_enabled=False)
    if args.command=='plan':
        result=plan(args.source,args.branches,args.default_branch)
        if args.policy:
            result=apply_policy(result,json.loads(Path(args.policy).read_text(encoding='utf-8-sig')),args.legacy_source)
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        summary={'node_count':len(result['node_order']),'event_count':len(result['events']),
                 'deferred':result['deferred'],'excluded_node_ids':result['excluded_node_ids'],'plan_path':args.output}
    else:
        value=json.loads(Path(args.plan).read_text(encoding='utf8'))
        if args.command=='import':summary=install(value,args.target)
        else:
            summary=verify(value,args.config,not args.no_opening)
            Path(args.output).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
