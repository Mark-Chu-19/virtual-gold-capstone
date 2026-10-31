"""Check operational color semantics in the provisioned artifact, not just the builder."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / 'dashboards'


def panels(filename):
    doc = json.loads((ROOT/'grafana/dashboards'/filename).read_text())
    return {p['title']:p for row in doc['panels'] for p in ([row] + row.get('panels',[])) if p['type'] != 'row'}


def color(panel, value):
    fields = panel['fieldConfig']['defaults']
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
    assert color(panels('vg-redactor.json')[title],value) == expected


def test_unknown_data_is_gray_and_benchmark_metrics_are_neutral():
    for p in panels('vg-redactor.json').values():
        fields = p['fieldConfig']['defaults']
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
