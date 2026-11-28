"""Server-observed call usage and timing. No pricing tables or inferred invoices."""
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4


def money(value):
    if value is None or isinstance(value, bool): return None
    try: number = Decimal(str(value))
    except (InvalidOperation, ValueError): return None
    return str(number) if number.is_finite() and 0 <= number <= 10**9 else None


def tokens(value):
    return value if type(value) is int and 0 <= value <= 10**15 else None


def name(value, fallback='unreported-model'):
    return value if isinstance(value,str) and re.fullmatch(r'[\w./:@+-]{1,160}',value) else fallback


def model_row(provider, model, data):
    return {'provider':name(provider),'model':name(model),
            'input_tokens':tokens(data.get('input_tokens',data.get('inputTokens',data.get('input')))),
            'output_tokens':tokens(data.get('output_tokens',data.get('outputTokens',data.get('output')))),
            'cache_read_tokens':tokens(data.get('cache_read_tokens',data.get('cacheReadInputTokens',data.get('cache_read_input_tokens')))),
            'cache_write_tokens':tokens(data.get('cache_write_tokens',data.get('cacheCreationInputTokens',data.get('cache_creation_input_tokens')))),
            'cost_usd':money(data.get('cost_usd',data.get('costUSD',data.get('cost'))))}


def cli_usage(tool, raw):
    """Read vendor envelopes, never model-written structured_output/report text."""
    try:
        if tool=='claude':
            value=json.loads(raw)
            if not isinstance(value,dict): return [],None
            detail=value.get('modelUsage')
            rows=[model_row('anthropic',model,data) for model,data in list(detail.items())[:100] if isinstance(data,dict)] if isinstance(detail,dict) else []
            if not rows and isinstance(value.get('usage'),dict):
                rows=[model_row('anthropic',value.get('model','unreported-model'),value['usage'])]
            return rows,money(value.get('total_cost_usd'))
        rows=[];seen=set()
        for line in raw.splitlines():
            try:event=json.loads(line)
            except (ValueError,UnicodeError):continue
            if not isinstance(event,dict):continue
            part=event.get('part',{})
            if event.get('type')!='step_finish' or not isinstance(part,dict): continue
            key=part.get('id')
            if key and key in seen: continue
            if key:seen.add(key)
            usage=part.get('tokens',{})
            if not isinstance(usage,dict):usage={}
            cache=usage.get('cache',{})
            rows.append(model_row('opencode',part.get('modelID',part.get('model','unreported-model')),dict(usage,cost=part.get('cost'),
                cache_read_tokens=cache.get('read') if isinstance(cache,dict) else None,
                cache_write_tokens=cache.get('write') if isinstance(cache,dict) else None)))
        return combine_models(rows),str(sum(Decimal(r['cost_usd']) for r in rows)) if rows and all(r['cost_usd'] is not None for r in rows) else None
    except (ValueError,TypeError,AttributeError,UnicodeError):return [],None


def combine_models(rows):
    result={}
    for row in rows:
        key=(row['provider'],row['model'])
        if key not in result:result[key]=dict(row);continue
        total=result[key]
        for field in ('input_tokens','output_tokens','cache_read_tokens','cache_write_tokens','cost_usd'):
            if total[field] is None or row[field] is None:total[field]=None
            else:total[field]=str(Decimal(total[field])+Decimal(row[field])) if field=='cost_usd' else total[field]+row[field]
    return list(result.values())


def call(tool, payload, requested_model, started_at, ended_at, seconds, raw=b''):
    rows,cost=cli_usage(tool,raw)
    if cost is None and rows and all(row['cost_usd'] is not None for row in rows):cost=str(sum(Decimal(row['cost_usd']) for row in rows))
    return {'id':uuid4().hex,'tool':tool,'role':str(payload.get('stage','model'))[:40],
            'requested_model':name(requested_model,'configured'),'started_at':started_at,'ended_at':ended_at,
            'duration_seconds':round(seconds,6),'models':rows,'cost_usd':cost}


def timestamp(value):
    if not isinstance(value,str):return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError,OverflowError):return None


