"""Independent conversation keys, distributed creation, lifecycle and legacy compatibility."""
import asyncio
import base64
import json
import time

import fakeredis.aioredis
import pytest

from vg_redactor.contracts.errors import ProblemError
from vg_redactor.tokens.conversation_store import MemoryConversationStore
from vg_redactor.tokens.service import TokenService
from vg_redactor.tokens.store import MemoryMappingStore, RedisMappingStore
from vg_redactor.tokens.wire import Principal, TOKEN_V2

from test_tokens_v2 import KEYS, OTHER, body, client_for, configure
from vg_redactor.api.app import create_app
from vg_redactor.settings import IdentitySettings, hash_key


def service(store=None, *, clock=time.time, max_life=86400, active='k1', keys=None):
    return TokenService(keys or KEYS, active, store or MemoryMappingStore(), clock=clock,
                        conversation_max_lifetime_seconds=max_life)


async def render(svc, *, mode='aes_siv', group='workflow1', ttl=60, tenant='tenant1'):
    from vg_redactor.contracts.types import Candidate, Decision, RedactionRequestV2
    req = RedactionRequestV2.model_validate(body(mode, '202-555-0102', group_id=group))
    context = svc.context(req, Principal(tenant), mode, ttl)
    decision = Decision(candidate=Candidate(field='email.body', start=0, end=12,
        type='PHONE_PERSONAL', detectors={'rules'}), tier='high', action='redact',
        confidence=1, reason='test')
    out = await context.render([decision])
    return out.redacted_email['body'], context


async def test_concurrent_creation_reuses_one_random_key_and_separates_conversations():
    svc = service()
    principal = Principal('tenant1')
    keys = await asyncio.gather(*[svc.conversations.get_or_create(principal, 'workflow1', 60)
                                  for _ in range(30)])
    assert len({key.scope for key in keys}) == len({key.seed for key in keys}) == 1
    other = await svc.conversations.get_or_create(principal, 'workflow2', 60)
    tenant = await svc.conversations.get_or_create(Principal('tenant2'), 'workflow1', 60)
    assert len({keys[0].seed, other.seed, tenant.seed}) == 3
    assert keys[0].derive('token-aes-siv', 64) != keys[0].derive('mapping-aes-siv', 64)
    assert keys[0].derive('reference-hmac', 32) != keys[0].seed
    raw = await svc.conversations.store.get('tenant1', keys[0].scope)
    assert 'workflow1' not in raw and base64.b64encode(keys[0].seed).decode() not in raw
    assert 'seed' not in repr(keys[0]) and 'workflow1' not in repr(keys[0])


@pytest.mark.parametrize('mode', ['mapping', 'aes_siv'])
async def test_stable_tokens_across_time_and_lifetime_extension(mode):
    start = int(time.time()); now = [start]
    svc = service(clock=lambda: now[0])
    first, ctx = await render(svc, mode=mode)
    now[0] += 10
    second, later = await render(svc, mode=mode, ttl=120)
    different, _ = await render(svc, mode=mode, group='workflow2')
    assert first == second and first != different
    assert later.expires == start + 130 > ctx.expires
    assert first.startswith('[VG:2:')
    assert str(start + 60) not in first
    assert (await svc.restore(first, Principal('tenant1'))).restored_text == '202-555-0102'
    assert len(svc.store._groups) == (2 if mode == 'mapping' else 0)
    assert TOKEN_V2.fullmatch(first)


