"""V2 contracts: backend switching, exact restoration, isolation and shared-state failures."""
import asyncio
import base64
import time

import fakeredis.aioredis
import httpx
import pytest

from conftest import KEY
from vg_redactor.api.app import create_app
from vg_redactor.contracts.types import RedactionRequestV2
from vg_redactor.settings import IdentitySettings, hash_key
from vg_redactor.tokens.service import CANDIDATE, Principal, TokenService
from vg_redactor.tokens.store import MemoryMappingStore, RedisMappingStore

KEYS = {'k1': base64.b64encode(bytes(range(64))).decode()}
OTHER = 'second-agent'


def body(mode='mapping', text='Call 202-555-0102 and 123-45-6789', **kwargs):
    return {'purpose': 'Summarize', 'email': {'body': text}, 'group_id': 'workflow1',
            'tokenization': {'mode': mode}, **kwargs}


def configure(settings):
    settings.tokenization.keys = KEYS.copy()
    settings.api_key_hashes.add(hash_key(OTHER))
    for key in (KEY, OTHER):
        settings.api_identities[hash_key(key)] = IdentitySettings(tenant_id='tenant1')
    return settings


def client_for(app, key=KEY):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                            base_url='http://test', headers={'Authorization': 'Bearer ' + key})


@pytest.fixture
async def v2(settings, components, model):
    app = create_app(configure(settings), components, model)
    async with client_for(app) as client:
        yield client, app


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_roundtrip_without_record_id_and_exact_text(v2, mode):
    client, app = v2
    response = await client.post('/v2/redactions', json=body(mode))
    assert response.status_code == 200, response.text
    result = response.json()
    assert 'record' not in result
    redacted = result['redacted_email']['body']
    assert '202-555-0102' not in redacted and '123-45-6789' not in redacted
    assert app.state.records.stats()['active'] == 0
    for _ in range(2):
        restore = (await client.post('/v2/restorations', json={'text': redacted})).json()
        assert restore == {'restore_decision': 'RESTORED',
                           'restored_text': body()['email']['body'], 'unmatched_placeholders': []}
    assert bool(app.state.tokens.store._groups) is (mode == 'mapping')


async def test_mixed_modes_requests_agents_and_instances(settings, components, model):
    settings = configure(settings)
    shared = MemoryMappingStore()
    app_a = create_app(settings, components, model, token_store=shared)
    app_b = create_app(settings, components, model, token_store=shared)
    async with client_for(app_a) as a, client_for(app_b, OTHER) as b:
        texts = []
        for mode, original in [('mapping', 'Call 202-555-0102'), ('aes_siv', 'SSN 123-45-6789')]:
            r = await a.post('/v2/redactions', json=body(mode, original))
            assert r.status_code == 200, r.text
            texts.append(r.json()['redacted_email']['body'])
        restored = (await b.post('/v2/restorations', json={'text': ' / '.join(texts)})).json()
        assert restored['restored_text'] == 'Call 202-555-0102 / SSN 123-45-6789'
        assert app_b.state.records.stats()['active'] == 0


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_existing_tokens_preserved_while_new_values_redacted(v2, mode):
    client, _ = v2
    first = (await client.post('/v2/redactions', json=body(mode, 'Call 202-555-0102'))).json()
    original_token = CANDIDATE.findall(first['redacted_email']['body'])[0]
    second = await client.post('/v2/redactions', json=body(mode, original_token + ' then 303-555-0103'))
    assert second.status_code == 200, second.text
    text = second.json()['redacted_email']['body']
    assert original_token in text and '303-555-0103' not in text
    result = (await client.post('/v2/restorations', json={'text': text})).json()
    assert result['restored_text'] == '202-555-0102 then 303-555-0103'
    new_span = second.json()['spans'][0]
    assert new_span['start'] >= len(original_token)


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_tamper_expiry_and_authorization_are_all_or_nothing(v2, settings, mode):
    client, app = v2
    r = (await client.post('/v2/redactions', json=body(mode))).json()
    token = CANDIDATE.findall(r['redacted_email']['body'])[0]
    malformed = token[:-2] + ('A' if token[-2] != 'A' else 'B') + ']'
    cases = [malformed, token.replace(':PHONE_PERSONAL:', ':EMAIL_PERSONAL:'),
             token.replace(':1:', ':2:', 1), '[VG:garbage]', '[VG:unterminated', token[1:], '[PHONE_1]']
    for bad in cases:
        result = (await client.post('/v2/restorations', json={'text': token + ' ' + bad})).json()
        assert result['restore_decision'] == 'BLOCKED', (bad, result)
        assert 'restored_text' not in result
    # Same key material, different tenant: neither backend may resolve the token.
    settings.api_identities[hash_key(OTHER)] = IdentitySettings(tenant_id='another-tenant')
    async with client_for(app, OTHER) as other:
        denied = (await other.post('/v2/restorations', json={'text': token})).json()
        assert denied['restore_decision'] == 'BLOCKED'
    settings.api_identities[hash_key(OTHER)] = IdentitySettings(tenant_id='tenant1', groups=['other'])
    async with client_for(app, OTHER) as other:
        assert (await other.post('/v2/redactions', json=body(mode))).status_code == 403
        assert (await other.post('/v2/restorations', json={'text': token})).json()['restore_decision'] == 'BLOCKED'
    app.state.tokens.clock = lambda: time.time() + 100000
    assert (await client.post('/v2/restorations', json={'text': token})).json()['restore_decision'] == 'BLOCKED'


