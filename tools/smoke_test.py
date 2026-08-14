from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    status = client.get('/api/status')
    assert status.status_code == 200
    assert status.json()['provider'] == 'demo'
    detail = client.get('/api/analyze/EXCL')
    assert detail.status_code == 200
    assert detail.json()['decision']['decision'] == 'DEMO — ANALYSIS DISABLED'
    scan = client.get('/api/scanner?limit=5')
    assert scan.status_code == 200 and len(scan.json()) == 5
    assert all(x['decision'] == 'DEMO — ANALYSIS DISABLED' for x in scan.json())
    assert client.get('/api/rulebook').status_code == 200
print('SMOKE TEST OK — demo decisions are disabled as intended')
