import unittest
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.priority_calculator import PriorityCalculator

class TestPriorityCalculator(unittest.TestCase):
    def test_critical_keywords(self):
        """Test detection of critical keywords"""
        news = {'title': 'Major hack detected in Binance', 'summary': 'Exchange breached security', 'source': 'coindesk'}
        priority = PriorityCalculator.calculate_priority(news)
        self.assertEqual(priority, 10, "Hack should be priority 10")

    def test_influential_persons(self):
        """Test detection of influential persons"""
        news = {'title': 'Elon Musk tweets about Doge', 'summary': 'To the moon', 'source': 'twitter'}
        priority = PriorityCalculator.calculate_priority(news)
        self.assertGreaterEqual(priority, 6, "Elon Musk should be at least priority 6")

    def test_low_priority(self):
        """Test low priority news"""
        news = {'title': 'Bitcoin price is stable', 'summary': 'Nothing happened today', 'source': 'random blog'}
        priority = PriorityCalculator.calculate_priority(news)
        # Base priority is 1 if text exists
        self.assertEqual(priority, 1)

    def test_ai_importance_boost(self):
        """Test that AI analysis can boost priority"""
        news = {'title': 'Unknown token update', 'summary': 'Technical stuff', 'source': 'github'}
        # Initial priority low
        self.assertLess(PriorityCalculator.calculate_priority(news), 5)
        
        # AI says critical
        ai_data = {'importance': 'Critical', 'importance_score': 10}
        priority = PriorityCalculator.calculate_priority(news, ai_data)
        self.assertEqual(priority, 10, "AI Critical with score 10 should boost to 10")

    def test_needs_ai_processing_filtering(self):
        """Test smart filtering for AI processing"""
        # 1. Russian short news -> Skip
        news_ru = {'title': 'Биткоин упал', 'summary': 'Цена снизилась на 1% сегодня утром.', 'source': 'tg'}
        # Assuming length < 300
        self.assertFalse(PriorityCalculator.needs_ai_processing(news_ru), "Should skip short Russian news")

        # 2. Price action only -> Skip
        news_price = {'title': 'BTC Price Update', 'summary': 'Bitcoin is up 2% to $45,000', 'source': 'coingecko'}
        self.assertFalse(PriorityCalculator.needs_ai_processing(news_price), "Should skip price action news")

        # 3. Important news -> Process
        news_impt = {'title': 'SEC Approves Bitcoin ETF', 'summary': 'The regulator has finally given the green light.', 'source': 'coindesk'}
        self.assertTrue(PriorityCalculator.needs_ai_processing(news_impt), "Should process important news")

if __name__ == '__main__':
    unittest.main()
