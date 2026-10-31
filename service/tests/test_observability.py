"""Metric semantics: final outcomes, measured boundaries, and capacity accounting."""
import asyncio
import time

import pytest

from conftest import EMAIL_REQ, post_json
from vg_redactor.obs.metrics import MODEL_OUTCOMES


def value(app, name, **labels):
    return app.state.metrics.registry.get_sample_value(name, labels) or 0


@pytest.mark.parametrize('prompt', ['detection', 'assessment'])
@pytest.mark.parametrize('fault,outcome', [('ok', 'ok'), ('garbage', 'unparseable'),
                                          ('down', 'unavailable'), ('timeout', 'timeout')])
async def test_one_model_final_outcome(client, app, model, prompt, fault, outcome):
    model.mode[prompt] = fault
    assert (await post_json(client, '/v3/redaction', EMAIL_REQ)).status_code == 200
    counts = {o: value(app, 'vg_model_calls_total', prompt=prompt, outcome=o)
              for o in MODEL_OUTCOMES}
    assert counts[outcome] == 1 and sum(counts.values()) == 1


@pytest.mark.parametrize('prompt', ['detection', 'assessment'])
async def test_internal_parser_error_is_500_and_releases_model_slot(client, app, components, prompt):
    name = 'parse_' + prompt
    original = getattr(components, name)

    def broken_parser(*args):
        raise RuntimeError('internal parser bug')

    setattr(components, name, broken_parser)
    response = await post_json(client, '/v3/redaction', EMAIL_REQ)
    assert response.status_code == 500
    assert value(app, 'vg_model_calls_total', prompt=prompt, outcome='internal_error') == 1
    assert sum(value(app, 'vg_model_calls_total', prompt=prompt, outcome=o) for o in MODEL_OUTCOMES) == 1
    assert value(app, 'vg_model_calls_total', prompt=prompt, outcome='unavailable') == 0
    assert value(app, 'vg_redaction_responses_total', mode='degraded') == 0
    assert app.state.records.stats()['reserved'] == app.state.records.stats()['active'] == 0
    # A second real request verifies the model semaphore wasn't leaked on the error path.
    setattr(components, name, original)
    assert (await post_json(client, '/v3/redaction', EMAIL_REQ)).status_code == 200


async def test_unexpected_adapter_error_still_degrades_as_unavailable(client, app, model):
    async def broken_adapter(*args, **kwargs):
        raise RuntimeError('adapter failed')

    model.generate = broken_adapter
    response = await post_json(client, '/v3/redaction', EMAIL_REQ)
    assert response.status_code == 200 and response.json()['degraded']
    assert value(app, 'vg_model_calls_total', prompt='detection', outcome='unavailable') == 1
    assert value(app, 'vg_model_calls_total', prompt='detection', outcome='internal_error') == 0


async def test_failed_response_after_fallback_is_not_successfully_degraded(client, app, model, monkeypatch):
    import vg_redactor.api.app as api
    model.mode['detection'] = 'down'

    def broken_response(result):
        raise RuntimeError('serialization failed')

    monkeypatch.setattr(api, '_json_response', broken_response)
    assert (await post_json(client, '/v3/redaction', EMAIL_REQ)).status_code == 500
    assert value(app, 'vg_redaction_responses_total', mode='error') == 1
    assert value(app, 'vg_redaction_responses_total', mode='degraded') == 0
    assert sum(s.value for f in app.state.metrics.registry.collect() for s in f.samples
               if s.name == 'vg_degraded_total') == 0
    assert app.state.records.stats()['active'] == 0


async def test_http_latency_includes_serialization_and_pipeline_does_not(client, app, monkeypatch):
    import vg_redactor.api.app as api
    original = api._json_response

    def slow_response(result):
        time.sleep(0.04)
        return original(result)

    monkeypatch.setattr(api, '_json_response', slow_response)
    assert (await post_json(client, '/v3/redaction', EMAIL_REQ)).status_code == 200
    http = value(app, 'vg_http_duration_seconds_sum', route='/v3/redaction', method='POST', status='200', mode='normal')
    pipeline = value(app, 'vg_pipeline_duration_seconds_sum', route='redactions', mode='normal')
    assert http - pipeline >= 0.035


async def test_final_degraded_response_and_delete_have_separate_counters(client, app, model):
    model.mode['assessment'] = 'garbage'
    response = await post_json(client, '/v3/redaction', EMAIL_REQ)
    sid = response.json()['session_id']
    await client.request('DELETE', '/v3/redaction', json={'session_id': sid})
    assert value(app, 'vg_redaction_responses_total', mode='degraded') == 1
    assert value(app, 'vg_degraded_total', reason='model_output_unparseable', stage='assessment') == 1
    assert value(app, 'vg_http_requests_total', route='/v3/redaction', method='POST', status='200') == 1
    assert value(app, 'vg_http_requests_total', route='/v3/redaction', method='DELETE', status='204') == 1


async def test_capacity_rejection_and_reserved_slot_are_visible(client, app, settings, components):
    settings.max_records = app.state.records.max_records = 1
    original_render = app.state.sessions.components.pseudonymize
    # Exercise the reserved state with a real in-flight request, not just a synthetic gauge.
    import threading
    blocked = threading.Event()

    def paused(*args):
        blocked.set()
        assert resume.wait(2)
        return original_render(*args)

    resume = threading.Event()
    components.pseudonymize = paused
    task = asyncio.create_task(post_json(client, '/v3/redaction', EMAIL_REQ))
    try:
        assert await asyncio.to_thread(blocked.wait, 2)
        assert (await post_json(client, '/v3/redaction', EMAIL_REQ)).status_code == 503
        assert value(app, 'vg_records_reserved') == 1
        assert value(app, 'vg_capacity_rejected_total') == 1
    finally:
        resume.set()
        await task
    assert value(app, 'vg_records_reserved') == 0
    assert value(app, 'vg_records_active') == 1


async def test_auth_failure_has_bounded_route_and_http_timing(client, app):
    response = await client.post('/v3/redaction', json=EMAIL_REQ, headers={'Authorization': 'Bearer wrong'})
    assert response.status_code == 401
    assert value(app, 'vg_http_requests_total', route='/v3/redaction', method='POST', status='401') == 1
    assert value(app, 'vg_http_duration_seconds_count', route='/v3/redaction', method='POST', status='401', mode='error') == 1
