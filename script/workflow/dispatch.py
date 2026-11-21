"""Registered workflow dispatch, with optional execution-context tracing."""
from importlib import import_module
from script.util.errors import ContractError


def operation(resources, name):
    if name not in resources.operations:
        raise ContractError('UNKNOWN_OPERATION', name)
    return resources.operations[name]


def _phase(context, phase, message, **fields):
    calls = getattr(context, '_calls', [])
    if calls: calls[-1]['phase'] = phase
    trace = getattr(context, 'trace', None)
    if trace: trace(message, **fields)


def dispatch(context, name, params):
    resources = context.resources
    entry = operation(resources, name)
    _phase(context, 'parameter_validation', 'validation.params.started')
    shape = resources.validator.resolve(entry['input_schema'])
    if isinstance(params, dict):
        params = dict(params)
        for key, definition in shape.get('properties', {}).items():
            field = resources.validator.resolve(definition)
            if key not in params and 'default' in field:
                from copy import deepcopy
                params[key] = deepcopy(field['default'])
    resources.validator.validate(params, entry['input_schema'])
    # Log actual defaults, without reserializing creative content.
    calls = getattr(context, '_calls', [])
    if calls:
        if params.get('branch_id'):
            calls[-1]['branch_id'] = params['branch_id']
        database_id = params.get('database_id') or params.get('story_id')
        if database_id:
            calls[-1]['database_id'] = database_id
    _phase(context, 'handler_resolution', 'validation.params.completed')
    route = entry['handler']
    if route not in resources.handlers:
        module, symbol = route.split(':', 1)
        resources.handlers[route] = getattr(import_module(module), symbol)
    _phase(context, 'handler_execution', 'handler.started', function=route)
    result = resources.handlers[route](context, params)
    _phase(context, 'result_validation', 'handler.completed', function=route)
    resources.validator.validate(result, entry['output_schema'])
    _phase(context, 'result_validation', 'validation.result.completed')
    return result
