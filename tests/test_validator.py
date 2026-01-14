import unittest
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.news_validator import NewsValidator

class TestNewsValidator(unittest.TestCase):
    def test_title_validation(self):
        """Test title length and content validation"""
        # Too short
        self.assertEqual(NewsValidator.validate_news_item({'title': 'Hi', 'url': 'http://a.com', 'source': 's'})[0], False)
        # Valid
        self.assertEqual(NewsValidator.validate_news_item({'title': 'Valid Title Here', 'url': 'http://a.com', 'source': 's'})[0], True)
        # Suspicious chars
        self.assertEqual(NewsValidator.validate_news_item({'title': 'Hack -- drop table', 'url': 'http://a.com', 'source': 's'})[0], False)

    def test_is_today_news(self):
        """Test freshness check"""
        now = datetime.now()
        
        # Fresh news (1 hour ago)
        news_fresh = {'published_at': (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')}
        self.assertTrue(NewsValidator.is_today_news(news_fresh, max_age_hours=24))

        # Stale news (25 hours ago)
        news_stale = {'published_at': (now - timedelta(hours=25)).strftime('%Y-%m-%d %H:%M:%S')}
        self.assertFalse(NewsValidator.is_today_news(news_stale, max_age_hours=24))

        # Invalid date format (should default to True to avoid missing news)
        news_invalid = {'published_at': 'invalid-date'}
        self.assertTrue(NewsValidator.is_today_news(news_invalid))

if __name__ == '__main__':
    unittest.main()
