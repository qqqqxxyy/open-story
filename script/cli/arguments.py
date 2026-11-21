"""Generic argument binding. All command descriptions come from conf/operations.json."""
import argparse
import json
from pathlib import Path
import sys
import textwrap
from script.util.errors import ContractError
from script.util.runtime import current
from .help import parameter_help, binding_required, command_description, command_details

class HelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self,prog):
        super().__init__(prog,width=100,max_help_position=28)
    def _split_lines(self,text,width):
        return textwrap.wrap(text,width,break_long_words=False,break_on_hyphens=False)

class Parser(argparse.ArgumentParser):
    def format_help(self):
        if hasattr(self, '_help_entry'):
            self.epilog = command_details(self._help_resources, self._help_entry)
        return super().format_help()

    def error(self, message):
        raise ContractError('INVALID_ARGUMENT', message)

def json_file(filename):
    raw = sys.stdin.read() if filename=='-' else Path(filename).read_text(encoding='utf-8-sig')
    return json.loads(raw)

def _kind(schema):
    kind = schema.get('type')
    if isinstance(kind,list): kind = next(k for k in kind if k!='null')
    if kind is None and schema.get('enum'):
        return 'boolean' if isinstance(schema['enum'][0], bool) else 'string'
    return kind

def _field(parser, binding, resources, entry):
    destination = '__'.join(binding['path'])
    options = {'dest':destination, 'default':argparse.SUPPRESS, 'required':binding_required(resources,entry,binding),
               'help':parameter_help(resources,entry,binding)}
    kind = binding['kind']
    if kind=='filters':
        options.update(action='append', metavar='FIELD=VALUE')
    elif kind=='json_file':
        options['metavar'] = 'JSON_PATH_OR_-'
    else:
        schema = resources.validator.resolve(binding['schema'])
        value_kind = _kind(schema)
        if value_kind=='boolean':
            options['action'] = argparse.BooleanOptionalAction
        elif value_kind=='array':
            item = resources.validator.resolve(schema['items'])
            options.update(nargs='+', type=int if _kind(item)=='integer' else str)
            if item.get('enum'): options['choices'] = item['enum']
        else:
            options['type'] = int if value_kind=='integer' else float if value_kind=='number' else str
            if schema.get('enum'): options['choices'] = schema['enum']
    parser.add_argument(binding['flag'], **options)

def build_parser(resources=None):
    resources = resources or current()
    settings = resources.settings['cli']
    parser = Parser(description=settings['description'],
                    epilog='按需查询：main.py <子命令> --help。单命令help包含参数、内容、返回和示例。',
                    formatter_class=HelpFormatter)
    subcommands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    for entry in resources.operations.values():
        child = subcommands.add_parser(entry['cli_name'], help=command_description(entry),
                                       description=command_description(entry),
                                       formatter_class=HelpFormatter)
        child._help_entry = entry
        child._help_resources = resources
        child.set_defaults(entry=entry)
        mode = entry['storage_mode']
        if mode!='initialize': child.add_argument(settings['config_flag'], dest='config', required=mode=='existing', help=resources.settings['help']['common_arguments']['config'])
        if mode!='existing': child.add_argument(settings['data_root_flag'], dest='data_root', help=resources.settings['help']['common_arguments']['data_root'])
        child.add_argument(settings['log_level_flag'], dest='log_level', choices=('debug','info','warn','error'),
                           help=resources.settings['help']['common_arguments']['log_level']+' 当前默认='+resources.settings['logging']['level'])
        child.add_argument(settings['output_file_flag'], dest='output_file', metavar='JSON_PATH',
                           help=resources.settings['help']['common_arguments']['output_file'])
        for binding in entry['bindings']: _field(child,binding,resources,entry)
    return parser

def _filters(expressions, binding, params, resources):
    definitions = resources.validator.resolve(binding['fields_schema'])
    entity = params.get(binding['entity_parameter'], binding['default_entity'])
    fields = definitions[entity]['properties']
    result = {}
    for expression in expressions:
        key, separator, value = expression.partition('=')
        if not separator or key not in fields or key in binding.get('exclude',[]):
            raise ContractError('INVALID_FILTER','Use a documented outer field: FIELD=VALUE')
        shape = fields[key]
        value = int(value) if _kind(shape)=='integer' else None if value=='null' and isinstance(shape.get('type'),list) and 'null' in shape['type'] else value
        if key in result:
            previous = result[key]
            result[key] = previous+[value] if isinstance(previous,list) else [previous,value]
        else: result[key]=value
    return result

def parse_request(argv=None, resources=None):
    resources = resources or current()
    arguments = vars(build_parser(resources).parse_args(argv))
    entry = arguments['entry']
    params = {name:{} for name in entry['containers']}
    deferred = []
    for binding in entry['bindings']:
        destination = '__'.join(binding['path'])
        if destination not in arguments: continue
        if binding['kind']=='filters':
            deferred.append((binding,arguments[destination])); continue
        value = json_file(arguments[destination]) if binding['kind']=='json_file' else arguments[destination]
        target = params
        for component in binding['path'][:-1]: target=target.setdefault(component,{})
        target[binding['path'][-1]]=value
    for binding,expressions in deferred:
        params[binding['path'][0]]=_filters(expressions,binding,params,resources)
    return ({'operation':entry['operation'],'params':params}, arguments.get('config'),
            arguments.get('data_root'), arguments.get('log_level'), arguments.get('output_file'))