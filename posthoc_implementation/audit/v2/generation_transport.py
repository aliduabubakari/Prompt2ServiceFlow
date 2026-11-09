"""One-request compatible chat transport with explicit outcome observations.

Never execute tool calls or substitute reasoning for final assistant content.
The SDK request arguments are logged; they are not proof of server limits.
"""
from __future__ import annotations

import copy
import json
import time
from urllib.parse import urlsplit

SENSITIVE={'apikey','authorization','accesstoken','refreshtoken','password','xapikey'}


def sanitize(value,secret):
    if isinstance(value,dict):return {k:'<redacted>' if str(k).lower().replace('_','').replace('-','') in SENSITIVE else sanitize(v,secret) for k,v in value.items()}
    if isinstance(value,list):return [sanitize(v,secret) for v in value]
    if isinstance(value,str) and secret:return value.replace(secret,'<redacted>')
    return value


def validate_model(config):
    parsed=urlsplit(config['base_url'])
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        raise ValueError('Endpoint must be HTTP(S) without embedded credentials/query')
    if not isinstance(config['api_key_env'],str) or not config['api_key_env']:raise ValueError('Use an environment variable for authentication')
    if not isinstance(config['max_tokens'],int) or isinstance(config['max_tokens'],bool) or config['max_tokens']<1:raise ValueError('Positive configured output budget required')


def request(model,messages):
    return {'model':model['model_name'],'messages':copy.deepcopy(messages),'max_tokens':model['max_tokens'],
            'temperature':model['temperature'],'top_p':model['top_p'],'seed':model['seed']}


def complete(config,request_args,secret,client_factory=None):
    """No SDK automatic retries; at most one inference request per invocation."""
    validate_model(config)
    if not secret:raise ValueError('Missing API token environment variable')
    if client_factory is None:
        from openai import OpenAI
        client_factory=OpenAI
    started=time.monotonic()
    try:
        with client_factory(base_url=config['base_url'],api_key=secret,timeout=config['request_timeout_s'],max_retries=0) as client:
            response=client.chat.completions.create(**request_args)
            raw=response.model_dump(mode='json') if hasattr(response,'model_dump') else response
            if not isinstance(raw,dict):raise TypeError('Completion is not an object')
        return {'status':'response_received','response':sanitize(raw,secret),'latency_s':time.monotonic()-started}
    except Exception as exc:
        # No headers. Sanitize the exception text because providers can echo
        # the API credential when rejecting authentication.
        return {'status':'inference_error','error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None),
                'error_message':sanitize(str(exc),secret),'latency_s':time.monotonic()-started,'response':None}


def observe(payload):
    if payload.get('status')!='response_received':return {'status':payload.get('status','inference_error'),'text':None,'finish_reason':None,'usage':None}
    raw=payload['response'];choices=raw.get('choices')
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
        return {'status':'invalid_completion_shape','text':None,'finish_reason':None,'usage':raw.get('usage')}
    choice=choices[0];message=choice.get('message')
    if not isinstance(message,dict):return {'status':'invalid_assistant_message','text':None,'finish_reason':choice.get('finish_reason'),'usage':raw.get('usage')}
    content=message.get('content');content_supported=True
    if content is None:text=''
    elif isinstance(content,str):text=content
    elif isinstance(content,list) and all(isinstance(b,dict) and b.get('type')=='text' and isinstance(b.get('text'),str) for b in content):text=''.join(b['text'] for b in content)
    else:text=None;content_supported=False
    finish=choice.get('finish_reason');tools=message.get('tool_calls') or message.get('function_call')
    status=('unexpected_tool_call' if tools or finish in ('tool_calls','function_call') else 'unsupported_content_shape' if not content_supported else
            'content_filtered' if finish=='content_filter' else 'output_limit' if finish=='length' else 'empty_response' if not text.strip() else
            'complete_text' if finish=='stop' else 'unrecognized_finish_reason')
    return {'status':status,'text':text,'finish_reason':finish,'usage':raw.get('usage'),
            'reported_model':raw.get('model'),'reasoning_fields_present':[k for k in ('reasoning_content','reasoning','analysis') if message.get(k) is not None],
            'tool_calls_present':bool(tools),'response_id':raw.get('id'),
            'visible_content_characters':len(text) if isinstance(text,str) else None,
            'empty_visible_content':not text.strip() if isinstance(text,str) else None}
