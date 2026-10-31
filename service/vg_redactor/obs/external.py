"""Optional local exporter for VG08 aggregate snapshots and offline evaluation reports.

Missing or invalid sources expose availability=0 and omit source metrics (no invented zeroes).
No file path, input content, arbitrary JSON key, or exception message is exported as a label.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import threading
from pathlib import Path

from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from ..contracts.types import TIERS
MAX_SOURCE_BYTES = 1_000_000
METADATA = ('run', 'dataset', 'split', 'model', 'policy', 'prompt_detection', 'prompt_assessment', 'calibration')


def number(value, *, integer=False, probability=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid nonnegative number')
    if integer and type(value) is not int:
        raise ValueError('Expected integer')
    if probability and value > 1:
        raise ValueError('Expected probability')
    return value


def keys(data, expected):
    if not isinstance(data, dict) or set(data) != set(expected):
        raise ValueError('Unexpected schema fields')


def header(data):
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Unsupported schema version')
    number(data['updated_at'])


def validate_host(data):
    keys(data, ('schema_version','updated_at','routing','release'))
    header(data)
    for field, choices in [('routing',('cloud','local','blocked')),('release',('sent','blocked','failed'))]:
        keys(data[field], choices)
        for value in data[field].values():
            number(value, integer=True)
    return data


def validate_evaluation(data):
    keys(data, ('schema_version','updated_at','metadata','emails','span_counts_by_tier',
                'email_leak_rate_by_tier','recall','fact_recall','extra_masks','optional_masked','calibration'))
    header(data)
    keys(data['metadata'], METADATA)
    for value in data['metadata'].values():
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:/+\-]{1,100}',value):
            raise ValueError('Metadata requires short version identifiers')
    if data['metadata']['split'] not in ('dev','test','validation'):
        raise ValueError('Unknown dataset split')
    number(data['emails'],integer=True)
    if not data['emails']:
        raise ValueError('Empty evaluation')
    number(data['extra_masks'],integer=True)
    for field in ('recall','fact_recall','optional_masked'):
        if data[field] is not None:
            number(data[field],probability=True)
    keys(data['span_counts_by_tier'],TIERS)
    keys(data['email_leak_rate_by_tier'],TIERS)
    for tier, counts in data['span_counts_by_tier'].items():
        keys(counts, ('required','leaked'))
        for value in counts.values():
            number(value,integer=True)
        if counts['leaked'] > counts['required']:
            raise ValueError('Leaked count exceeds required count')
        if data['email_leak_rate_by_tier'][tier] is not None:
            number(data['email_leak_rate_by_tier'][tier],probability=True)
    c = data['calibration']
    if c is not None:
        keys(c, ('samples','raw_ece','calibrated_ece','bins'))
        number(c['samples'],integer=True)
        if c['samples'] == 0 or not isinstance(c['bins'],list):
            raise ValueError('Invalid calibration sample count')
        number(c['raw_ece'],probability=True)
        number(c['calibrated_ece'],probability=True)
        totals, seen = {'raw':0,'calibrated':0}, set()
        for b in c['bins']:
            keys(b, ('kind','bin','count','mean_score','private_fraction'))
            key = (b['kind'],b['bin'])
            if b['kind'] not in totals or b['bin'] not in tuple(map(str,range(10))) or key in seen:
                raise ValueError('Invalid calibration bin')
            seen.add(key)
            number(b['count'],integer=True)
            if not b['count']:
                raise ValueError('Empty calibration bin')
            number(b['mean_score'],probability=True)
            number(b['private_fraction'],probability=True)
            totals[b['kind']] += b['count']
        if any(n != c['samples'] for n in totals.values()):
            raise ValueError('Calibration bins do not match sample count')
    return data


def gauge(name, help_, value, labels=(), values=()):
    m = GaugeMetricFamily(name,help_,labels=list(labels))
    m.add_metric(list(values),value)
    return m


class SnapshotCollector:
    def __init__(self, host_snapshot=None, evaluation_report=None):
        self.paths = {'host':host_snapshot,'evaluation':evaluation_report}

    def collect(self):
        loaded = {}
        for source,path in self.paths.items():
            data = None
            if path:
                try:
                    if Path(path).stat().st_size > MAX_SOURCE_BYTES:
                        raise ValueError('Source file too large')
                    data = json.loads(Path(path).read_text())
                    (validate_host if source == 'host' else validate_evaluation)(data)
                except Exception:  # noqa: BLE001  untrusted file: any failure marks only this source unavailable
                    data = None
            loaded[source] = data
        available = GaugeMetricFamily('vg_external_source_available','Source snapshot is present and valid',labels=['source'])
        timestamps = GaugeMetricFamily('vg_external_source_updated_timestamp_seconds','Producer timestamp; inspect age before using results',labels=['source'])
        for source,data in loaded.items():
            available.add_metric([source],int(data is not None))
            if data is not None:
                timestamps.add_metric([source],data['updated_at'])
        yield available
        yield timestamps
        host = loaded['host']
        if host is not None:
            for field,label in [('routing','route'),('release','outcome')]:
                m = CounterMetricFamily('vg_host_'+field+'_total','VG08 cumulative '+field+' events (host reported)',labels=[label])
                for choice,count in host[field].items():
                    m.add_metric([choice],count)
                yield m
        data = loaded['evaluation']
        if data is None:
            return
        yield gauge('vg_evaluation_info','Latest evaluation run metadata',1,METADATA,tuple(data['metadata'][k] for k in METADATA))
        yield gauge('vg_evaluation_emails','Emails in labelled evaluation',data['emails'])
        for field in ('required','leaked'):
            m = GaugeMetricFamily('vg_evaluation_spans_'+field,'Labelled '+field+' spans including FACT',labels=['tier'])
            for tier,c in data['span_counts_by_tier'].items():
                m.add_metric([tier],c[field])
            yield m
        span_ratio = GaugeMetricFamily('vg_evaluation_span_leak_ratio','Missed required spans / required spans including FACT',labels=['tier'])
        email_ratio = GaugeMetricFamily('vg_evaluation_email_leak_ratio','Repository scorer: fraction of emails leaking entities, excluding FACT',labels=['tier'])
        for tier,c in data['span_counts_by_tier'].items():
            if c['required']:
                span_ratio.add_metric([tier],c['leaked']/c['required'])
            ratio = data['email_leak_rate_by_tier'][tier]
            if ratio is not None:
                email_ratio.add_metric([tier],ratio)
        yield span_ratio
        yield email_ratio
        for field in ('recall','fact_recall','extra_masks','optional_masked'):
            if data[field] is not None:
                yield gauge('vg_evaluation_'+field,'Repository scorer '+field,data[field])
        c = data['calibration']
        if c:
            yield gauge('vg_evaluation_calibration_samples','Held-out candidate labels used for calibration evaluation',c['samples'])
            ece = GaugeMetricFamily('vg_evaluation_ece','Ten-bin expected calibration error',labels=['kind'])
            for kind in ('raw','calibrated'):
                ece.add_metric([kind],c[kind+'_ece'])
            yield ece
            for field in ('count','mean_score','private_fraction'):
                m = GaugeMetricFamily('vg_evaluation_calibration_bin_'+field,'Reliability bin '+field,labels=['kind','bin'])
                for b in c['bins']:
                    m.add_metric([b['kind'],b['bin']],b[field])
                yield m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-snapshot',type=Path)
    parser.add_argument('--evaluation-report',type=Path)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=9101)
    args = parser.parse_args()
    registry = CollectorRegistry()
    registry.register(SnapshotCollector(args.host_snapshot,args.evaluation_report))
    start_http_server(args.port,addr=args.host,registry=registry)
    threading.Event().wait()


if __name__ == '__main__':
    main()
