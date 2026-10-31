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
HOST_SOURCE, EVALUATION_SOURCE = 'source="host"', 'source="evaluation"'
PROFILES = json.loads((Path(__file__).parent / 'thresholds.json').read_text())


def metric(name, labels=''):
    return name + '{' + S + (',' + labels if labels else '') + '}'


def panel(title, kind, x, y, w, h, queries=(), unit='short', description='', profile=None, **defaults):
    targets = []
    for i, (expr, legend) in enumerate(queries):
        target = dict(refId=chr(65+i), expr=expr, legendFormat=legend, datasource=DS)
        if kind in ('stat', 'gauge', 'bargauge', 'table'):
            target.update(instant=True, range=False)
        if kind == 'table':
            target['format'] = 'table'
        targets.append(target)
    field_defaults = dict(unit=unit, noValue='No data',
                          color=dict(mode='palette-classic') if kind == 'timeseries' else dict(mode='fixed',fixedColor='blue'),
                          thresholds=dict(mode='absolute',steps=[dict(color='blue',value=None)]))
    field_defaults.update(defaults)
    if profile:
        field_defaults.update(color=dict(mode='thresholds'),thresholds=PROFILES[profile])
        field_defaults['mappings'] = list(field_defaults.get('mappings', [])) + [
            dict(type='special',options=dict(match=missing,result=dict(text='No data',color='gray')))
            for missing in ('null','nan')]
        description += ' Color bands are provisional operational targets, not paging alerts.'
    p = dict(title=title, type=kind, description=description, datasource=DS,
             gridPos=dict(x=x, y=y, w=w, h=h), targets=targets,
             fieldConfig=dict(defaults=field_defaults, overrides=[]),
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


def table_fields(p, names, renames=None):
    """Keep technical Prometheus fields out of user-facing tables."""
    p['transformations'] = [
        dict(id='filterFieldsByName',options=dict(include=dict(names=names))),
        dict(id='organize',options=dict(indexByName={name:i for i,name in enumerate(names)},renameByName=renames or {})),
    ]
    return p


def matrix_table(p, row_name, column_name, columns):
    p['transformations'] = [
        dict(id='filterFieldsByName',options=dict(include=dict(names=[row_name,column_name,'Value']))),
        dict(id='groupingToMatrix',options=dict(rowField=row_name,columnField=column_name,valueField='Value',emptyValue='null')),
        dict(id='organize',options=dict(indexByName={name:i for i,name in enumerate(columns)},renameByName=columns)),
    ]
    return p


def health_column(p, name, profile, unit='short'):
    """Only the health column gets thresholds; activity counts stay neutral."""
    p['fieldConfig']['overrides'].append(dict(matcher=dict(id='byName',options=name),properties=[
        dict(id='unit',value=unit),dict(id='color',value=dict(mode='thresholds')),
        dict(id='thresholds',value=PROFILES[profile]),
        dict(id='custom.cellOptions',value=dict(type='color-text')),
        dict(id='mappings',value=[dict(type='special',options=dict(match=missing,result=dict(text='No data',color='gray'))) for missing in ('null','nan')]),
    ]))


def metadata_query():
    """One vector of setting/value rows, avoiding sparse joins between unrelated info metrics."""
    vectors = []
    for name, labels in (
        ('vg_build_info',('service','contract','policy','model','prompt_detection','prompt_assessment','context_store')),
        ('vg_runtime_info',('model_backend','restoration_backend','components')),
    ):
        for label in labels:
            vectors.append(f'sum by (setting,setting_value) (label_replace(label_replace({metric(name)}, "setting_value", "$1", "{label}", "(.*)"), "setting", "{label}", "__name__", ".*"))')
    return ' or '.join(vectors)


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
    add(panel('HTTP availability','stat',12,1,4,4,[(availability,'Availability')],unit='percentunit',min=0,max=1,profile='availability',
              description='POST redaction: 2xx / (2xx + 5xx). Excludes 4xx. Degraded 200 is available. No traffic is undefined.'))
    degraded_mode, completed_modes = 'mode="degraded"', 'mode=~"normal|degraded"'  # no backslashes in f-strings before 3.12
    degraded = f'sum(rate({metric("vg_redaction_responses_total", degraded_mode)}[{W}]))'
    completed = f'sum(rate({metric("vg_redaction_responses_total", completed_modes)}[{W}]))'
    share = panel('Degraded share of successful redactions','stat',16,1,4,4,[(f'{degraded} / {completed}','Degraded')],unit='percentunit',min=0,max=1,profile='degraded',
                  description='Successful degraded / all successful redactions. Includes the selected-range trend; final failures after fallback count as errors instead.')
    share['targets'][0].update(instant=False,range=True)
    share['options'].update(graphMode='area',wideLayout=False)
    share['options']['reduceOptions']['calcs'] = ['last']
    add(share)
    occupancy = f'({metric("vg_records_active")} + {metric("vg_records_reserved")}) / {metric("vg_records_capacity")}'
    add(panel('Session capacity used','gauge',20,1,4,4,[(occupancy,'Active + reserved')],unit='percentunit',min=0,max=1,profile='capacity'))
    add(row('Requests and performance',5))
    add(stacked(panel('Requests by HTTP status','timeseries',0,6,12,8,
        [(f'sum by (status) (rate(vg_http_requests_total{{{R}}}[{W}]))','{{status}}')],unit='reqps',description='POST /v3/redaction only. Includes authentication failures.')))
    add(panel('HTTP end-to-end latency · successful redactions','timeseries',12,6,12,8,
        quantiles('vg_http_duration_seconds','route="/v3/redaction",method="POST",mode=~"normal|degraded"'),unit='s',
        description='Server entry through final ASGI body send: validation, sessions, pipeline and serialization. Excludes client network time.'))
    add(panel('Pipeline latency · normal / degraded / error','timeseries',0,14,12,10,
        quantiles('vg_pipeline_duration_seconds','route="redactions"'),unit='s',description='Orchestrator only. Independent of HTTP latency; percentile differences are not overhead measurements.'))
    stage = panel('Stage latency trend · p95','timeseries',12,14,12,10,
        quantiles('vg_stage_duration_seconds','','stage',(0.95,)),unit='s',
        description='Detection stages run concurrently; do not sum their percentiles. The smallest histogram bucket is 5ms: fast stub stages can share interpolated p95 values of 4.75ms.')
    stage['options']['legend'].update(placement='right',width=230)
    add(stage)
    add(row('Fallback and model calls',24))
    add(stacked(panel('Degraded responses by cause and stage','timeseries',0,25,10,9,
        [(f'sum by (reason,stage) (rate({metric("vg_degraded_total")}[{W}]))','{{reason}} / {{stage}}')],unit='reqps')))
    calls = metric('vg_model_calls_total')
    good = metric('vg_model_calls_total','outcome="ok"')
    counts = f'sum by (prompt,outcome) (increase({calls}[$__range]))'
    ratio = f'sum by (prompt) (increase({good}[$__range])) / sum by (prompt) (increase({calls}[$__range]))'
    query = f'({counts}) or label_replace(({ratio}), "outcome", "parsed_success", "prompt", ".*")'
    models = panel('Model outcomes and parsed success · selected range','table',10,25,14,9,[(query,'')],decimals=1,
        description='One final outcome per invocation. Counts and parsed success ratio use the same selected time range, including queue timeouts, cancellation and internal errors. No calls gives an undefined ratio. Parsed success is not privacy accuracy.')
    matrix_table(models,'prompt','outcome',{'prompt\\outcome':'Prompt','ok':'OK','unavailable':'Unavailable','timeout':'Timeout','unparseable':'Unparseable','cancelled':'Cancelled','internal_error':'Internal error','parsed_success':'Parsed success'})
    health_column(models,'Parsed success','model_success','percentunit')
    for name,width in {'Prompt':95,'OK':55,'Unavailable':90,'Timeout':70,'Unparseable':90,'Cancelled':80,'Internal error':95,'Parsed success':100}.items():
        models['fieldConfig']['overrides'].append(dict(matcher=dict(id='byName',options=name),properties=[dict(id='custom.width',value=width)]))
    add(models)
    add(row('Sessions, observed components and versions',34))
    # A row per scope, with event columns so rejection coloring does not color normal deletions red.
    removed = f'sum by (event) (label_replace(increase({metric("vg_records_removed_total")}[$__range]), "event", "$1", "reason", "(.*)"))'
    rejected = f'label_replace(sum(increase({metric("vg_capacity_rejected_total")}[$__range])), "event", "capacity_rejected", "__name__", ".*")'
    zeros = ' or '.join(f'label_replace(0 * sum({metric("vg_records_capacity")}), "event", "{event}", "__name__", ".*")' for event in ('deleted','expired','capacity_rejected'))
    events = f'label_replace((({removed}) or ({rejected}) or {zeros}), "scope", "Selected range", "event", ".*")'
    lifecycle = panel('Session lifecycle · selected range','table',0,35,8,12,[(events,'')],decimals=1,
        description='Estimated counts for expiry, active deletion and explicit capacity rejection. Other HTTP 503s are excluded; only rejection counts receive health colors.')
    matrix_table(lifecycle,'scope','event',{'scope\\event':'Scope','deleted':'Deleted','expired':'Expired','capacity_rejected':'Capacity rejected'})
    lifecycle['transformations'][-1]['options']['excludeByName'] = {'scope\\event':True}
    lifecycle['fieldConfig']['defaults']['custom'] = dict(width=120)
    health_column(lifecycle,'Capacity rejected','capacity_rejections')
    add(lifecycle)
    components = panel('Components · last observed result','table',8,35,8,12,[(metric('vg_component_up'),'')],unit='none',
        description='Rules and Presidio report last actual execution, not continuous probes. Model endpoint reports reachability only.')
    table_fields(components,['component','Value'],{'component':'Component','Value':'Status'})
    components['fieldConfig']['overrides'] = [dict(matcher=dict(id='byName',options='Status'),properties=[
        dict(id='mappings',value=[dict(type='value',options={'-1':dict(text='UNKNOWN',color='gray'),'0':dict(text='DOWN',color='red'),'1':dict(text='UP',color='green')})]),
        dict(id='custom.cellOptions',value=dict(type='color-text')),
    ])]
    add(components)
    info = panel('Versions and runtime backends','table',16,35,8,12,[(metadata_query(),'')],unit='none',
        description='Version and backend values, one setting per row. Mixed components include stub prompts/parsers. Version metadata is not benchmark accuracy.')
    table_fields(info,['setting','setting_value'],{'setting':'Setting','setting_value':'Value'})
    info['options'].update(sortBy=[dict(displayName='Setting',desc=False)])
    add(info)
    for item in p:
        if item.get('type') == 'timeseries' and 'latency' in item['title'].lower():
            item['fieldConfig']['overrides'].append(dict(matcher=dict(id='byRegexp',options='/degraded/'),properties=[dict(id='custom.lineStyle',value=dict(fill='dash',dash=[8,4]))]))
    diagnostics = row('Diagnostics · model queues, session trends and API lifecycle',47)
    diagnostics['collapsed'] = True
    d = diagnostics['panels']
    d.append(panel('Model slot queue wait · p50/p95/p99','timeseries',0,48,12,8,
        quantiles('vg_model_queue_wait_seconds','','prompt'),unit='s',
        description='Includes successful and timed-out queue waits. Separate from execution latency. The smallest histogram bucket is 5ms.'))
    d.append(panel('Model execution and parsing · p50/p95/p99','timeseries',12,48,12,8,
        quantiles('vg_model_call_duration_seconds','','prompt'),unit='s',
        description='After acquiring the slot through generation and parsing. Queue-only timeouts have no execution sample. The smallest histogram bucket is 5ms.'))
    d.append(panel('In-flight redaction requests','timeseries',0,56,8,8,
        [(metric('vg_inflight_requests'),'In flight')],
        description='Requests admitted to pipeline processing; excludes rejected validation and capacity requests.'))
    d.append(panel('Session slots','timeseries',8,56,16,8,
        [(metric('vg_records_active'),'Active'),(metric('vg_records_reserved'),'Reserved'),(metric('vg_records_capacity'),'Capacity')]))
    api_labels = 'route=~"$diagnostic_route",method=~"$diagnostic_method"'
    d.append(stacked(panel('API lifecycle · selected route and method','timeseries',0,64,12,8,
        [(f'sum by (route,method,status) (rate({metric("vg_http_requests_total",api_labels)}[{W}]))','{{route}} {{method}} / {{status}}')],unit='reqps',
        description='Use diagnostic filters to inspect redaction, restore and delete independently. Overview metrics remain POST redaction only.')))
    d.append(panel('HTTP latency · selected operation and status','timeseries',12,64,12,8,
        [(f'histogram_quantile(0.95, sum by (le,route,method,status) (rate({metric("vg_http_duration_seconds_bucket",api_labels)}[{W}])))','p95 {{route}} {{method}} / {{status}}')],unit='s',
        description='Includes errors and restore/delete; separated by status so fast rejects do not hide slow successful operations.'))
    spans = panel('Rendered span decisions · selected range','bargauge',0,72,24,8,
        [(f'sum by (tier,action,mode) (increase({metric("vg_spans_total")}[$__range]))','{{tier}} / {{action}} / {{mode}}')],
        description='Rendered decisions, including attempts that later fail audit/serialization. Missed entities are absent; this cannot measure leak rate or accuracy.')
    spans['options'].update(orientation='horizontal')
    d.append(spans)
    for i,item in enumerate(d,100):
        item['id'] = i
    add(diagnostics)
    result = dashboard('Virtual Gold: Redaction Service','vg-redactor',p)
    result['templating']['list'].extend([
        dict(name='diagnostic_route',label='Diagnostic route',type='custom',query='/v3/redaction,/v3/restore',multi=True,includeAll=True,allValue='/v3/redaction|/v3/restore',current=dict(text='All',value='$__all')),
        dict(name='diagnostic_method',label='Diagnostic method',type='custom',query='POST,DELETE',multi=True,includeAll=True,allValue='POST|DELETE',current=dict(text='All',value='$__all')),
    ])
    return result


def external_dashboard():
    selector = 'job="vg-external",instance=~"$external_instance"'
    def m(name, labels=''):
        return name + '{' + selector + (','+labels if labels else '') + '}'
    p = []
    add = p.append
    add(row('VG08 host · externally reported routing and provider release',0))
    states = [dict(type='value',options={'0':dict(text='MISSING / INVALID',color='gray'),'1':dict(text='VALID SNAPSHOT',color='green')})]
    add(panel('Exporter scrape','stat',0,1,4,4,[(f'up{{{selector}}}','Exporter')],unit='none',
        mappings=[dict(type='value',options={'0':dict(text='DOWN',color='red'),'1':dict(text='UP',color='green')})]))
    add(panel('VG08 aggregate source','stat',4,1,4,4,[(m('vg_external_source_available','source="host"'),'Host source')],unit='none',mappings=states,
        description='No VG08 producer is bundled. Routing and release are reported by the actual host through the documented snapshot contract.'))
    add(panel('Host snapshot age','stat',8,1,4,4,[(f'time() - {m("vg_external_source_updated_timestamp_seconds", HOST_SOURCE)}', 'Age')],unit='s',
        description='Age since the host published the aggregate. An old valid file can still be stale; verify this before interpreting zero rates.'))
    add(panel('Routing · selected range','bargauge',12,1,6,7,[(f'sum by (route) (increase({m("vg_host_routing_total")}[$__range]))','{{route}}')],
        description='Host decisions: cloud, local, blocked. A cloud route decision does not prove provider dispatch.'))
    add(panel('Provider release · selected range','bargauge',18,1,6,7,[(f'sum by (outcome) (increase({m("vg_host_release_total")}[$__range]))','{{outcome}}')],
        description='Actual host dispatch outcomes: sent, blocked, failed. Never inferred from service HTTP 200 or degraded flags.'))
    add(row('Offline labelled evaluation · latest imported run only',8))
    add(panel('Evaluation report source','stat',0,9,4,4,[(m('vg_external_source_available','source="evaluation"'),'Evaluation source')],unit='none',mappings=states))
    add(panel('Evaluated emails','stat',4,9,4,4,[(m('vg_evaluation_emails'),'Emails')]))
    add(panel('Report age','stat',8,9,4,4,[(f'time() - {m("vg_external_source_updated_timestamp_seconds", EVALUATION_SOURCE)}', 'Age')],unit='s'))
    info = panel('Dataset, split and version provenance','table',12,9,12,7,[(m('vg_evaluation_info'),'')])
    info['transformations'] = [dict(id='filterFieldsByName',options=dict(include=dict(names=['run','dataset','split','model','policy','prompt_detection','prompt_assessment','calibration'])))]
    add(info)
    add(panel('Required span leakage by tier · includes FACT','bargauge',0,16,12,8,[(m('vg_evaluation_span_leak_ratio'),'{{tier}}')],unit='percentunit',min=0,max=1,
        description='Missed required labelled spans / required spans of that tier. Entity coverage threshold 95%; FACT threshold 50%. No required spans means no value. This is a benchmark proxy, not observed cloud leakage.'))
    add(panel('Emails leaking entities by tier · repository scorer','bargauge',12,16,12,8,[(m('vg_evaluation_email_leak_ratio'),'{{tier}}')],unit='percentunit',min=0,max=1,
        description='Emails missing at least one required entity span of a tier / all emails. Existing scorer excludes FACT, which has a separate recall metric. Distinct denominator from span leakage.'))
    add(panel('Entity recall','stat',0,24,6,5,[(m('vg_evaluation_recall'),'Recall')],unit='percentunit',min=0,max=1))
    add(panel('FACT recall','stat',6,24,6,5,[(m('vg_evaluation_fact_recall'),'FACT recall')],unit='percentunit',min=0,max=1))
    add(panel('Public labelled spans touched','stat',12,24,6,5,[(m('vg_evaluation_optional_masked'),'Optional masked')],unit='percentunit',min=0,max=1,
        description='Fraction of retain-labelled spans with any predicted redaction overlap. Not a whole-document character over-redaction rate.'))
    add(panel('Extra predicted masks','stat',18,24,6,5,[(m('vg_evaluation_extra_masks'),'Extra masks')],
        description='Predicted redaction spans overlapping no labelled span, as defined by the repository scorer.'))
    add(row('Calibration · independent candidate labels required',29))
    add(panel('Calibration sample count','stat',0,30,6,5,[(m('vg_evaluation_calibration_samples'),'Candidates')],
        description='Optional independently labelled held-out candidates. Empty until calibration samples are explicitly supplied.'))
    add(panel('Expected calibration error · raw vs calibrated','bargauge',6,30,6,8,[(m('vg_evaluation_ece'),'{{kind}}')],unit='percentunit',min=0,max=1,
        description='Ten equal-width bins; compare both scores on the same held-out candidates. Exclude deterministic policy overrides.'))
    add(panel('Reliability bins · mean predicted private probability','bargauge',12,30,6,8,[(m('vg_evaluation_calibration_bin_mean_score'),'{{kind}} bin {{bin}}')],unit='percentunit',min=0,max=1))
    add(panel('Reliability bins · observed private fraction','bargauge',18,30,6,8,[(m('vg_evaluation_calibration_bin_private_fraction'),'{{kind}} bin {{bin}}')],unit='percentunit',min=0,max=1,
        description='Bin 0: [0,0.1), … bin 9: [0.9,1]. Empty bins are omitted, not filled with zero.'))
    result = dashboard('Virtual Gold: Release and Offline Evaluation','vg-release-evaluation',p)
    result['templating']['list'] = [dict(name='external_instance',label='Exporter instance',type='query',datasource=DS,
        query='label_values(up{job="vg-external"}, instance)',refresh=1,multi=False,includeAll=False)]
    result['links'] = [dict(title='Service overview',type='link',url='/d/vg-redactor',keepTime=True)]
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    service = service_dashboard()
    service['links'] = [dict(title='Release and offline evaluation',type='link',url='/d/vg-release-evaluation',keepTime=True)]
    (ROOT/'vg-redactor.json').write_text(json.dumps(service,indent=2)+'\n')
    (ROOT/'vg-release-evaluation.json').write_text(json.dumps(external_dashboard(),indent=2)+'\n')


if __name__ == '__main__':
    main()
