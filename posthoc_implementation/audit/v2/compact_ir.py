"""Lossless schema-aware positional encoding, with public bookkeeping only.

No reference IR, default service choices, missing-value completion, or semantic
repair. Every required non-bookkeeping value must be present in model output.
"""
from __future__ import annotations

import copy
import json

from jsonschema import Draft202012Validator

FORMAT='p2sf.compact_ir/1'
BOOKKEEPING=('ir_version','composition_id','catalog_snapshot','source')
COMPOSITE=('allOf','anyOf','oneOf','if','then','else','not')


def strict_json(text):
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    def invalid(_):raise ValueError('Non-finite JSON value')
    return json.loads(text,object_pairs_hook=pairs,parse_constant=invalid)


class Codec:
    def __init__(self,schema,metadata):
        self.full=copy.deepcopy(schema);self.metadata=copy.deepcopy(metadata)
        if set(metadata)!=set(BOOKKEEPING):raise ValueError('Bookkeeping fields must be exact')
        # Only the fixed identity/format fields are externally supplied.
        if metadata['ir_version']!='0.1.0':raise ValueError('Unsupported IR version')
        self.body=copy.deepcopy(schema)
        for key in BOOKKEEPING:
            self.body['properties'].pop(key,None)
        self.body['required']=[k for k in self.body['required'] if k not in BOOKKEEPING]
        self.columns={}
        transformed=self.transform(self.body,'record')
        definitions={key:self.transform(value,'$defs/'+key) for key,value in self.full.get('$defs',{}).items()}
        transformed.pop('$defs',None);transformed.pop('$id',None);transformed.pop('$schema',None)
        self.schema={'$schema':'https://json-schema.org/draft/2020-12/schema',
            '$id':'https://prompt2serviceflow.local/v2/compact_ir_1.schema.json',
            'type':'object','required':['format','record'],'additionalProperties':False,
            'properties':{'format':{'const':FORMAT},'record':transformed},'$defs':definitions}
        Draft202012Validator.check_schema(self.schema)
        self.validate_local_refs(self.full)

    def resolve(self,node):
        while isinstance(node,dict) and '$ref' in node:
            reference=node['$ref']
            if not reference.startswith('#/$defs/') or reference.count('/')!=2:
                raise ValueError('Only direct local definition references are supported')
            node=self.full['$defs'][reference.rsplit('/',1)[1]]
        return node

    def validate_local_refs(self,node,in_composite=False):
        if isinstance(node,dict):
            if '$ref' in node:
                resolved=self.resolve(node)
                if in_composite and self.is_record(resolved):
                    raise ValueError('Record reference inside conditional/union requires a new codec version')
            for key,value in node.items():
                self.validate_local_refs(value,in_composite or key in COMPOSITE)
        elif isinstance(node,list):
            for value in node:self.validate_local_refs(value,in_composite)

    @staticmethod
    def is_record(node):
        return (isinstance(node,dict) and node.get('type')=='object' and isinstance(node.get('properties'),dict)
                and bool(node.get('required')) and not any(k in node for k in COMPOSITE))

    def transform(self,node,path):
        if not isinstance(node,dict):return node
        if '$ref' in node:return copy.deepcopy(node)
        if any(k in node for k in COMPOSITE):return copy.deepcopy(node)
        if self.is_record(node):
            required=node['required'];optional={k:v for k,v in node['properties'].items() if k not in required}
            extras=bool(optional) or node.get('additionalProperties',True) is not False
            self.columns[path]=required+(['optional_fields'] if extras else [])
            slots=[{**self.transform(node['properties'][k],path+'/'+k),'title':k} for k in required]
            if extras:
                extra={'type':'object','properties':{k:self.transform(v,path+'/'+k) for k,v in optional.items()},
                       'additionalProperties':copy.deepcopy(node.get('additionalProperties',True)),'title':'optional_fields'}
                slots.append(extra)
            return {'type':'array','prefixItems':slots,'items':False,'minItems':len(slots),'maxItems':len(slots),
                    'description':'Object fields in fixed order: '+', '.join(self.columns[path])+'. No omitted slots or inferred defaults.'}
        value=copy.deepcopy(node)
        for key in ('properties',):
            if isinstance(value.get(key),dict):value[key]={k:self.transform(v,path+'/'+k) for k,v in value[key].items()}
        if isinstance(value.get('items'),dict):value['items']=self.transform(value['items'],path+'/*')
        if isinstance(value.get('additionalProperties'),dict):value['additionalProperties']=self.transform(value['additionalProperties'],path+'/*')
        value.pop('$defs',None)
        return value

    def convert(self,value,node,decode):
        node=self.resolve(node)
        if not isinstance(node,dict) or any(k in node for k in COMPOSITE):return copy.deepcopy(value)
        if self.is_record(node):
            required=node['required'];optional=set(node['properties'])-set(required)
            extras=bool(optional) or node.get('additionalProperties',True) is not False
            if decode:
                if not isinstance(value,list) or len(value)!=len(required)+int(extras):raise ValueError('Wrong compact record slot count')
                result={k:self.convert(value[i],node['properties'][k],True) for i,k in enumerate(required)}
                if extras:
                    for key,item in value[-1].items():
                        if key in required:raise ValueError('Required field repeated in optional_fields')
                        result[key]=self.convert(item,node['properties'].get(key,node.get('additionalProperties',True)),True)
                return result
            result=[self.convert(value[k],node['properties'][k],False) for k in required]
            if extras:result.append({k:self.convert(v,node['properties'].get(k,node.get('additionalProperties',True)),False) for k,v in value.items() if k not in required})
            return result
        if node.get('type')=='array':return [self.convert(v,node.get('items',True),decode) for v in value]
        if node.get('type')=='object':return {k:self.convert(v,node.get('properties',{}).get(k,node.get('additionalProperties',True)),decode) for k,v in value.items()}
        return copy.deepcopy(value)

    def encode(self,ir):
        Draft202012Validator(self.full).validate(ir)
        if any(ir[k]!=self.metadata[k] for k in BOOKKEEPING):raise ValueError('Public metadata differs; it cannot be silently replaced')
        body={k:v for k,v in ir.items() if k not in BOOKKEEPING}
        value={'format':FORMAT,'record':self.convert(body,self.body,False)}
        Draft202012Validator(self.schema).validate(value)
        return value

    def decode(self,value):
        Draft202012Validator(self.schema).validate(value)
        ir={**self.convert(value['record'],self.body,True),**copy.deepcopy(self.metadata)}
        Draft202012Validator(self.full).validate(ir)
        return ir
