"""Single external CLI: bootstrap -> bind -> workflow -> uniform JSON response."""
from pathlib import Path
from uuid import uuid4
from time import perf_counter
import json
import os
import tempfile
from hashlib import sha256
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from script.cli.bootstrap import bootstrap, PROJECT_ROOT
from script.cli.arguments import parse_request
from script.util.errors import ContractError
from script.util.runtime import AGENT, using
from script.util.contracts import validate
from script.util.logging import StoryLogger
from script.workflow.cli.api import Application

def failure(operation, exc, fallback):
    error={'code':getattr(exc,'code',fallback),'message':str(exc)}
    if getattr(exc,'details',None) is not None:error['details']=exc.details
    return {'ok':False,'operation':operation,'data':None,'error':error}

def execute(app, request):
    name = request.get('operation','unknown') if isinstance(request,dict) else 'unknown'
    with using(app.resources):
        try:
            # Application validates envelope and dispatcher validates operation params.
            response={'ok':True,'operation':name,'data':app.execute(request),'error':None}
        except Exception as exc:
            response=failure(name,exc,'OPERATION_FAILED')
        validate(response,'response',AGENT)
        return response

def save_response_file(filename, serialized):
    """Publish the complete serialized envelope before reporting a file receipt."""
    target=Path(filename).resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    raw=serialized.encode('utf-8')
    descriptor,temporary=tempfile.mkstemp(prefix='.'+target.name+'.',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'output_file':str(target),'response_characters':len(serialized),
            'response_utf8_bytes':len(raw),'sha256':sha256(raw).hexdigest()}


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    help_requested = '--help' in arguments or '-h' in arguments
    app=None
    resources=None
    name='unknown'
    request={}
    output_file=None
    invocation_id=uuid4().hex
    started=perf_counter()
    phase='bootstrap'
    try:
        resources=bootstrap(logging_enabled=not help_requested)
        phase='argument_parsing'
        request,config,data_root,log_level,output_file=parse_request(arguments,resources)
        name=request['operation']
        app=Application(config,data_root,resources,log_level)
        invocation_id=app.invocation_id
        phase='execution'
        response=execute(app,request)
    except Exception as exc:
        response=failure(name,exc,'STARTUP_FAILED')
        if not help_requested:
            logger=resources.logger if resources else StoryLogger(PROJECT_ROOT/'story-data/default_logs')
            logger.error('startup.failed',code=response['error']['code'],error=str(exc),operation=name,
                         invocation_id=invocation_id,phase=phase,duration_ms=round((perf_counter()-started)*1000,3))
    finally:
        if app: app.close()
    serialized=json.dumps(response,ensure_ascii=False,allow_nan=False)
    metrics={'response_characters':len(serialized),
             'response_utf8_bytes':len(serialized.encode('utf-8'))}
    if app:
        app.log_response_metrics(response, request.get('params'), **metrics)
    elif not help_requested and resources and resources.logger:
        resources.logger.info('response.serialized', operation=name, invocation_id=invocation_id,
                              ok=response['ok'], **metrics)
    if output_file is not None:
        try:
            receipt=save_response_file(output_file,serialized)
            with using(resources):validate(receipt,'cli_output_file_result',AGENT)
            if response['ok']:
                serialized=json.dumps({'ok':True,'operation':name,'data':receipt,'error':None},ensure_ascii=False)
        except (OSError,ValueError) as exc:
            response=failure(name,ContractError('OUTPUT_WRITE_FAILED','Response export failed: '+str(exc)),'OUTPUT_WRITE_FAILED')
            serialized=json.dumps(response,ensure_ascii=False)
        if app:
            app.logger.info('response.file_output',operation=name,invocation_id=invocation_id,
                            output_file=str(Path(output_file).absolute()),ok=response['ok'],
                            stdout_characters=len(serialized),stdout_utf8_bytes=len(serialized.encode('utf-8')))
    print(serialized)
    exits=resources.settings['exit_codes'] if resources else {'success':0,'error':1}
    return exits['success'] if response['ok'] else exits['error']

if __name__=='__main__':
    raise SystemExit(main())
