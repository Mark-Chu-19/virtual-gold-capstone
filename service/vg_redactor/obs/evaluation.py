"""Offline labelled evaluation; never run against the reserved test set implicitly."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import time
from pathlib import Path

from ..contracts.fields import iter_fields
from ..contracts.types import EmailIn

TIERS = ('high', 'medium', 'low', 'public')


def scorer():
    path = Path(__file__).resolve().parents[3] / 'data/baseline/score.py'
    spec = importlib.util.spec_from_file_location('vg_baseline_score', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calibration(samples):
    """Ten equal-width bins, same candidates for raw and calibrated ECE."""
    bins = {kind: [[0, 0., 0] for _ in range(10)] for kind in ('raw', 'calibrated')}
    for sample in samples:
        if set(sample) != {'raw', 'calibrated', 'is_private'} or type(sample['is_private']) is not bool:
            raise ValueError('Calibration sample requires raw, calibrated, is_private only')
        for kind in bins:
            score = sample[kind]
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Calibration score must be a finite probability')
            b = bins[kind][min(int(score * 10), 9)]
            b[0] += 1
            b[1] += score
            b[2] += int(sample['is_private'])
    count = sum(b[0] for b in bins['raw'])
    if not count:
        return None
    result = dict(samples=count, bins=[])
    for kind, groups in bins.items():
        result[kind + '_ece'] = sum(abs(total_score - private) for n,total_score,private in groups) / count
        for i,(n,total_score,private) in enumerate(groups):
            if n:
                result['bins'].append(dict(kind=kind, bin=str(i), count=n,
                                           mean_score=total_score/n, private_fraction=private/n))
    return result


def report(gold, predictions, metadata, samples=None):
    """Use the repository's scorer, plus explicitly named span-level leakage including FACT."""
    # Missing predictions are not silently treated as unmasked, successful cloud releases.
    if not gold or set(gold) != set(predictions):
        raise ValueError('Gold and predictions must contain the same nonempty set of email IDs')
    engine = scorer()
    counts = {tier: dict(required=0, leaked=0) for tier in TIERS}
    for eid, record in gold.items():
        spans = predictions[eid].get('spans')
        if not isinstance(spans, list):
            raise ValueError('Every prediction requires an explicit spans list')
        fields = iter_fields(record['request']['purpose'], EmailIn.model_validate(record['request']['email'])) if 'request' in record else {}
        for span in spans:
            if type(span.get('start')) is not int or type(span.get('end')) is not int or span['start'] < 0 or span['end'] <= span['start']:
                raise ValueError('Invalid prediction offsets')
            if span.get('action', 'redact') not in ('redact', 'retain'):
                raise ValueError('Invalid prediction action')
            if 'field' in span:
                if span['field'] not in fields or span['end'] > len(fields[span['field']]):
                    raise ValueError('Prediction outside request field')
            elif span['end'] > len(record['text']):
                raise ValueError('Prediction outside email text')
        covered = set()
        for span in engine.to_text_spans(record, spans):
            covered.update(range(span['start'], span['end']))
        for span in record['spans']:
            if span.get('ground_truth') not in ('redact', 'retain'):
                raise ValueError('Reviewed ground_truth labels are required')
            if span['ground_truth'] != 'redact':
                continue
            tier = span['tier']
            if tier not in counts:
                raise ValueError('Unknown tier')
            positions = engine.alnum_positions(record['text'],span['start'],span['end']) or list(range(span['start'],span['end']))
            fraction = len(covered.intersection(positions)) / len(positions)
            threshold = 0.5 if span['type'] == 'FACT' else 0.95
            counts[tier]['required'] += 1
            counts[tier]['leaked'] += int(fraction < threshold)
    scored = engine.score(gold, predictions, 'ground_truth')
    # Deliberately omit misses, raw text, IDs and per-email details from exported artifacts.
    result = dict(schema_version=1, updated_at=time.time(), metadata=metadata,
                  emails=scored['emails'], span_counts_by_tier=counts,
                  email_leak_rate_by_tier=scored['leak_rate_by_tier'],
                  recall=scored['recall'], fact_recall=scored['fact_recall'],
                  extra_masks=scored['extra_masks'], optional_masked=scored['optional_masked'],
                  calibration=calibration(samples) if samples is not None else None)
    return result


def load_records(path):
    result = {}
    with Path(path).open(encoding='utf8') as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            if record['id'] in result:
                raise ValueError('Duplicate email ID')
            result[record['id']] = record
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', required=True)
    parser.add_argument('--pred', required=True)
    parser.add_argument('--metadata', required=True, help='JSON version metadata, see dashboards/README.md')
    parser.add_argument('--calibration-samples', help='JSONL of raw/calibrated/is_private on held-out candidates')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    metadata = json.loads(Path(args.metadata).read_text())
    samples = None
    if args.calibration_samples:
        samples = [json.loads(line) for line in Path(args.calibration_samples).read_text().splitlines() if line.strip()]
    result = report(load_records(args.gold), load_records(args.pred), metadata, samples)
    from .external import validate_evaluation
    validate_evaluation(result)
    target = Path(args.out)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    temporary.replace(target)


if __name__ == '__main__':
    main()