def normalize_calls(values):
    if not isinstance(values,list) or len(values)>200:return []
    result=[]
    for value in values:
        if not isinstance(value,dict) or not re.fullmatch(r'[a-f0-9]{32}',str(value.get('id',''))):continue
        duration=value.get('duration_seconds')
        if isinstance(duration,bool) or not isinstance(duration,(int,float)) or not math.isfinite(duration) or not 0<=duration<=604800:continue
        if timestamp(value.get('started_at')) is None or timestamp(value.get('ended_at')) is None:continue
        models=value.get('models',[])
        if not isinstance(models,list) or len(models)>100:continue
        clean={key:value.get(key) for key in ('id','started_at','ended_at','duration_seconds')}
        clean.update(tool=name(value.get('tool')),role=name(value.get('role'),'model'),requested_model=name(value.get('requested_model'),'configured'),
                     models=[model_row(row.get('provider'),row.get('model'),row) for row in models if isinstance(row,dict)],cost_usd=money(value.get('cost_usd')))
        if value.get('module_id'):clean['module_id']=str(value['module_id'])[:100]
        result.append(clean)
    return result


def merge_calls(target, values):
    """One immutable record per server call ID; replay never adds cost again."""
    seen={entry['id'] for entry in target}
    for entry in normalize_calls(values):
        if entry['id'] not in seen:target.append(entry);seen.add(entry['id'])


def timing(attempt, clock):
    start=timestamp(attempt.get('started_at'));end=timestamp(attempt.get('ended_at'))
    active=attempt.get('status',attempt.get('state')) in {'RUNNING','DISPATCHING','WAITING_INPUT','UNKNOWN','CANCEL_REQUESTED'}
    if start is not None and end is None and active:end=clock
    if start is None or end is None or start>end:return None
    return start,end


def summarize(attempts, simulation=False, clock=None):
    clock=clock if clock is not None else datetime.now(timezone.utc).timestamp()
    calls={};missing=False;spans=[]
    for attempt in attempts:
        span=timing(attempt,clock)
        if span:spans.append(span)
        rows=attempt.get('telemetry_calls',[])
        if not simulation and attempt.get('tool') in {'claude','opencode'} and not rows:missing=True
        for row in rows:calls.setdefault(row['id'],row)
    values=list(calls.values());rows=[row for value in values for row in value.get('models',[])]
    reported=[Decimal(value['cost_usd']) for value in values if value.get('cost_usd') is not None]
    unavailable=missing or any(value.get('cost_usd') is None for value in values)
    status='partial' if reported and unavailable else 'unavailable' if unavailable else 'reported' if values else 'not_applicable'
    return {'status':status,'models':combine_models(rows),'reported_cost_usd':str(sum(reported)) if reported else None,
            'cost_usd':None if unavailable or not values else str(sum(reported)),
            'round_count':len(attempts),'call_count':len(values),
            'tokens_partial':missing or any(not value.get('models') or any(r.get('input_tokens') is None or r.get('output_tokens') is None for r in value['models']) for value in values),
            'total_seconds':round(sum(end-start for start,end in spans),3) if spans else None,
            'elapsed_seconds':round(max(end for _,end in spans)-min(start for start,_ in spans),3) if spans else None,
            'timing_partial':len(spans)!=len(attempts)}


def control_attempt(entry):
    return {'id':entry['id'],'ordinal':1,'tool':entry['tool'],'model':entry['requested_model'],
            'started_at':entry['started_at'],'ended_at':entry['ended_at'],'status':'RECORDED','telemetry_calls':[entry]}


def integration_attempts(job):
    integration=job.get('integration',{})
    return [dict(entry['attempt'],status=entry.get('status'),ended_at=entry.get('ended_at'))
            for entry in [*integration.get('history',[]),integration] if entry.get('attempt')]


def project_telemetry(job):
    clock=datetime.now(timezone.utc).timestamp();simulation=job.get('execution')=='demo';all_attempts=[]
    controls=job.get('control_telemetry',[])
    for module in job['modules']:
        module_attempts=[]
        for stage in module['stages'].values():
            attempts=stage['attempts'];stage['telemetry']=summarize(attempts,simulation,clock)
            module_attempts+=attempts
        module_attempts += [control_attempt(entry) for entry in controls if entry.get('module_id')==module['id']]
        module['telemetry']=summarize(module_attempts,simulation,clock)
        all_attempts += [attempt for stage in module['stages'].values() for attempt in stage['attempts']]
    all_attempts += integration_attempts(job)
    all_attempts += [control_attempt(entry) for entry in controls]
    result=summarize(all_attempts,simulation,clock)
    start=timestamp(job.get('created_at'));end=timestamp((job.get('final_review') or {}).get('at')) or clock
    result['elapsed_seconds']=round(max(0,end-start),3) if start is not None else None
    job['telemetry']=result
    return job
