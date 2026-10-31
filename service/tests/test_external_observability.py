"""P2 contracts use synthetic labels only; never evaluate the reserved test dataset here."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from vg_redactor.obs.evaluation import calibration, load_records, report
from vg_redactor.obs.external import SnapshotCollector, validate_evaluation, validate_host

META = dict(run='fixture-1', dataset='synthetic-v1', split='dev', model='stub', policy='0.1',
            prompt_detection='stub-0', prompt_assessment='stub-0', calibration='none')


def fixtures():
    gold = {'E1': dict(id='E1', text='Alice secret 100', domain='synthetic', spans=[
        dict(start=0,end=5,text='Alice',type='PERSON',service_type='PERSON',tier='medium',ground_truth='redact'),
        dict(start=6,end=12,text='secret',type='FACT',service_type='BUSINESS_CONFIDENTIAL',tier='high',ground_truth='redact'),
        dict(start=13,end=16,text='100',type='AMOUNT',tier='low',ground_truth='retain')])}
    pred = {'E1':dict(id='E1', spans=[dict(start=0,end=5),dict(start=6,end=9),dict(start=13,end=16)])}
    return gold,pred


def render(collector):
    registry = CollectorRegistry()
    registry.register(collector)
    return generate_latest(registry).decode()


def test_span_and_email_leak_denominators_and_fact_threshold():
    gold,pred = fixtures()
    result = report(gold,pred,META)
    validate_evaluation(result)
    assert result['span_counts_by_tier']['high'] == dict(required=1,leaked=0)
    assert result['span_counts_by_tier']['medium'] == dict(required=1,leaked=0)
    assert result['fact_recall'] == 1 and result['optional_masked'] == 1
    pred['E1']['spans'][0]['end'] = 2
    pred['E1']['spans'][1]['end'] = 8
    result = report(gold,pred,META)
    assert result['span_counts_by_tier']['medium']['leaked'] == 1
    assert result['span_counts_by_tier']['high']['leaked'] == 1
    # Existing scorer excludes FACT in email leak rates, intentionally labelled separately.
    assert result['email_leak_rate_by_tier']['high'] == 0
    assert result['email_leak_rate_by_tier']['medium'] == 1
    assert result['fact_recall'] == 0
    assert 'Alice' not in json.dumps(result) and 'E1' not in json.dumps(result)


def test_calibration_ece_uses_same_samples_and_omits_empty_bins():
    c = calibration([dict(raw=.9,calibrated=.1,is_private=False),
                     dict(raw=.1,calibrated=.8,is_private=True)])
    assert c['raw_ece'] == pytest.approx(.9)
    assert c['calibrated_ece'] == pytest.approx(.15)
    assert c['samples'] == 2 and len(c['bins']) == 4
    assert calibration([]) is None
    with pytest.raises(ValueError):
        calibration([dict(raw=float('nan'),calibrated=.2,is_private=True)])
    with pytest.raises(ValueError):
        calibration([dict(raw=.9,calibrated=.2,is_private=1)])


def test_missing_predictions_and_invalid_offsets_fail_closed():
    gold,pred = fixtures()
    with pytest.raises(ValueError):
        report(gold,{},META)
    pred['E1']['spans'][0]['end'] = 9999
    with pytest.raises(ValueError):
        report(gold,pred,META)


def test_exporter_only_exports_valid_aggregate_snapshots(tmp_path):
    gold,pred = fixtures()
    evaluation = report(gold,pred,META,[dict(raw=.8,calibrated=.7,is_private=True)])
    host = dict(schema_version=1,updated_at=1000,routing=dict(cloud=5,local=2,blocked=1),
                release=dict(sent=4,blocked=1,failed=1))
    hp,ep = tmp_path/'host.json',tmp_path/'evaluation.json'
    hp.write_text(json.dumps(host)); ep.write_text(json.dumps(evaluation))
    collector = SnapshotCollector(hp,ep)
    names = [m.name for m in collector.collect()]
    assert len(names) == len(set(names)), 'Each metric family must be emitted only once'
    payload = render(collector)
    assert 'vg_host_release_total{outcome="sent"} 4.0' in payload
    assert 'vg_evaluation_span_leak_ratio{tier="medium"} 0.0' in payload
    assert 'vg_evaluation_span_leak_ratio{tier="public"}' not in payload
    assert 'vg_evaluation_ece{kind="raw"}' in payload
    assert 'Alice' not in payload and str(tmp_path) not in payload
    # Repeated scrapes read cumulative totals, never increment again on re-reading a file.
    assert render(collector) == payload
    host['release']['sent'] = 6
    hp.write_text(json.dumps(host))
    assert 'vg_host_release_total{outcome="sent"} 6.0' in render(collector)
    # An invalid replacement omits data rather than displaying stale successes or fake zeroes.
    hp.write_text('{')
    ep.unlink()
    payload = render(collector)
    assert 'vg_external_source_available{source="host"} 0.0' in payload
    assert 'vg_host_release_total' not in payload
    assert 'vg_evaluation_recall' not in payload


def test_schemas_reject_raw_fields_and_inconsistent_calibration():
    host = dict(schema_version=1,updated_at=1000,routing=dict(cloud=0,local=0,blocked=0),
                release=dict(sent=0,blocked=0,failed=0),text='private')
    with pytest.raises(ValueError):
        validate_host(host)
    gold,pred = fixtures()
    data = report(gold,pred,META,[dict(raw=.8,calibrated=.7,is_private=True)])
    bad = copy.deepcopy(data)
    bad['calibration']['samples'] = 100
    with pytest.raises(ValueError):
        validate_evaluation(bad)
    bad = copy.deepcopy(data)
    bad['span_counts_by_tier']['medium']['leaked'] = 99
    with pytest.raises(ValueError):
        validate_evaluation(bad)


def test_offline_cli_writes_sanitized_report_atomically(tmp_path):
    gold,pred = fixtures()
    gp,pp,mp,out = (tmp_path/name for name in ('gold.jsonl','pred.jsonl','metadata.json','report.json'))
    gp.write_text(json.dumps(gold['E1'])+'\n')
    pp.write_text(json.dumps(pred['E1'])+'\n')
    mp.write_text(json.dumps(META))
    subprocess.run([sys.executable,'-m','vg_redactor.obs.evaluation','--gold',str(gp),'--pred',str(pp),
                    '--metadata',str(mp),'--out',str(out)],cwd=Path(__file__).resolve().parents[1],check=True)
    validate_evaluation(json.loads(out.read_text()))
    assert not out.with_suffix('.json.tmp').exists()
    assert 'Alice' not in out.read_text()
    gp.write_text(gp.read_text()*2)
    with pytest.raises(ValueError,match='Duplicate'):
        load_records(gp)


def test_malformed_source_only_disables_that_source(tmp_path):
    gold,pred = fixtures()
    host = dict(schema_version=1,updated_at=1000,routing=dict(cloud=1,local=0,blocked=0),
                release=dict(sent=1,blocked=0,failed=0))
    hp,ep = tmp_path/'host.json',tmp_path/'evaluation.json'
    hp.write_text(json.dumps(host))
    for payload in ('{"schema_version":1,"updated_at":' + '9'*400 + '}', '['*50000 + ']'*50000, 'x'*1_000_001):
        ep.write_text(payload)
        out = render(SnapshotCollector(hp,ep))
        assert 'vg_external_source_available{source="evaluation"} 0.0' in out
        assert 'vg_external_source_available{source="host"} 1.0' in out
        assert 'vg_host_release_total{outcome="sent"} 1.0' in out


def test_reserved_test_set_and_mismatched_dev_split_are_rejected():
    split = json.loads((Path(__file__).resolve().parents[2]/'data/baseline/split_v1.1.json').read_text())
    meta = dict(META, dataset='baseline-v1.1')

    def synthetic(ids):
        return ({i: dict(id=i,text='Alice',spans=[]) for i in ids}, {i: dict(id=i,spans=[]) for i in ids})

    gold,pred = synthetic(split['test'])
    with pytest.raises(ValueError,match='Reserved test set'):
        report(gold,pred,meta)
    gold,pred = synthetic(split['dev'][:5])
    with pytest.raises(ValueError,match='full dev set'):
        report(gold,pred,meta)
    gold,pred = synthetic(split['dev'])
    with pytest.raises(ValueError,match='full dev set'):
        report(gold,pred,dict(meta,split='validation'))
