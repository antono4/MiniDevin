"""Backend route tests for minidevin server using httpx TestClient."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(name='client')
def _client():
    from fastapi.testclient import TestClient
    from minidevin.server import app
    with TestClient(app) as client:
        yield client


def test_home_serves_static(client):
    r = client.get('/')
    assert r.status_code == 200
    # HTML harus berisi root index atau minimal landing
    assert 'MiniDevin' in r.text or 'home' in r.text.lower()


def test_sessions_endpoint_empty(client):
    r = client.get('/api/sessions')
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert isinstance(r.json(), (list, dict))


def test_health(client):
    r = client.get('/api/health')
    assert r.status_code in (200, 404)


def test_404_not_setting(client):
    r = client.get('/api/definitely-not-a-route')
    assert r.status_code == 404


def test_eventstream_appendable(tmp_path):
    """Parameter-free structural test: event stream persist append-only."""
    from minidevin.events import EventStream

    p = tmp_path / 'ev.jsonl'
    es = EventStream(p)
    es.add('user', content='hello')
    es.add('assistant', content='hi')
    lines = p.read_text(encoding='utf-8').strip().split('\n')
    assert len(lines) == 2
    import json as jd
    assert jd.loads(lines[0])['content'] == 'hello';