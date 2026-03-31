def get_news_snapshot(hours_back=12, limit=5):
    return {
        "headlines": [],
        "summary_terms": [],
        "bias_summary": {
            "bias": "neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
        },
    }
