from textblob import TextBlob
from dataclasses import dataclass
from typing import List, Dict
import datetime as dt


@dataclass
class NewsItem:
    date: dt.date
    title: str
    source: str = "dummy"


def dummy_news_fetch(ticker: str) -> List[NewsItem]:
    # Placeholder: in real life, call NewsAPI or similar
    today = dt.date.today()
    return [
        NewsItem(date=today, title=f"{ticker} sees strong demand in key markets"),
        NewsItem(date=today, title=f"Analysts remain cautious on {ticker} valuation"),
    ]


def compute_sentiment_for_ticker(ticker: str) -> Dict:
    news_items = dummy_news_fetch(ticker)
    scores = []
    for item in news_items:
        polarity = TextBlob(item.title).sentiment.polarity
        scores.append(
            {
                "date": item.date.isoformat(),
                "title": item.title,
                "polarity": polarity,
                "source": item.source,
            }
        )
    avg_polarity = sum(s["polarity"] for s in scores) / len(scores) if scores else 0.0
    return {"ticker": ticker, "avg_polarity": avg_polarity, "items": scores}