async def test_idle_expiry_maximum_lifetime_and_no_revival():
    start = int(time.time()); now = [start]
    svc = service(clock=lambda: now[0], max_life=30)
    token, context = await render(svc, ttl=10)
    now[0] += 5
    short = await svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 1)
    assert short.expires_at == start + 10
    now[0] = start + 8
    extended = await svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 15)
    assert extended.expires_at == start + 23
    now[0] = start + 22
    capped = await svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 1000)
    assert capped.expires_at == start + 30
    now[0] = start + 30
    assert (await svc.restore(token, Principal('tenant1'))).restore_decision == 'BLOCKED'
    with pytest.raises(ProblemError) as exc:
        await svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 60)
    assert exc.value.status == 410
    # Idle expiry before the hard maximum is equally final until tombstone retention ends.
    now[0] = start
    idle, _ = await render(svc, group='idle', ttl=5)
    now[0] = start + 6
    assert (await svc.restore(idle, Principal('tenant1'))).restore_decision == 'BLOCKED'
    with pytest.raises(ProblemError):
        await render(svc, group='idle')


async def test_master_rotation_rewraps_without_changing_tokens_or_dek():
    store = MemoryMappingStore(); old = service(store)
    token, context = await render(old)
    rotated = {**KEYS, 'k2': base64.b64encode(bytes(reversed(range(64)))).decode()}
    new = service(store, keys=rotated, active='k2')
    assert (await new.restore(token, Principal('tenant1'))).restore_decision == 'RESTORED'
    raw = json.loads(await store.conversations.get('tenant1', context.key.scope))
    assert raw['kek_id'] == 'k2'
    current = await new.conversations.load(Principal('tenant1'), context.key.scope, '1')
    assert current.seed == context.key.seed
    repeated, _ = await render(new)
    assert repeated == token
    # The old wrapping key can be retired for this already rewrapped format-2 conversation.
    only_new = service(store, keys={'k2': rotated['k2']}, active='k2')
    assert (await only_new.restore(token, Principal('tenant1'))).restore_decision == 'RESTORED'
    no_persistence = service(keys={'k2': rotated['k2']}, active='k2')
    assert (await no_persistence.restore(token, Principal('tenant1'))).restore_decision == 'BLOCKED'


async def test_redis_creation_race_cross_instance_restart_and_encrypted_records():
    server = fakeredis.FakeServer()
    clients = [fakeredis.aioredis.FakeRedis(server=server, decode_responses=True) for _ in range(2)]
    stores = [RedisMappingStore('', client=client) for client in clients]
    services = [service(store) for store in stores]
    # Force both workers to observe an absent index before their first atomic create.
    barrier = asyncio.Event(); arrivals = [0]
    for store in stores:
        original = store.conversations.find
        async def racing_find(*args, _original=original):
            value = await _original(*args)
            if value is None:
                arrivals[0] += 1
                if arrivals[0] >= 2:
                    barrier.set()
                await barrier.wait()
            return value
        store.conversations.find = racing_find
    outputs = await asyncio.gather(*[render(services[i % 2], mode='mapping', ttl=60 + i)
                                     for i in range(20)])
    scopes = {context.key.scope for _, context in outputs}
    seeds = {context.key.seed for _, context in outputs}
    assert len(scopes) == len(seeds) == 1
    assert len({token for token, _ in outputs}) == 1
    index_keys = await clients[0].keys('vg:conversation:*:index:*')
    record_keys = await clients[0].keys('vg:conversation:*:key:*')
    assert len(index_keys) == len(record_keys) == 1
    raw = await clients[0].get(record_keys[0])
    assert 'workflow1' not in raw and base64.b64encode(next(iter(seeds))).decode() not in raw
    record = json.loads(raw)
    assert record['expires_at'] >= int(time.time()) + 78
    restarted = service(stores[1])
    assert (await restarted.restore(outputs[0][0], Principal('tenant1'))).restore_decision == 'RESTORED'
    for client in clients:
        await client.aclose()


