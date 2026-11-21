"""Reusable validation of caller-supplied schemas; no configuration IO."""
import json
import jsonschema
from referencing import Registry, Resource
from .errors import ContractError
from .runtime import DATA, WORKFLOW, AGENT, current

class SchemaValidator:
    def __init__(self, schemas):
        self.schemas = {schema['$id']:schema for schema in schemas.values()}
        self.registry = Registry().with_resources((uri, Resource.from_contents(schema)) for uri,schema in self.schemas.items())
        self._validators = {}

    def resolve_context(self, schema, document=None):
        if '$ref' not in schema:
            return schema, document
        uri,pointer=schema['$ref'].split('#',1)
        target=self.schemas[uri] if uri else document
        value=target
        for part in pointer.strip('/').split('/'):
            if part:value=value[part.replace('~1','/').replace('~0','~')]
        resolved,origin=self.resolve_context(value,target)
        return {**resolved,**{k:v for k,v in schema.items() if k!='$ref'}},origin

    def resolve(self, schema, document=None):
        return self.resolve_context(schema,document)[0]

    def validate(self, value, schema):
        key = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        if key not in self._validators:
            self._validators[key] = jsonschema.Draft7Validator(schema, registry=self.registry)
        error = next(self._validators[key].iter_errors(value), None)
        if error:
            raise ContractError('INVALID_SCHEMA', '/'.join(map(str,error.absolute_path))+': '+error.message)
        try:
            json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ContractError('INVALID_JSON', str(exc)) from exc

def validate(value, name, catalog=DATA):
    schema = {'$schema':catalog['$schema'], '$ref':catalog['$id']+'#/definitions/'+name}
    current().validator.validate(value, schema)
