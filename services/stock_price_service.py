"""
실시간 주가/암호화폐 가격 수집 서비스
yfinance를 통해 주요 종목의 현재가를 가져와 Gemini 프롬프트에 주입.
sports_schedule_service.py 패턴과 동일한 구조.
"""

import yfinance as yf
from datetime import datetime, timezone


# ── 조회할 종목 목록 (70개) ──────────────────────────────────────────────────
WATCH_TICKERS = {
    # 빅테크 / AI
    "NVDA":  "Nvidia (NVDA)",
    "AAPL":  "Apple (AAPL)",
    "MSFT":  "Microsoft (MSFT)",
    "GOOGL": "Alphabet/Google (GOOGL)",
    "AMZN":  "Amazon (AMZN)",
    "META":  "Meta (META)",
    "AMD":   "AMD (AMD)",
    "INTC":  "Intel (INTC)",
    "TSM":   "TSMC (TSM)",
    "ARM":   "Arm Holdings (ARM)",
    "QCOM":  "Qualcomm (QCOM)",
    "MU":    "Micron Technology (MU)",
    "SMCI":  "Super Micro Computer (SMCI)",
    "ASML":  "ASML (ASML)",
    # 클라우드 / 엔터프라이즈
    "CRM":   "Salesforce (CRM)",
    "ORCL":  "Oracle (ORCL)",
    # EV / 모빌리티
    "TSLA":  "Tesla (TSLA)",
    "RIVN":  "Rivian (RIVN)",
    "NIO":   "NIO (NIO)",
    "F":     "Ford (F)",
    "UBER":  "Uber (UBER)",
    "LYFT":  "Lyft (LYFT)",
    "ABNB":  "Airbnb (ABNB)",
    # 금융 / 핀테크
    "JPM":   "JPMorgan Chase (JPM)",
    "GS":    "Goldman Sachs (GS)",
    "BAC":   "Bank of America (BAC)",
    "V":     "Visa (V)",
    "MA":    "Mastercard (MA)",
    "PYPL":  "PayPal (PYPL)",
    "XYZ":   "Block/Square (XYZ)",
    "COIN":  "Coinbase (COIN)",
    "HOOD":  "Robinhood (HOOD)",
    # 미디어 / 엔터
    "NFLX":  "Netflix (NFLX)",
    "DIS":   "Disney (DIS)",
    "SPOT":  "Spotify (SPOT)",
    "SNAP":  "Snap (SNAP)",
    "RBLX":  "Roblox (RBLX)",
    # 방산 / 우주
    "BA":    "Boeing (BA)",
    "LMT":   "Lockheed Martin (LMT)",
    "PLTR":  "Palantir (PLTR)",
    # 에너지
    "XOM":   "ExxonMobil (XOM)",
    "CVX":   "Chevron (CVX)",
    # 리테일
    "WMT":   "Walmart (WMT)",
    "SHOP":  "Shopify (SHOP)",
    # 중국 빅테크
    "BABA":  "Alibaba (BABA)",
    # 밈주식 / 화제주
    "GME":   "GameStop (GME)",
    "AMC":   "AMC Entertainment (AMC)",
    "MSTR":  "MicroStrategy (MSTR)",
    "RDDT":  "Reddit (RDDT)",
    "RKLB":  "Rocket Lab (RKLB)",
    "IONQ":  "IonQ (IONQ)",
    "MARA":  "Marathon Digital (MARA)",
    # 암호화폐
    "BTC-USD":  "Bitcoin (BTC)",
    "ETH-USD":  "Ethereum (ETH)",
    "SOL-USD":  "Solana (SOL)",
    "XRP-USD":  "XRP (XRP)",
    "BNB-USD":  "BNB (BNB)",
    "DOGE-USD": "Dogecoin (DOGE)",
    "ADA-USD":  "Cardano (ADA)",
    "AVAX-USD": "Avalanche (AVAX)",
    "LINK-USD": "Chainlink (LINK)",
    "LTC-USD":  "Litecoin (LTC)",
    "DOT-USD":  "Polkadot (DOT)",
    "SHIB-USD": "Shiba Inu (SHIB)",
    # 원자재 선물
    "GC=F":  "Gold (XAU/USD)",
    "CL=F":  "Crude Oil WTI",
    "SI=F":  "Silver (XAG/USD)",
    "NG=F":  "Natural Gas",
    # 외환
    "EURUSD=X": "EUR/USD",
    "JPY=X":    "USD/JPY",
    "GBPUSD=X": "GBP/USD",
    # 미국 지수
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ Composite",
    "^DJI":  "Dow Jones (DJIA)",
    "^VIX":  "VIX (Volatility Index)",
    # 해외 지수
    "^N225": "Nikkei 225",
    "^FTSE": "FTSE 100",
    "^HSI":  "Hang Seng Index",
}


def fetch_stock_prices() -> list[dict]:
    """
    주요 종목의 현재가를 yfinance로 조회.

    Returns:
        [{"ticker": "NVDA", "label": "Nvidia (NVDA)", "price": 183.5,
          "currency": "USD", "change_pct": -2.3}, ...]
    """
    results = []
    tickers_str = " ".join(WATCH_TICKERS.keys())

    try:
        data = yf.download(
            tickers_str,
            period="1d",
            interval="1m",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
        )
    except Exception as e:
        print(f"⚠️ yfinance bulk download failed: {e}")
        return []

    # previousClose를 위한 Ticker 정보 (배치 조회)
    prev_close_map = {}
    try:
        tickers_obj = yf.Tickers(tickers_str)
        for ticker in WATCH_TICKERS:
            try:
                info = tickers_obj.tickers[ticker].fast_info
                prev = getattr(info, 'previous_close', None)
                if prev:
                    prev_close_map[ticker] = float(prev)
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️ previousClose fetch failed: {e}")

    for ticker, label in WATCH_TICKERS.items():
        try:
            if len(WATCH_TICKERS) == 1:
                df = data
            else:
                df = data[ticker]

            if df is None or df.empty:
                continue

            price = float(df["Close"].dropna().iloc[-1])
            prev = prev_close_map.get(ticker)
            change_pct = round((price - prev) / prev * 100, 2) if prev else 0.0

            results.append({
                "ticker": ticker,
                "label":  label,
                "price":  round(price, 2),
                "currency": "USD",
                "change_pct": change_pct,
            })
        except Exception as e:
            print(f"⚠️ Price fetch failed [{ticker}]: {e}")
            continue

    print(f"📈 Stock prices: {len(results)} ticker(s) fetched.")
    return results


def build_stock_context(prices: list[dict]) -> str:
    """
    Gemini 프롬프트에 주입할 현재 주가 컨텍스트 텍스트 생성.
    sports_schedule_service.build_match_context() 패턴과 동일.
    """
    if not prices:
        return ""

    lines = ["=== CURRENT MARKET PRICES (real-time, use as threshold baseline) ==="]
    lines.append("Use these EXACT prices when setting price thresholds in questions.")
    lines.append("Set thresholds within ±5% of the current price to ensure uncertainty.")
    lines.append("")
    for p in prices:
        lines.append(f"  {p['label']}: ${p['price']:,.2f} USD")
    lines.append("")
    lines.append("=== END OF MARKET PRICES ===")
    return "\n".join(lines)
