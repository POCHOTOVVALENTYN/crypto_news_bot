import unittest
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.message_builder import AdvancedMessageFormatter

class TestAdvancedMessageFormatter(unittest.TestCase):
    def test_clean_text(self):
        """Test HTML and whitespace cleaning"""
        raw = "<p>  Hello   <b>World</b>  </p>"
        cleaned = AdvancedMessageFormatter.clean_text(raw)
        self.assertEqual(cleaned, "Hello World")

    def test_smart_truncate(self):
        """Test text truncation"""
        text = "Word " * 200
        truncated = AdvancedMessageFormatter.smart_truncate(text, length=50)
        self.assertLessEqual(len(truncated), 53) # 50 + "..."
        self.assertTrue(truncated.endswith("..."))

    def test_format_structure(self):
        """Test message structure"""
        data = AdvancedMessageFormatter.format_professional_news(
            title="Bitcoin Hits 100k",
            summary="It finally happened.",
            source="CoinDesk",
            source_url="http://coindesk.com",
            ai_data={'sentiment': 'Bullish', 'coin': 'BTC'},
            prices={'bitcoin': {'price': 100000, 'change': 5.0}}
        )
        text = data['text']
        
        # Clean text to ignore HTML tags (links, bold, etc)
        cleaned_text = AdvancedMessageFormatter.clean_text(text)
        
        # Check components
        self.assertIn("Bitcoin Hits 100k", cleaned_text)
        self.assertIn("#BTC", cleaned_text) # Coin tag
        self.assertIn("It finally happened", cleaned_text)
        # Note: Sentiment might be translated, verify logic
        self.assertIn("Бычий", cleaned_text) # Sentiment (translated)
        self.assertIn("$100,000", cleaned_text) # Price

if __name__ == '__main__':
    unittest.main()