async def test_mapping_delete_does_not_revoke_aes(v2):
    client, _ = v2
    texts = []
    for mode in ['mapping', 'aes_siv']:
        texts.append((await client.post('/v2/redactions', json=body(mode))).json()['redacted_email']['body'])
    for _ in range(2):
        assert (await client.delete('/v2/groups/workflow1/mappings')).status_code == 204
    assert (await client.post('/v2/restorations', json={'text': texts[0]})).json()['restore_decision'] == 'BLOCKED'
    assert (await client.post('/v2/restorations', json={'text': texts[1]})).json()['restore_decision'] == 'RESTORED'


async def test_defaults_metadata_validation_and_legacy_compatibility(v2, settings):
    client, app = v2
    settings.tokenization.default_mode = 'aes_siv'
    req = body(); req.pop('tokenization'); req['include'] = ['service_info']
    result = (await client.post('/v2/redactions', json=req)).json()
    assert result['tokenization']['mode'] == 'aes_siv'
    assert result['service_info']['tokenization']['restoration_requires_record_id'] is False
    for mutation in [{'tokenization': {'mode': 'unknown'}}, {'mapping': {'retain': True}},
                     {'tokenization': {'ttl_seconds': 1000000}}, {'group_id': '../bad'}]:
        bad = {**body(), **mutation}
        assert (await client.post('/v2/redactions', json=bad)).status_code == 422
    # A full v1 record store cannot prevent stateless AES-SIV or v2 mapping requests.
    app.state.records.max_records = 0
    assert (await client.post('/v2/redactions', json=body('aes_siv'))).status_code == 200
    assert (await client.post('/v2/redactions', json=body('mapping'))).status_code == 200


async def test_missing_keys_fails_closed_and_v1_still_available(settings, components, model):
    app = create_app(settings, components, model)
    async with client_for(app) as client:
        assert (await client.post('/v2/redactions', json=body())).status_code == 503
        assert (await client.post('/v2/restorations', json={'text': 'hello'})).status_code == 503
        assert (await client.post('/v1/redactions', json={'purpose': 'Summarize',
                                                       'email': {'body': 'Hello'}})).status_code == 200


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_key_rotation_and_new_default_do_not_break_old_tokens(v2, settings, mode):
    client, app = v2
    old = (await client.post('/v2/redactions', json=body(mode))).json()['redacted_email']['body']
    rotated = {**KEYS, 'k2': base64.b64encode(bytes(reversed(range(64)))).decode()}
    new_service = TokenService(rotated, 'k2', app.state.tokens.store)
    assert (await new_service.restore(old, Principal('tenant1'))).restore_decision == 'RESTORED'
    # Restart requires configured keys; no per-process random key is used.
    restarted = TokenService(KEYS, 'k1', app.state.tokens.store)
    assert (await restarted.restore(old, Principal('tenant1'))).restore_decision == 'RESTORED'


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_idempotency_replay_and_conflict(v2, mode):
    client, app = v2
    headers = {'Idempotency-Key': 'same-request'}
    first = await client.post('/v2/redactions', json=body(mode), headers=headers)
    second = await client.post('/v2/redactions', json=body(mode), headers=headers)
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert second.headers['Idempotency-Replayed'] == 'true'
    assert first.json()['redacted_email'] == second.json()['redacted_email']
    assert second.json()['request_id'] == second.headers['X-Request-ID']
    assert first.json()['request_id'] != second.json()['request_id']
    assert (await client.post('/v2/redactions', json=body(mode, 'Different'), headers=headers)).status_code == 409


