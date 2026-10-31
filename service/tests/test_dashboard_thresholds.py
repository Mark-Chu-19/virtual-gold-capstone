"""Check operational color semantics in the provisioned artifact, not just the builder."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'dashboards'


def panels(filename):
    doc = json.loads((ROOT/'grafana/dashboards'/filename).read_text())
    return {p['title']:p for row in doc['panels'] for p in ([row] + row.get('panels',[])) if p['type'] != 'row'}


def field_config(panel, name=None):
    fields = dict(panel['fieldConfig']['defaults'])
    for override in panel['fieldConfig']['overrides']:
        if override['matcher'] == dict(id='byName',options=name):
            fields.update({p['id']:p['value'] for p in override['properties']})
    return fields


def color(panel, value, field=None):
    fields = field_config(panel,field)
    if fields['color']['mode'] == 'fixed':
        return fields['color']['fixedColor']
    result = None
    for step in fields['thresholds']['steps']:
        if step['value'] is None or value >= step['value']:
            result = step['color']
    return result


@pytest.mark.parametrize('title,value,expected', [
    ('HTTP availability',0,'red'), ('HTTP availability',.99,'orange'),
    ('HTTP availability',.999,'green'), ('HTTP availability',1,'green'),
    ('Session capacity used',.79,'green'), ('Session capacity used',.8,'orange'),
    ('Session capacity used',.9,'red'), ('Session capacity used',1,'red'),
    ('Degraded share of successful redactions',0,'green'),
    ('Degraded share of successful redactions',.01,'orange'),
    ('Degraded share of successful redactions',.05,'red'),
    ('Degraded share of successful redactions',1,'red'),
    ('Model calls with valid parsed output',.94,'red'),
    ('Model calls with valid parsed output',.95,'orange'),
    ('Model calls with valid parsed output',.99,'green'),
    ('Capacity rejections · selected range',1,'red'),
])
def test_health_color_boundaries(title,value,expected):
    field = None
    if title == 'Model calls with valid parsed output':
        title,field = 'Model outcomes and parsed success · selected range','Parsed success'
    elif title == 'Capacity rejections · selected range':
        title,field = 'Session lifecycle · selected range','Capacity rejected'
    assert color(panels('vg-redactor.json')[title],value,field) == expected


def test_unknown_data_is_gray_and_benchmark_metrics_are_neutral():
    for p in panels('vg-redactor.json').values():
        for name in [None]+[o['matcher']['options'] for o in p['fieldConfig']['overrides'] if o['matcher']['id']=='byName']:
            fields = field_config(p,name)
            if fields['color']['mode'] == 'thresholds':
                missing = {m['options']['match']:m['options']['result']['color']
                           for m in fields['mappings'] if m['type']=='special'}
                assert missing == dict(null='gray',nan='gray')
    for title in ('Required span leakage by tier · includes FACT','Entity recall',
                  'Expected calibration error · raw vs calibrated'):
        p = panels('vg-release-evaluation.json')[title]
        assert color(p,0) == color(p,1) == 'blue'


def test_generated_dashboards_match_builder_and_profiles():
    spec = importlib.util.spec_from_file_location('vg_dashboards',ROOT/'build_dashboard.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    service = builder.service_dashboard()
    service['links'] = [dict(title='Release and offline evaluation',type='link',url='/d/vg-release-evaluation',keepTime=True)]
    for filename,expected in [('vg-redactor.json',service),('vg-release-evaluation.json',builder.external_dashboard())]:
        assert json.loads((ROOT/'grafana/dashboards'/filename).read_text()) == expected


def test_compact_dashboard_retains_distinct_diagnostics_and_single_stage_view():
    doc = json.loads((ROOT/'grafana/dashboards/vg-redactor.json').read_text())
    all_panels = panels('vg-redactor.json')
    assert len(all_panels) == 22
    diagnostics = doc['panels'][-1]
    assert diagnostics['collapsed'] and len(diagnostics['panels']) == 7
    assert 'Session slots' in {p['title'] for p in diagnostics['panels']}
    assert all(name in all_panels for name in (
        'HTTP end-to-end latency · successful redactions','Pipeline latency · normal / degraded / error',
        'Model slot queue wait · p50/p95/p99','Model execution and parsing · p50/p95/p99'))
    expressions = [q['expr'] for p in all_panels.values() for q in p.get('targets',[])]
    assert len(expressions) == len(set(expressions)), 'Do not duplicate complete queries across panels'
    assert sum('vg_stage_duration_seconds_bucket' in q for q in expressions) == 1


def test_degraded_card_includes_trend_without_stale_last_value():
    p = panels('vg-redactor.json')['Degraded share of successful redactions']
    assert p['targets'][0]['range'] and not p['targets'][0]['instant']
    assert p['options']['graphMode'] == 'area'
    assert p['options']['reduceOptions']['calcs'] == ['last']


def test_tables_hide_technical_fields_and_use_consistent_count_windows():
    all_panels = panels('vg-redactor.json')
    versions = all_panels['Versions and runtime backends']
    assert len(versions['targets']) == 1
    assert versions['transformations'][0]['options']['include']['names'] == ['setting','setting_value']
    components = all_panels['Components · last observed result']
    assert components['transformations'][0]['options']['include']['names'] == ['component','Value']
    model = all_panels['Model outcomes and parsed success · selected range']
    assert len(model['targets']) == 1
    assert '$__range' in model['targets'][0]['expr'] and '$__rate_interval' not in model['targets'][0]['expr']
    assert model['transformations'][1]['id'] == 'groupingToMatrix'
    lifecycle = all_panels['Session lifecycle · selected range']
    assert color(lifecycle,100,'Deleted') == 'blue'
    assert color(lifecycle,1,'Capacity rejected') == 'red'
