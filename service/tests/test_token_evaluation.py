"""The model experiment must not mistake omitted entities for successful preservation."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'evaluate_tokens', Path(__file__).parents[1] / 'scripts' / 'evaluate_tokens.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_preservation_distinguishes_omission_mutation_and_extra_mentions():
    source = '[VG:a] [VG:b] [VG:a]'
    omitted = module.preservation(source, '[VG:a]')
    assert omitted['distinct_preserved'] == 1 and not omitted['all_distinct_preserved']
    changed = module.preservation(source, '[VG:a] [VG:c]')
    assert changed['unexpected_tokens'] == 1 and not changed['all_distinct_preserved']
    extra = module.preservation(source, source + ' [VG:a]')
    assert extra['all_distinct_preserved'] and extra['unexpected_tokens'] == 0
    assert extra['extra_occurrences'] == 1 and not extra['exact_copy']