async def test_redis_atomic_concurrent_writes_expiry_and_cross_instance(settings, components, model):
    server = fakeredis.FakeServer()
    clients = [fakeredis.aioredis.FakeRedis(server=server, decode_responses=True) for _ in range(2)]
    stores = [RedisMappingStore('', client=c) for c in clients]
    apps = [create_app(configure(settings), components, model, token_store=s) for s in stores]
    async with client_for(apps[0]) as a, client_for(apps[1], OTHER) as b:
        requests = [body('mapping', f'Call 202-555-{i:04d}') for i in range(10)]
        responses = await asyncio.gather(*[(a if i % 2 else b).post('/v2/redactions', json=req)
                                           for i, req in enumerate(requests)])
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        text = ' / '.join(r.json()['redacted_email']['body'] for r in responses)
        restored = (await b.post('/v2/restorations', json={'text': text})).json()
        assert restored['restored_text'] == ' / '.join(req['email']['body'] for req in requests)
        # Independent TokenService/Redis clients share encrypted values; no plaintext in Redis.
        for key in await clients[0].keys('vg:tokens:*'):
            values = await clients[0].hgetall(key)
            assert all('202-555' not in v for v in values.values())
        # Retaining a shorter request may not shorten older token lifetimes.
        req = body(); req['tokenization']['ttl_seconds'] = 5
        assert (await a.post('/v2/redactions', json=req)).status_code == 200
        for key in await clients[0].keys('vg:tokens:*'):
            assert await clients[0].ttl(key) > 100
        # Cross-instance idempotency returns the same tokenized result.
        h = {'Idempotency-Key': 'shared-idem'}
        first = await a.post('/v2/redactions', json=body(), headers=h)
        second = await b.post('/v2/redactions', json=body(), headers=h)
        assert first.status_code == second.status_code == 200
        assert first.json()['redacted_email'] == second.json()['redacted_email']
        assert second.headers['Idempotency-Replayed'] == 'true'
        await b.delete('/v2/groups/workflow1/mappings')
        assert (await a.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'BLOCKED'
    for c in clients:
        await c.aclose()


async def test_storage_failure_blocks_mapping_but_not_stateless_aes(settings, components, model):
    class Broken(MemoryMappingStore):
        async def put(self, *args):
            raise ConnectionError('CANARY secret internal error')
        async def get(self, *args):
            raise ConnectionError('CANARY secret internal error')
        async def ping(self):
            raise ConnectionError()
    app = create_app(configure(settings), components, model, token_store=Broken())
    async with client_for(app) as client:
        failed = await client.post('/v2/redactions', json=body())
        assert failed.status_code == 503 and 'CANARY' not in failed.text
        aes = await client.post('/v2/redactions', json=body('aes_siv'))
        assert aes.status_code == 200
        text = aes.json()['redacted_email']['body']
        assert (await client.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'RESTORED'
        assert (await client.get('/readyz')).json()['mode'] == 'degraded'


async def test_exact_case_unicode_and_alias_forms_have_distinct_tokens(v2):
    _, app = v2
    from vg_redactor.contracts.types import Candidate, Decision
    for mode in ['mapping', 'aes_siv']:
        original = 'Dana|Dana Whitfield|DANA|李明'
        req = RedactionRequestV2.model_validate(body(mode, original))
        context = app.state.tokens.context(req, Principal('tenant1'), mode, 60)
        decisions = []
        offset = 0
        for value in original.split('|'):
            candidate = Candidate(field='email.body', start=offset, end=offset + len(value),
                                  type='PERSON', detectors={'rules'})
            decisions.append(Decision(candidate=candidate, tier='high', action='redact',
                                      confidence=1, reason='test'))
            offset += len(value) + 1
        out = await context.render(decisions)
        assert len(set(CANDIDATE.findall(out.redacted_email['body']))) == 4
        result = await app.state.tokens.restore(out.redacted_email['body'], Principal('tenant1'))
        assert result.restored_text == original


def test_key_validation():
    for keys, active in [({'k1': 'bad'}, 'k1'), ({'bad:key': KEYS['k1']}, 'bad:key'),
                         ({'k1': base64.b64encode(b'short').decode()}, 'k1'), (KEYS, 'absent')]:
        with pytest.raises(ValueError):
            TokenService(keys, active, MemoryMappingStore())


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_long_encrypted_headers_can_be_passed_to_another_agent(v2, mode):
    client, _ = v2
    address = ('a' * 63 + '.') * 3 + 'b' * 50 + '@example.test'
    assert 250 < len(address) <= 320
    req = body(mode)
    req['email']['from'] = {'name': 'Sender', 'address': address}
    first = await client.post('/v2/redactions', json=req)
    assert first.status_code == 200, first.text
    req['email'] = first.json()['redacted_email']
    second = await client.post('/v2/redactions', json=req)
    assert second.status_code == 200, second.text
    assert second.json()['redacted_email']['from']['address'] == req['email']['from']['address']
    restored = (await client.post('/v2/restorations', json={'text': req['email']['from']['address']})).json()
    assert restored['restored_text'] == address


async def test_concurrent_idempotency_conflict_and_retry_after_failure(v2, model):
    client, _ = v2
    entered, release = asyncio.Event(), asyncio.Event()
    original_generate = model.generate

    async def paused(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original_generate(*args, **kwargs)

    model.generate = paused
    headers = {'Idempotency-Key': 'concurrent'}
    first = asyncio.create_task(client.post('/v2/redactions', json=body(), headers=headers))
    await asyncio.wait_for(entered.wait(), 1)
    try:
        duplicate = await client.post('/v2/redactions', json=body(), headers=headers)
        assert duplicate.status_code == 409 and duplicate.headers['Retry-After'] == '1'
    finally:
        release.set()
    assert (await first).status_code == 200
    failed = body(text='[VG:broken]')
    h = {'Idempotency-Key': 'retry-failed'}
    assert (await client.post('/v2/redactions', json=failed, headers=h)).status_code == 422
    # Failed input did not leave a stale lease: correcting it with the same key can succeed.
    assert (await client.post('/v2/redactions', json=body(), headers=h)).status_code == 200


async def test_v2_degraded_flow_and_no_private_text_in_observability(v2, settings, model, caplog):
    import logging
    client, app = v2
    caplog.set_level(logging.INFO)
    logging.getLogger('vg_redactor').propagate = True
    model.mode['assessment'] = 'garbage'
    for mode in ['mapping', 'aes_siv']:
        response = await client.post('/v2/redactions', json=body(mode),
                                     headers={'Idempotency-Key': mode + '-degraded'})
        assert response.status_code == 200 and response.json()['degraded'] is True
        text = response.json()['redacted_email']['body']
        restored = (await client.post('/v2/restorations', json={'text': text})).json()
        assert restored['restored_text'] == body()['email']['body']
    observations = caplog.text + open(settings.audit_log_path).read() + app.state.metrics.render().decode()
    for private in ['202-555-0102', '123-45-6789', KEYS['k1'], '[VG:1:']:
        assert private not in observations
    assert 'token_backend' in observations and 'vg_token_redactions_total' in observations


async def test_default_api_keys_are_isolated(settings, components, model):
    settings.tokenization.keys = KEYS
    settings.api_key_hashes.add(hash_key(OTHER))
    app = create_app(settings, components, model)
    async with client_for(app) as a, client_for(app, OTHER) as b:
        for mode in ['mapping', 'aes_siv']:
            text = (await a.post('/v2/redactions', json=body(mode))).json()['redacted_email']['body']
            assert (await b.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'BLOCKED'


def test_settings_from_environment(tmp_path, monkeypatch):
    from vg_redactor.settings import Settings
    import json
    config = tmp_path / 'service.yaml'; config.write_text('{}')
    monkeypatch.setenv('VG_API_KEYS', KEY)
    monkeypatch.setenv('VG_TOKEN_KEYS', json.dumps(KEYS))
    monkeypatch.setenv('VG_ACTIVE_TOKEN_KEY_ID', 'k1')
    monkeypatch.setenv('VG_TOKEN_STORE', 'redis')
    monkeypatch.setenv('VG_REDIS_URL', 'redis://private-redis:6379/0')
    monkeypatch.setenv('VG_API_IDENTITIES', json.dumps({hash_key(KEY): {'tenant_id': 'tenant1',
                                                                     'groups': ['workflow1']}}))
    result = Settings.load(config)
    assert result.tokenization.keys == KEYS and result.tokenization.store == 'redis'
    assert result.api_identities[hash_key(KEY)].groups == ['workflow1']
    assert KEYS['k1'] not in repr(result)


async def test_existing_token_contents_do_not_reach_local_model(v2, model):
    client, _ = v2
    text = (await client.post('/v2/redactions', json=body('aes_siv', 'Call 202-555-0102'))).json()['redacted_email']['body']
    prompts = []
    original = model.generate

    async def recording(prompt, **kwargs):
        prompts.append(prompt)
        return await original(prompt, **kwargs)

    model.generate = recording
    result = await client.post('/v2/redactions', json=body('mapping', text + ' then 303-555-0103'))
    assert result.status_code == 200
    assert prompts and all('[VG' not in p and '202-555-0102' not in p for p in prompts)


async def test_mapping_reads_and_masking_obey_end_to_end_deadline(settings, components, model):
    class SlowReads(MemoryMappingStore):
        async def get(self, *args):
            await asyncio.sleep(1)
            return await super().get(*args)

    settings = configure(settings)
    store = SlowReads()
    app = create_app(settings, components, model, token_store=store)
    async with client_for(app) as client:
        text = (await client.post('/v2/redactions', json=body())).json()['redacted_email']['body']
        settings.timeout_ms = 20
        assert (await client.post('/v2/restorations', json={'text': text})).status_code == 504
        h = {'Idempotency-Key': 'timeout-mask'}
        assert (await client.post('/v2/redactions', json=body(text=text), headers=h)).status_code == 504
        # A timed-out pre-detection operation releases its idempotency lease.
        assert (await client.post('/v2/redactions', json=body('aes_siv', 'Hello'), headers=h)).status_code == 200
