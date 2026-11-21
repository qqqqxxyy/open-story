"""Storage-only defaults, errors and pagination; no agent operation dependency."""
from datetime import datetime, timezone
import uuid
from script.util.contracts import DATA, ContractError, validate
from script.util.runtime import current
DataError = ContractError
IDS = {k:k+'_id' for k in ('node','object','event','relation')}
def now():return datetime.now(timezone.utc).isoformat()
def make_id(prefix):return prefix+'-'+uuid.uuid4().hex


def prepare(entity,value):
    value=dict(value)
    defaults={'node':{'node_type':'scene','state':'creating',**{k:None for k in ('predecessor_node_id','narrative_event_id','summary_event_id')}},'event':{'event_action':'append','state':'active'},
              'relation':{'state':'active',**{k:None for k in ('target_node_id','target_event_id','target_object_id')}},'object':{}}
    for key,default in defaults[entity].items():value.setdefault(key,default)
    validate(value,entity+'_input')
    return value


def check_filters(entity,filters):
    fields=DATA['definitions'][entity]['properties']
    if not isinstance(filters,dict) or set(filters)-set(fields):
        raise DataError('INVALID_FILTER','Filter only documented outer fields')
    if 'content' in filters:
        raise DataError('INVALID_FILTER','JSON content is not parsed by this data interface')


def page(items,total,offset,limit):
    result={'items':items,'total':total,'offset':offset,'next_offset':offset+len(items) if offset+len(items)<total else None}
    validate(result,'page')
    return result


def validate_relation(value):
    present = {kind for kind in ('node','event','object') if value.get('target_'+kind+'_id') is not None}
    rules = current().relation_rules
    rule = rules['types'].get(value['relation_type'])
    if rule is None:
        if rules['default']['targets']=='exactly_one' and len(present)!=1:
            raise ContractError('INVALID_RELATION','Unregistered types have exactly one target')
        return
    if rule.get('key_type') and value['key_type']!=rule['key_type']:
        raise ContractError('INVALID_RELATION','Wrong key type')
    if not set(rule.get('required_targets',[])) <= present or not present <= set(rule['allowed_targets']):
        raise ContractError('INVALID_RELATION','Wrong target shape for '+value['relation_type'])
    if rule.get('state') and value['state']!=rule['state']:
        raise ContractError('INVALID_RELATION','Wrong relation state')
