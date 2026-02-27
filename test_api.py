import unittest
from app import create_app

class APITestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_health_check(self):
        res = self.client.get('/health')
        self.assertEqual(res.status_code, 200)

    def test_get_open_issues(self):
        res = self.client.get('/api/issues/open')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), 2)

    def test_get_issue_detail(self):
        res = self.client.get('/api/issues/test-id-123')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['id'], "test-id-123")
        self.assertEqual(len(data['data']['options']), 2)

    def test_get_my_info(self):
        res = self.client.get('/api/users/me')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual('test@nostradapick.com', data['data'].get("email"))

if __name__ == '__main__':
    unittest.main()
