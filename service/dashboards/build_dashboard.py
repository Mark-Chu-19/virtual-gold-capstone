"""Build provisioned Grafana dashboards using only the Python standard library.

Run from any directory: python service/dashboards/build_dashboard.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent / 'grafana' / 'dashboards'
DS = {'type': 'prometheus', 'uid': 'prometheus'}
S = 'job="vg-redactor",instance=~"$instance"'
R = S + ',route="/v3/redaction",method="POST"'
W = '$__rate_interval'


def metric(name, labels=''):
    return name + '{' + S + (',' + labels if labels else '') + '}'


def panel(title, kind, x, y, w, h, queries=(), unit='short', description='', **defaults):
    targets = []
    for i, (expr, legend) in enumerate(queries):
        target = dict(refId=chr(65+i), expr=expr, legendFormat=legend, datasource=DS)
        if kind in ('stat', 'gauge', 'bargauge', 'table'):
            target.update(instant=True, range=False)
        if kind == 'table':
            target['format'] = 'table'
        targets.append(target)
    p = dict(title=title, type=kind, description=description, datasource=DS,
             gridPos=dict(x=x, y=y, w=w, h=h), targets=targets,
             fieldConfig=dict(defaults=dict(unit=unit, noValue='No data', **defaults), overrides=[]),
             options=dict(legend=dict(displayMode='table', placement='bottom', calcs=['lastNotNull']),
                          tooltip=dict(mode='multi')))
    if kind in ('stat', 'gauge', 'bargauge'):
        p['options'] = dict(reduceOptions=dict(calcs=['lastNotNull'], fields='', values=False),
                            colorMode='value', graphMode='none', textMode='auto', orientation='auto')
    if kind == 'table':
        p['options'] = dict(showHeader=True)
    return p


def row(title, y):
    return dict(type='row', title=title, collapsed=False, gridPos=dict(x=0,y=y,w=24,h=1), panels=[])


def quantiles(name, labels, grouping='mode', qs=(0.5, 0.95, 0.99)):
    return [(f'histogram_quantile({q}, sum by (le,{grouping}) (rate({metric(name+"_bucket", labels)}[{W}])))',
             f'p{int(q*100)} {{{{{grouping}}}}}') for q in qs]


def stacked(p):
    p['fieldConfig']['defaults']['custom'] = dict(stacking=dict(mode='normal',group='A'),fillOpacity=45)
    return p


def dashboard(title, uid, panels):
    for i, p in enumerate(panels, 1):
        p['id'] = i
    return dict(uid=uid, title=title, tags=['virtual-gold'], timezone='browser', schemaVersion=39,
                version=2, refresh='5s', time=dict(**{'from':'now-15m','to':'now'}), editable=False,
                graphTooltip=1, panels=panels, annotations=dict(list=[]),
                timepicker=dict(refresh_intervals=['5s','10s','30s','1m'],time_options=['15m','1h','24h']),
                templating=dict(list=[dict(name='instance',label='Service instance',type='query',datasource=DS,
                    query='label_values(up{job="vg-redactor"}, instance)',refresh=1,multi=False,includeAll=False)]))


def service_dashboard():
    p = []
    add = p.append
    add(row('Service overview · live health, not benchmark accuracy',0))
    add(panel('Metrics scrape', 'stat',0,1,4,4,[(f'up{{{S}}}','Scrape')],unit='none',
              mappings=[dict(type='value',options={'0':dict(text='DOWN',color='red'),'1':dict(text='UP',color='green')})]))
    add(panel('Model endpoint probe', 'stat',4,1,4,4,[(metric('vg_component_up','component="model_endpoint"'),'Model endpoint')],unit='none',
              description='Endpoint reachability only. Does not prove model generation or parsing works.',
              mappings=[dict(type='value',options={'-1':dict(text='UNKNOWN',color='gray'),'0':dict(text='UNREACHABLE',color='orange'),'1':dict(text='REACHABLE',color='green')})]))
    add(panel('Redaction requests · selected range','stat',8,1,4,4,
              [(f'sum(increase(vg_http_requests_total{{{R}}}[$__range]))','Requests')]))
    success = f'sum(rate(vg_http_requests_total{{{R},status=~"2.."}}[{W}]))'
    base = f'sum(rate(vg_http_requests_total{{{R}}}[{W}]))'
    failures = f'sum(rate(vg_http_requests_total{{{R},status=~"5.."}}[{W}]))'
    success = f'({success} or ({base} * 0))'
    failures = f'({failures} or ({base} * 0))'
    availability = f'{success} / ({success} + {failures})'
    add(panel('HTTP availability','stat',12,1,4,4,[(availability,'Availability')],unit='percentunit',min=0,max=1,
              description='POST redaction: 2xx / (2xx + 5xx). Excludes 4xx. Degraded 200 is available. No traffic is undefined.'))
    degraded = f'sum(rate({metric("vg_redaction_responses_total", "mode=\"degraded\"")}[{W}]))'
    completed = f'sum(rate({metric("vg_redaction_responses_total", "mode=~\"normal|degraded\"")}[{W}]))'
    add(panel('Degraded share of successful redactions','stat',16,1,4,4,[(f'{degraded} / {completed}','Degraded')],unit='percentunit',min=0,max=1))
    occupancy = f'({metric("vg_records_active")} + {metric("vg_records_reserved")}) / {metric("vg_records_capacity")}'
    add(panel('Session capacity used','gauge',20,1,4,4,[(occupancy,'Active + reserved')],unit='percentunit',min=0,max=1))
    add(row('Requests and performance',5))
    add(stacked(panel('Requests by HTTP status','timeseries',0,6,12,8,
        [(f'sum by (status) (rate(vg_http_requests_total{{{R}}}[{W}]))','{{status}}')],unit='reqps',description='POST /v3/redaction only. Includes authentication failures.')))
    add(panel('HTTP end-to-end latency · successful redactions','timeseries',12,6,12,8,
        quantiles('vg_http_duration_seconds','route="/v3/redaction",method="POST",mode=~"normal|degraded"'),unit='s',
        description='Server entry through final ASGI body send: validation, sessions, pipeline and serialization. Excludes client network time.'))
    add(panel('Pipeline latency · normal / degraded / error','timeseries',0,14,12,8,
        quantiles('vg_pipeline_duration_seconds','route="redactions"'),unit='s',description='Orchestrator only. Independent of HTTP latency; percentile differences are not overhead measurements.'))
    add(panel('Stage latency · p95','bargauge',12,14,12,8,
        quantiles('vg_stage_duration_seconds','','stage',(0.95,)),unit='s',
        description='Last window p95 by stage. Detection stages run concurrently; do not sum stage percentiles.'))
    add(row('Fallback and model calls',22))
    add(panel('Degraded share · successful responses','timeseries',0,23,8,8,[(f'{degraded} / {completed}','Degraded share')],unit='percentunit',min=0,max=1,
        description='Only final successful degraded responses. Requests failing after fallback count as errors instead.'))
    add(stacked(panel('Degraded responses by cause and stage','timeseries',8,23,8,8,
        [(f'sum by (reason,stage) (rate({metric("vg_degraded_total")}[{W}]))','{{reason}} / {{stage}}')],unit='reqps')))
    add(panel('Model final outcomes · selected range','bargauge',16,23,8,8,
        [(f'sum by (prompt,outcome) (increase({metric("vg_model_calls_total")}[$__range]))','{{prompt}} / {{outcome}}')],
        description='One terminal outcome per invocation, after parsing: ok, timeout, unavailable, unparseable, cancelled. Queue timeouts count as invocations.'))
    add(row('Sessions, observed components and versions',31))
    add(panel('Session slots','timeseries',0,32,8,8,
        [(metric('vg_records_active'),'Active'),(metric('vg_records_reserved'),'Reserved'),(metric('vg_records_capacity'),'Capacity')]))
    add(panel('Capacity rejections · selected range','stat',8,32,4,4,
        [(f'increase({metric("vg_capacity_rejected_total")}[$__range])','Capacity rejected')],description='Only capacity-exhausted; not all HTTP 503 responses.'))
    add(panel('Removed sessions · selected range','bargauge',8,36,4,4,
        [(f'sum by (reason) (increase({metric("vg_records_removed_total")}[$__range]))','{{reason}}')]))
    add(panel('Components · last observed result','table',12,32,6,8,[(metric('vg_component_up'),'')],
        description='Rules and Presidio report last actual execution, not continuous probes. -1 = not observed, 0 = failure, 1 = success.'))
    info = panel('Versions and runtime backends','table',18,32,6,8,[(metric('vg_build_info'),''),(metric('vg_runtime_info'),'')],
        description='Default model backend is stub. Mixed components still include stub prompts/parsers. Version metadata is not evidence of benchmark accuracy.')
    info['transformations'] = [dict(id='merge',options={}), dict(id='filterFieldsByName',options=dict(include=dict(names=['service','contract','policy','model','prompt_detection','prompt_assessment','context_store','model_backend','restoration_backend','components'])))]
    add(info)
    # Distinguish degraded lines consistently without changing their units.
    for item in p:
        if item.get('type') == 'timeseries' and 'latency' in item['title'].lower():
            item['fieldConfig']['overrides'].append(dict(matcher=dict(id='byRegexp',options='/degraded/'),properties=[dict(id='custom.lineStyle',value=dict(fill='dash',dash=[8,4]))]))
    diagnostics = row('Diagnostics · expand for model queues, API lifecycle and decisions',40)
    diagnostics['collapsed'] = True
    d = diagnostics['panels']
    d.append(panel('Model slot queue wait · p50/p95/p99','timeseries',0,41,12,8,
        quantiles('vg_model_queue_wait_seconds','','prompt'),unit='s',
        description='Includes successful and timed-out queue waits. Separate from execution latency.'))
    d.append(panel('Model execution and parsing · p50/p95/p99','timeseries',12,41,12,8,
        quantiles('vg_model_call_duration_seconds','','prompt'),unit='s',
        description='After acquiring the slot through generation and parsing. Queue-only timeouts have no execution sample.'))
    d.append(panel('In-flight redaction requests','timeseries',0,49,6,8,
        [(metric('vg_inflight_requests'),'In flight')],
        description='Requests admitted to pipeline processing; excludes rejected validation and capacity requests.'))
    d.append(panel('Stage latency trend · p95','timeseries',6,49,18,8,
        quantiles('vg_stage_duration_seconds','','stage',(0.95,)),unit='s'))
    api_labels = 'route=~"$diagnostic_route",method=~"$diagnostic_method"'
    d.append(stacked(panel('API lifecycle · selected route and method','timeseries',0,57,12,8,
        [(f'sum by (route,method,status) (rate({metric("vg_http_requests_total",api_labels)}[{W}]))','{{route}} {{method}} / {{status}}')],unit='reqps',
        description='Use diagnostic filters to inspect redaction, restore and delete independently. Overview metrics remain POST redaction only.')))
    d.append(panel('HTTP latency · selected operation and status','timeseries',12,57,12,8,
        [(f'histogram_quantile(0.95, sum by (le,route,method,status) (rate({metric("vg_http_duration_seconds_bucket",api_labels)}[{W}])))','p95 {{route}} {{method}} / {{status}}')],unit='s',
        description='Includes errors and restore/delete; separated by status so fast rejects do not hide slow successful operations.'))
    d.append(panel('Rendered span decisions · selected range','bargauge',0,65,12,8,
        [(f'sum by (tier,action,mode) (increase({metric("vg_spans_total")}[$__range]))','{{tier}} / {{action}} / {{mode}}')],
        description='Rendered decisions, including attempts that later fail audit/serialization. Missed entities are absent; this cannot measure leak rate or accuracy.'))
    good = metric('vg_model_calls_total','outcome="ok"')
    all_calls = metric('vg_model_calls_total')
    d.append(panel('Model calls with valid parsed output','timeseries',12,65,12,8,
        [(f'sum by (prompt) (rate({good}[{W}])) / sum by (prompt) (rate({all_calls}[{W}]))','{{prompt}}')],unit='percentunit',min=0,max=1,
        description='Final ok / all terminal outcomes, including queue timeout and cancellation. Not model accuracy.'))
    for i,item in enumerate(d,100):
        item['id'] = i
    add(diagnostics)
    result = dashboard('Virtual Gold: Redaction Service','vg-redactor',p)
    result['templating']['list'].extend([
        dict(name='diagnostic_route',label='Diagnostic route',type='custom',query='/v3/redaction,/v3/restore',multi=True,includeAll=True,allValue='/v3/redaction|/v3/restore',current=dict(text='All',value='$__all')),
        dict(name='diagnostic_method',label='Diagnostic method',type='custom',query='POST,DELETE',multi=True,includeAll=True,allValue='POST|DELETE',current=dict(text='All',value='$__all')),
    ])
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT/'vg-redactor.json').write_text(json.dumps(service_dashboard(),indent=2)+'\n')


if __name__ == '__main__':
    main()
