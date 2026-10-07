"""Focused test for the badge auto-evaluation engine and challenge progress."""
import os
import sys
import tempfile
import unittest
from unittest import mock

# Point the app at a throwaway DB before importing any backend module.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)
if 'DB_URL' not in os.environ:
    os.environ['DB_URL'] = os.path.join(tempfile.mkdtemp(), 'test_badges.db')

import models  # noqa: E402 (import triggers init_db on the temp DB)
import gamification.badges as badges  # noqa: E402


class BadgeEngineTest(unittest.TestCase):
    def setUp(self):
        conn = models.get_db()
        for table in ('user_events', 'user_challenges', 'user_badges', 'collections',
                      'settings', 'readings', 'anomalies', 'predictions', 'activity',
                      'users', 'bins'):
            conn.execute("DELETE FROM " + table)
        conn.execute("INSERT INTO bins (id, level, status) VALUES ('wetBin', 0, 'empty')")
        conn.execute("INSERT INTO bins (id, level, status) VALUES ('dryBin', 0, 'empty')")
        conn.commit()
        conn.close()
        self.uid = models.create_user('tester', 'tester@example.com', 'secret123', 'Tester')

    def _one_collection(self):
        models.update_bin('wetBin', 60, distance=5, user_id=self.uid)
        models.update_bin('wetBin', 3, distance=90, user_id=self.uid)

    @mock.patch('gamification.badges.socketio')
    def test_collector_10_unlocks_and_emits(self, sock):
        for _ in range(10):
            self._one_collection()
        result = badges.evaluate_user(self.uid)
        unlocked_ids = [b['id'] for b in result['badges']]
        self.assertIn('collector_10', unlocked_ids)
        self.assertNotIn('collector_50', unlocked_ids)
        self.assertTrue(any(call.args[0] == 'badge_unlocked' for call in sock.emit.call_args_list))

    @mock.patch('gamification.badges.socketio')
    def test_night_owl_and_data_nerd_unlock(self, _sock):
        conn = models.get_db()
        conn.execute(
            "INSERT INTO collections (bin_type, level_before, user_id, collected_at) "
            "VALUES ('wetBin', 55, ?, '2026-09-10 02:30:00')", (self.uid,))
        for _ in range(10):
            conn.execute(
                "INSERT INTO user_events (user_id, event_type) VALUES (?, 'analytics_view')",
                (self.uid,))
        conn.commit()
        conn.close()
        result = badges.evaluate_user(self.uid)
        unlocked_ids = [b['id'] for b in result['badges']]
        self.assertIn('night_owl', unlocked_ids)
        self.assertIn('data_nerd', unlocked_ids)

    @mock.patch('gamification.badges.socketio')
    def test_eco_score_challenge_progress(self, _sock):
        for _ in range(10):
            self._one_collection()
        challenges = badges.evaluate_user(self.uid)['challenges']
        eco = next(c for c in challenges if c.get('metric') == 'eco_score_month')
        self.assertEqual(eco['progress'], 100)
        self.assertEqual(eco['completed'], 1)


if __name__ == '__main__':
    unittest.main()