async def test_close_revokes_both_modes_rejects_new_writes_and_cached_replays(settings, components, model):
    app = create_app(configure(settings), components, model)
    async with client_for(app) as a, client_for(app, OTHER) as b:
        texts = []
        for mode in ['mapping', 'aes_siv']:
            result = await a.post('/v2/redactions', json=body(mode),
                                   headers={'Idempotency-Key': mode})
            assert result.status_code == 200, result.text
            assert result.json()['tokenization']['format_version'] == 2
            texts.append(result.json()['redacted_email']['body'])
        for _ in range(2):
            assert (await b.delete('/v2/groups/workflow1')).status_code == 204
        for text in texts:
            assert (await a.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'BLOCKED'
        for mode in ['mapping', 'aes_siv']:
            for headers in [{}, {'Idempotency-Key': mode}]:
                response = await a.post('/v2/redactions', json=body(mode), headers=headers)
                assert response.status_code == 410
        key_store = app.state.tokens.conversations.store
        closed = json.loads(await key_store.find('tenant1', 'workflow1'))
        assert closed['status'] == 'closed' and closed['wrapped_key'] is None
        assert not app.state.tokens.store._groups
        # Closing an unused group creates a tombstone instead of silently allowing later writes.
        assert (await a.delete('/v2/groups/unused')).status_code == 204
        assert (await a.post('/v2/redactions', json=body(group_id='unused'))).status_code == 410


async def test_close_is_tenant_and_group_scoped(settings, components, model):
    settings = configure(settings)
    settings.api_identities[hash_key(OTHER)] = IdentitySettings(tenant_id='tenant2', groups=['workflow2'])
    app = create_app(settings, components, model)
    async with client_for(app) as a, client_for(app, OTHER) as b:
        text = (await a.post('/v2/redactions', json=body())).json()['redacted_email']['body']
        assert (await b.delete('/v2/groups/workflow1')).status_code == 403
        settings.api_identities[hash_key(OTHER)] = IdentitySettings(tenant_id='tenant2')
        assert (await b.delete('/v2/groups/workflow1')).status_code == 204
        assert (await a.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'RESTORED'


async def test_key_storage_failure_and_corrupt_wrapping_fail_closed(settings, components, model):
    class Broken(MemoryConversationStore):
        async def find(self, *args):
            raise ConnectionError('CANARY secret')
        async def get(self, *args):
            raise ConnectionError('CANARY secret')
    store = MemoryMappingStore()
    svc = service(store)
    token, context = await render(svc)
    store.conversations = Broken()
    app = create_app(configure(settings), components, model, token_store=store)
    async with client_for(app) as client:
        for mode in ['mapping', 'aes_siv']:
            response = await client.post('/v2/redactions', json=body(mode))
            assert response.status_code == 503 and 'CANARY' not in response.text
        assert (await client.post('/v2/restorations', json={'text': token})).status_code == 503
    # Stored ciphertext modification cannot result in a new replacement key or plaintext.
    raw = await svc.conversations.store.find('tenant1', 'workflow1')
    record = json.loads(raw); record['wrapped_key'] = 'AAAA'
    await svc.conversations.store.swap('tenant1', context.key.scope, raw,
        json.dumps(record), int(time.time()) + 86400)
    with pytest.raises(ProblemError) as exc:
        await svc.restore(token, Principal('tenant1'))
    assert exc.value.status == 503


async def test_close_during_detection_cannot_publish_a_new_token(settings, components, model):
    app = create_app(configure(settings), components, model)
    entered, release = asyncio.Event(), asyncio.Event()
    generate = model.generate
    async def paused(*args, **kwargs):
        entered.set()
        await release.wait()
        return await generate(*args, **kwargs)
    model.generate = paused
    async with client_for(app) as client:
        running = asyncio.create_task(client.post('/v2/redactions', json=body('aes_siv')))
        await asyncio.wait_for(entered.wait(), 1)
        try:
            assert (await client.delete('/v2/groups/workflow1')).status_code == 204
        finally:
            release.set()
        result = await running
        assert result.status_code == 410 and 'redacted_email' not in result.json()


async def test_legacy_wire_vectors_and_new_tokens_restore_together():
    svc = service()
    # Frozen format-1 vectors under KEYS['k1']; generated from the pre-manager wire contract.
    legacy_mapping = '[VG:1:m:PHONE_PERSONAL:k1:5907f099785fd04bba56c543c17bad38:4102444800:bbdKibvvP6QDZfGpYxbse3BHev-958hS.FUR-PvfOx5FORg-dhv4YLg]'
    legacy_siv = '[VG:1:s:PHONE_PERSONAL:k1:5907f099785fd04bba56c543c17bad38:4102444800:We0fGH6MdA9ExQb04gTxaA9Cd-OJ4QGCUczWlQ]'
    await svc.store.put('9afbe7e5b26e934c84a3ba0b47fbe54e13212361db9541ce304aad55d99b7578',
        {'bbdKibvvP6QDZfGpYxbse3BHev-958hS': 'xSe9IUPRygudi3vbpJhPpGCdFGz3VIzxSn616A'}, 4102444800)
    new_mapping, _ = await render(svc, mode='mapping')
    new_siv, _ = await render(svc)
    text = ' / '.join([legacy_mapping, legacy_siv, new_mapping, new_siv])
    assert (await svc.restore(text, Principal('tenant1'))).restored_text == ' / '.join(['202-555-0102'] * 4)
    assert (await svc.restore(text, Principal('tenant2'))).restore_decision == 'BLOCKED'


async def test_cached_result_survives_kek_rotation_and_retirement(settings, components, model):
    settings = configure(settings)
    store = MemoryMappingStore()
    app = create_app(settings, components, model, token_store=store)
    async with client_for(app) as client:
        first = await client.post('/v2/redactions', json=body('aes_siv'),
                                  headers={'Idempotency-Key': 'rotation'})
        assert first.status_code == 200
        cache = app.state.tokens  # retain the current HTTP app, but rotate its key manager in place
        new_key = base64.b64encode(bytes(reversed(range(64)))).decode()
        cache.keys['k2'] = base64.b64decode(new_key)
        cache.conversations.active_key_id = 'k2'
        cache.active_key_id = 'k2'
        second = await client.post('/v2/redactions', json=body('aes_siv'),
                                   headers={'Idempotency-Key': 'rotation'})
        assert second.status_code == 200 and second.headers['Idempotency-Replayed'] == 'true'
        cache.keys.pop('k1')
        third = await client.post('/v2/redactions', json=body('aes_siv'),
                                  headers={'Idempotency-Key': 'rotation'})
        assert third.status_code == 200
        assert first.json()['redacted_email'] == third.json()['redacted_email']


async def test_mixed_conversation_cache_cannot_bypass_closure(settings, components, model):
    app = create_app(configure(settings), components, model)
    async with client_for(app) as client:
        foreign = (await client.post('/v2/redactions', json=body('aes_siv', group_id='other'))).json()['redacted_email']['body']
        request = body('aes_siv', foreign + ' and 303-555-0103')
        headers = {'Idempotency-Key': 'mixed'}
        assert (await client.post('/v2/redactions', json=request, headers=headers)).status_code == 200
        assert (await client.delete('/v2/groups/other')).status_code == 204
        # The request's own group remains open, but an embedded conversation was closed.
        assert (await client.post('/v2/redactions', json=request, headers=headers)).status_code == 409


async def test_new_tokens_reject_scope_type_and_version_tampering():
    svc = service()
    for mode in ['mapping', 'aes_siv']:
        token, ctx = await render(svc, mode=mode)
        for bad in [token.replace(ctx.key.scope, '0' * 32),
                    token.replace(':PHONE_PERSONAL:', ':EMAIL_PERSONAL:'),
                    token.replace(':1:', ':2:'), token.replace('[VG:2:', '[VG:9:')]:
            result = await svc.restore(token + ' ' + bad, Principal('tenant1'))
            assert result.restore_decision == 'BLOCKED' and result.restored_text is None


async def test_redis_close_race_with_refresh_cannot_reactivate_key():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = RedisMappingStore('', client=client)
    svc = service(store)
    token, _ = await render(svc)
    await asyncio.gather(
        svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 120),
        svc.conversations.close(Principal('tenant1'), 'workflow1'), return_exceptions=True)
    record = json.loads(await store.conversations.find('tenant1', 'workflow1'))
    assert record['status'] == 'closed' and record['wrapped_key'] is None
    assert (await svc.restore(token, Principal('tenant1'))).restore_decision == 'BLOCKED'
    await client.aclose()


async def test_aes_extension_also_retains_existing_mapping_entries():
    now = [int(time.time())]
    svc = service(clock=lambda: now[0])
    token, context = await render(svc, mode='mapping', ttl=60)
    now[0] += 30
    await render(svc, mode='aes_siv', ttl=120)
    _, expiry = svc.store._groups[svc._storage_group(Principal('tenant1'), 'conversation-1', context.key.scope)]
    assert expiry == now[0] + 120
    assert (await svc.restore(token, Principal('tenant1'))).restore_decision == 'RESTORED'


async def test_explicit_rewrap_does_not_extend_deadline():
    start = int(time.time()); now = [start]
    store = MemoryMappingStore(); svc = service(store, clock=lambda: now[0])
    token, ctx = await render(svc, ttl=60)
    now[0] += 20
    rotated = {**KEYS, 'k2': base64.b64encode(bytes(reversed(range(64)))).decode()}
    new = service(store, keys=rotated, active='k2', clock=lambda: now[0])
    await new.conversations.rewrap(Principal('tenant1'), 'workflow1')
    record = json.loads(await store.conversations.find('tenant1', 'workflow1'))
    assert record['expires_at'] == start + 60 and record['kek_id'] == 'k2'
    assert (await new.restore(token, Principal('tenant1'))).restore_decision == 'RESTORED'


async def test_close_remains_effective_if_mapping_cleanup_fails(settings, components, model):
    class FailsOnce(MemoryMappingStore):
        fail = True
        async def delete(self, groups):
            if self.fail:
                self.fail = False
                raise ConnectionError()
            return await super().delete(groups)
    store = FailsOnce()
    app = create_app(configure(settings), components, model, token_store=store)
    async with client_for(app) as client:
        text = (await client.post('/v2/redactions', json=body())).json()['redacted_email']['body']
        assert (await client.delete('/v2/groups/workflow1')).status_code == 503
        assert (await client.post('/v2/restorations', json={'text': text})).json()['restore_decision'] == 'BLOCKED'
        assert (await client.post('/v2/redactions', json=body())).status_code == 410
        assert (await client.delete('/v2/groups/workflow1')).status_code == 204
        assert not store._groups


async def test_close_during_mapping_commit_is_detected_before_response():
    class ClosesOnCommit(MemoryMappingStore):
        manager = None
        async def put(self, group, values, expires_at):
            await super().put(group, values, expires_at)
            await self.manager.close(Principal('tenant1'), 'workflow1')
    store = ClosesOnCommit(); svc = service(store)
    store.manager = svc.conversations
    with pytest.raises(ProblemError) as exc:
        await render(svc, mode='mapping')
    assert exc.value.status == 410


async def test_malformed_key_record_fails_closed_without_replacement():
    svc = service()
    token, ctx = await render(svc)
    store = svc.conversations.store
    raw = await store.get('tenant1', ctx.key.scope)
    await store.swap('tenant1', ctx.key.scope, raw, '{broken', int(time.time()) + 86400)
    for action in [lambda: svc.restore(token, Principal('tenant1')),
                   lambda: svc.conversations.get_or_create(Principal('tenant1'), 'workflow1', 60)]:
        with pytest.raises(ProblemError) as exc:
            await action()
        assert exc.value.status == 503
    assert await store.get('tenant1', ctx.key.scope) == '{broken'
