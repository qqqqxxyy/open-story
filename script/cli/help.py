"""On-demand help rendered from the same registry and schemas used by execution."""
import json
import sys
from pathlib import Path


def value_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def shape_text(schema):
    kind=schema.get('type')
    if isinstance(kind,list):kind=' | '.join(kind)
    if kind is None:
        kind='枚举' if 'enum' in schema else '固定值' if 'const' in schema else '联合结构' if any(k in schema for k in ('oneOf','anyOf','allOf')) else '任意合法JSON'
    parts=[str(kind)]
    if 'enum' in schema:parts.append('可选='+value_text(schema['enum']))
    if 'const' in schema:parts.append('值='+value_text(schema['const']))
    if 'default' in schema:parts.append('默认='+value_text(schema['default']))
    for key,label in (('minimum','最小'),('maximum','最大'),('minLength','最短'),('maxLength','最长'),
                      ('minItems','最少项'),('minProperties','最少字段'),('pattern','格式')):
        if key in schema:parts.append(label+'='+str(schema[key]))
    if schema.get('uniqueItems'):parts.append('项不重复')
    if schema.get('required') and not schema.get('properties'):
        parts.append('必填字段='+value_text(schema['required']))
    return '；'.join(parts)


def binding_required(resources,entry,binding):
    shape,document=resources.validator.resolve_context(entry['input_schema'])
    required=True
    for component in binding['path']:
        if component not in shape.get('properties',{}):return False
        required=required and component in shape.get('required',[])
        shape,document=resources.validator.resolve_context(shape['properties'][component],document)
    return required


def parameter_help(resources,entry,binding):
    if binding['kind']=='filters':return binding.get('description','外层FIELD=VALUE筛选；可重复。')
    shape=resources.validator.resolve(binding['schema'])
    name=binding['path'][-1]
    description=binding.get('description',shape.get('description',resources.settings.get('help',{}).get('field_descriptions',{}).get(name,'')))
    required='必填' if binding_required(resources,entry,binding) else '可选'
    file='；UTF-8 JSON文件，-读取stdin' if binding['kind']=='json_file' else ''
    return required+'；'+shape_text(shape)+file+('；'+description if description else '')


def structure(resources,schema,label,required=False,depth=0,document=None,seen=()):
    """Expand only the selected API, with bounded recursion and cycle protection."""
    reference=schema.get('$ref')
    shape,document=resources.validator.resolve_context(schema,document)
    descriptions=resources.settings.get('help',{}).get('field_descriptions',{})
    description=shape.get('description',descriptions.get(label.split('.')[-1].removesuffix('[]'),''))
    prefix='  '*depth
    lines=[prefix+label+(' [必填]' if required else '')+': '+shape_text(shape)+(' — '+description if description else '')]
    if reference is not None and reference in seen:
        lines.append(prefix+'  同一结构引用，停止重复展开。');return lines
    seen=seen+(reference,) if reference else seen
    if depth>=resources.settings.get('help',{}).get('max_depth',4):
        if shape.get('properties') or shape.get('items'):lines.append(prefix+'  更深层字段按所引用契约；此处折叠。')
        return lines
    for key,child in shape.get('properties',{}).items():
        lines.extend(structure(resources,child,key,key in shape.get('required',[]),depth+1,document,seen))
    if 'properties' in shape or shape.get('type')=='object':
        extra=shape.get('additionalProperties',True)
        lines.append(prefix+'  '+('额外字段不允许。' if extra is False else '其他字段/值保持开放JSON。' if extra is True else '其他字段按附加字段契约。'))
    if 'items' in shape:
        lines.extend(structure(resources,shape['items'],label.split('.')[-1]+'[]',False,depth+1,document,seen))
    for union in ('oneOf','anyOf','allOf'):
        for index,child in enumerate(shape.get(union,[]),1):
            lines.extend(structure(resources,child,union+'分支'+str(index),False,depth+1,document,seen))
    for keyword in ('if','then','else','not'):
        if keyword in shape:lines.extend(structure(resources,shape[keyword],keyword,False,depth+1,document,seen))
    return lines


def _quote(value):
    value=str(value)
    return "'"+value.replace("'","''")+"'" if any(c.isspace() or c in '<>' for c in value) else value


def command_description(entry):
    state='预留/未实现' if entry['storage_mode']=='reserved' else '可用'
    return '['+state+'] '+entry.get('help',{}).get('summary',entry['operation'])


