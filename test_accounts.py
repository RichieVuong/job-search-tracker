import tempfile
import unittest
from pathlib import Path

import database
# Tests always use disposable SQLite, even when Supabase is configured locally.
database.DATABASE_URL = ''
from fastapi.testclient import TestClient
from app import app, require_user


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_FILE
        database.DATABASE_FILE = str(Path(self.temp.name) / 'test.db')
        database.initialize_database()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        database.DATABASE_FILE = self.original
        self.temp.cleanup()

    def test_anonymous_requests_are_denied(self):
        self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/start')
        self.assertEqual(self.client.get('/health').json(), {'status':'ok'})
        self.assertEqual(self.client.get('/auth/me').headers['cache-control'], 'no-store')
        for path in ['/applications/recent', '/applications/count', '/applications/stats', '/applications/sections', '/applications/search?company=A']:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post('/applications', json={'company':'A','role':'B','status':'Applied'}).status_code, 401)
        self.assertEqual(self.client.patch('/applications/1', json={'status':'Offer'}).status_code, 401)
        self.assertEqual(self.client.delete('/applications/1').status_code, 401)

    def test_cross_site_writes_are_rejected(self):
        app.dependency_overrides[require_user] = lambda: 'alice'
        response = self.client.post('/goals', json={'text':'test'}, headers={'Origin':'https://other-site.example'})
        self.assertEqual(response.status_code, 403)

    def test_accounts_are_isolated(self):
        app.dependency_overrides[require_user] = lambda: 'alice'
        row = self.client.post('/applications', json={'company':'Acme','role':'SWE','status':'Applied'}).json()
        app.dependency_overrides[require_user] = lambda: 'bob'
        self.assertEqual(self.client.get('/applications/recent').json(), [])
        self.assertEqual(self.client.get('/applications/search?company=Ac').json(), [])
        self.assertEqual(self.client.get('/applications/count').json()['count'], 0)
        self.assertEqual(self.client.get('/applications/stats').json()['total'], 0)
        self.assertEqual(self.client.get('/applications/sections').json(), {'offers':[], 'in_progress':[]})
        self.assertEqual(self.client.patch(f'/applications/{row["id"]}', json={'status':'Offer'}).status_code, 404)
        self.assertEqual(self.client.delete(f'/applications/{row["id"]}').status_code, 404)
        app.dependency_overrides[require_user] = lambda: 'alice'
        self.assertEqual(self.client.patch(f'/applications/{row["id"]}', json={'status':'Offer'}).status_code, 200)
        self.assertEqual(self.client.get('/applications/recent').json()[0]['status'], 'Offer')
        self.assertEqual(self.client.delete(f'/applications/{row["id"]}').status_code, 200)

    def test_goals_are_private_and_persist(self):
        self.assertEqual(self.client.get('/goals').status_code, 401)
        app.dependency_overrides[require_user] = lambda: 'alice'
        goal = self.client.post('/goals', json={'text':'Apply to five roles'}).json()
        app.dependency_overrides[require_user] = lambda: 'bob'
        self.assertEqual(self.client.get('/goals').json(), [])
        self.assertEqual(self.client.patch(f'/goals/{goal["id"]}', json={'completed':True}).status_code, 404)
        app.dependency_overrides[require_user] = lambda: 'alice'
        self.assertEqual(self.client.patch(f'/goals/{goal["id"]}', json={'completed':True}).status_code, 200)
        self.assertEqual(self.client.get('/goals').json()[0]['completed'], 1)
        self.assertEqual(self.client.post('/goals', json={'text':'  '}).status_code, 400)

    def test_details_persist_and_are_private(self):
        row = database.create_application('alice', 'Acme', 'SWE', 'Applied')
        url = f'/applications/{row["id"]}/details'
        payload = {'company':'New name', 'role':'Intern', 'job_url':'https://example.com/job', 'notes':'Interview prep <notes>'}
        self.assertEqual(self.client.patch(url, json=payload).status_code, 401)
        app.dependency_overrides[require_user] = lambda: 'bob'
        self.assertEqual(self.client.patch(url, json=payload).status_code, 404)
        app.dependency_overrides[require_user] = lambda: 'alice'
        self.assertEqual(self.client.patch(url, json=payload).status_code, 200)
        saved = self.client.get('/applications/recent').json()[0]
        for key, value in payload.items():
            self.assertEqual(saved[key], value)
        self.assertEqual(saved['created_at'], row['created_at'])
        self.assertEqual(saved['status'], 'Applied')
        self.assertEqual(self.client.patch(url, json={**payload, 'job_url':'javascript:alert(1)'}).status_code, 422)
        self.assertEqual(self.client.patch(url, json={**payload, 'company':'  '}).status_code, 400)
        self.assertEqual(self.client.patch(url, json={**payload, 'job_url':None, 'notes':''}).status_code, 200)
        self.assertEqual(database.get_application_by_id('alice',row['id'])['job_url'], '')

    def test_unassigned_legacy_data_is_preserved_and_private(self):
        with database.get_connection() as conn:
            conn.execute("INSERT INTO applications(company,role,status) VALUES('Legacy','SWE','Applied')")
        database.initialize_database()
        self.assertEqual(database.get_recent_applications('alice'), [])
        with database.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM applications').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