def command_details(resources,entry):
    meta=entry.get('help',{})
    sections=['行为：'+meta.get('effect','具体行为见handler定义。')]
    payloads=[b for b in entry['bindings'] if b['kind']=='json_file']
    if payloads:
        sections.extend(['','JSON内容契约：'])
        for binding in payloads:
            sections.extend(structure(resources,binding['schema'],binding['flag']))
        sections.append('内容中的未知表意键仅在契约允许的开放区域保留；JSON文件读取不改写字符串。')
    shape=resources.validator.resolve(entry['input_schema'])
    variants=shape.get('allOf',[])
    if variants:
        sections.extend(['','条件与内容契约：'])
        for variant in variants:
            condition=variant.get('if',{})
            kind=condition.get('properties',{}).get('kind',{}).get('const')
            if kind is None:
                kind=next((part.get('properties',{}).get('kind',{}).get('const') for part in condition.get('allOf',[]) if 'kind' in part.get('properties',{})),None)
            content=variant.get('then',{}).get('properties',{}).get('content')
            if kind and content:sections.extend(structure(resources,content,'kind='+kind))
            else:sections.extend(structure(resources,variant,'条件约束'))
    for union in ('oneOf','anyOf'):
        for index,variant in enumerate(shape.get(union,[]),1):
            sections.extend(structure(resources,variant,union+'输入分支'+str(index)))
    sections.extend(['','返回：'])
    if entry['storage_mode']=='reserved':
        sections.append('  当前未实现，无成功业务结果；调用返回NOT_IMPLEMENTED。')
    else:
        sections.append('  成功：ok=true，operation='+entry['operation']+'，error=null；data结构如下。')
        sections.extend(structure(resources,entry['output_schema'],'data'))
    sections.extend(['','CLI文件输出：',
        '  --output-file只影响CLI传输，不进入operation.params；文件保存完整统一响应包络。',
        '  写入成功且业务成功时，stdout的data改为下列文件回执；不再输出大正文。',
        '  业务失败时也可转储错误包络，stdout仍返回原错误；写文件失败返回OUTPUT_WRITE_FAILED及非零退出码。'])
    sections.extend(structure(resources,{'$ref':resources.schemas['agent']['$id']+'#/definitions/cli_output_file_result'},'文件回执data'))
    sections.extend(['  失败：ok=false，data=null，error={code:string,message:string,details?:object}。',
                     '  退出码：成功='+str(resources.settings['exit_codes']['success'])+'，失败='+str(resources.settings['exit_codes']['error'])+'。'])
    sections.extend(structure(resources,{'$ref':resources.schemas['agent']['$id']+'#/definitions/partial_operation_details'},'error.details（仅部分完成时可选）'))
    if meta.get('notes'):
        sections.extend(['','前提与说明：'])
        sections.extend('  - '+note for note in meta['notes'])
    if meta.get('errors'):
        sections.extend(['','相关错误（非穷尽）：'])
        for code in meta['errors']:
            sections.append('  '+code+'：'+resources.errors.get(code,{}).get('description','见全局错误码定义。'))
    if meta.get('examples'):
        sections.extend(['','示例（请替换占位值；下面展示实际调用，会按上述行为读写）：'])
        for example in meta['examples']:
            arguments = example['arguments']
            command = "& '"+sys.executable.replace("'","''")+"' -B -X utf8 '"+str(Path(__file__).with_name('main.py').resolve())+"' "+entry['cli_name']+' '+' '.join(_quote(v) for v in arguments)
            stdin_content = 'content' in example and any(
                binding['flag'] in arguments and arguments[arguments.index(binding['flag'])+1] == '-'
                for binding in payloads)
            if stdin_content:
                sections.append('$OutputEncoding = [System.Text.UTF8Encoding]::new($false)')
                sections.append("@'")
                sections.extend(json.dumps(example['content'],ensure_ascii=False,indent=2).splitlines())
                sections.append("'@ | "+command)
            else:
                sections.append('  '+command)
                if 'content' in example:
                    sections.append('  对应内容文件示例：')
                    sections.extend('    '+line for line in json.dumps(example['content'],ensure_ascii=False,indent=2).splitlines())
    sections.extend(['','查询本help只加载脚本配置与契约，不实例化日志或检查轮转，不打开故事库，不执行handler，也不读取内容文件。'])
    return '\n'.join(sections)
