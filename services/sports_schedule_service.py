import requests
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta
from config import config


def _build_search_url(home: str, away: str, competition: str) -> str:
    """Google 검색 URL 생성 (팀명 + 대회명)"""
    query = f"{home} vs {away} {competition}"
    return f"https://www.google.com/search?q={quote_plus(query)}"

# ── football-data.org (Soccer) ─────────────────────────────────────────────
FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

SUPPORTED_SOCCER_COMPETITIONS = [
    "CL",   # UEFA Champions League
    "EL",   # UEFA Europa League
    "PL",   # Premier League
    "PD",   # La Liga
    "BL1",  # Bundesliga
    "SA",   # Serie A
    "FL1",  # Ligue 1
    "DED",  # Eredivisie
    "PPL",  # Primeira Liga
]

def get_today_football_matches(hours_ahead: int = 48) -> list[dict]:
    """football-data.org: 오늘~hours_ahead 이내 축구 경기 목록"""
    api_key = config.FOOTBALL_DATA_API_KEY
    if not api_key:
        print("⚠️ FOOTBALL_DATA_API_KEY not set. Skipping.")
        return []

    now_utc   = datetime.now(timezone.utc)
    cutoff    = now_utc + timedelta(hours=hours_ahead)
    date_from = now_utc.strftime('%Y-%m-%d')
    date_to   = cutoff.strftime('%Y-%m-%d')

    try:
        resp = requests.get(
            f"{FOOTBALL_DATA_BASE}/matches",
            headers={"X-Auth-Token": api_key},
            params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"⚠️ Football fetch failed: {e}")
        return []

    matches = []
    for match in data.get("matches", []):
        comp_code = match.get("competition", {}).get("code", "")
        if comp_code not in SUPPORTED_SOCCER_COMPETITIONS:
            continue
        try:
            kickoff = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
        except Exception:
            continue
        if kickoff <= now_utc or kickoff > cutoff:
            continue

        home_name = match["homeTeam"]["name"]
        away_name = match["awayTeam"]["name"]
        comp_name = match.get("competition", {}).get("name", comp_code)
        matches.append({
            "sport": "Soccer",
            "home": home_name,
            "away": away_name,
            "competition": comp_name,
            "kickoff_utc": kickoff.strftime('(UTC+0) %Y-%m-%d %H:%M'),
            "search_url": _build_search_url(home_name, away_name, comp_name),
        })

    print(f"⚽ Soccer: {len(matches)} match(es) within {hours_ahead}h.")
    return matches


# ── api-sports.io (NBA / MLB) ──────────────────────────────────────────────
API_SPORTS_HEADERS_KEY = "x-apisports-key"

def _fetch_api_sports(sport: str, endpoint: str, params: dict) -> dict:
    """api-sports.io 공통 호출 헬퍼"""
    key = config.API_SPORTS_KEY
    if not key:
        return {}
    try:
        url = f"https://v1.{sport}.api-sports.io/{endpoint}"
        resp = requests.get(
            url,
            headers={API_SPORTS_HEADERS_KEY: key},
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"⚠️ api-sports.io [{sport}] fetch failed: {e}")
        return {}


def get_today_nba_games(hours_ahead: int = 48) -> list[dict]:
    """api-sports.io: 오늘~hours_ahead 이내 NBA 경기 목록"""
    now_utc  = datetime.now(timezone.utc)
    cutoff   = now_utc + timedelta(hours=hours_ahead)
    # NBA 시즌: 2025-2026 → season=2025
    season   = str(now_utc.year - 1) if now_utc.month < 7 else str(now_utc.year)
    games    = []

    # 오늘 ~ date_to 날짜 순회
    check_dates = set()
    check_dates.add(now_utc.strftime('%Y-%m-%d'))
    check_dates.add(cutoff.strftime('%Y-%m-%d'))

    for date_str in sorted(check_dates):
        data = _fetch_api_sports("basketball", "games", {
            "date": date_str, "league": 12, "season": season  # 12 = NBA
        })
        for game in data.get("response", []):
            try:
                start_str = game["date"]  # "2026-03-13T00:00:00+00:00"
                kickoff   = datetime.fromisoformat(start_str)
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if kickoff <= now_utc or kickoff > cutoff:
                continue
            home = game["teams"]["home"]["name"]
            away = game["teams"]["visitors"]["name"]
            games.append({
                "sport": "NBA",
                "home": home,
                "away": away,
                "competition": "NBA",
                "kickoff_utc": kickoff.strftime('(UTC+0) %Y-%m-%d %H:%M'),
                "search_url": _build_search_url(home, away, "NBA"),
            })

    print(f"🏀 NBA: {len(games)} game(s) within {hours_ahead}h.")
    return games


def get_today_mlb_games(hours_ahead: int = 48) -> list[dict]:
    """api-sports.io: 오늘~hours_ahead 이내 MLB 경기 목록"""
    now_utc = datetime.now(timezone.utc)
    cutoff  = now_utc + timedelta(hours=hours_ahead)
    season  = str(now_utc.year)
    games   = []

    check_dates = set()
    check_dates.add(now_utc.strftime('%Y-%m-%d'))
    check_dates.add(cutoff.strftime('%Y-%m-%d'))

    for date_str in sorted(check_dates):
        data = _fetch_api_sports("baseball", "games", {
            "date": date_str, "league": 1, "season": season  # 1 = MLB
        })
        for game in data.get("response", []):
            try:
                start_str = game["date"]
                kickoff   = datetime.fromisoformat(start_str)
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if kickoff <= now_utc or kickoff > cutoff:
                continue
            home = game["teams"]["home"]["name"]
            away = game["teams"]["away"]["name"]
            games.append({
                "sport": "MLB",
                "home": home,
                "away": away,
                "competition": "MLB",
                "kickoff_utc": kickoff.strftime('(UTC+0) %Y-%m-%d %H:%M'),
                "search_url": _build_search_url(home, away, "MLB"),
            })

    print(f"⚾ MLB: {len(games)} game(s) within {hours_ahead}h.")
    return games


# ── 통합 ───────────────────────────────────────────────────────────────────
def get_all_sports_matches(hours_ahead: int = 48) -> list[dict]:
    """축구 + NBA + MLB 경기 목록 통합 반환"""
    all_matches = []
    all_matches.extend(get_today_football_matches(hours_ahead))
    all_matches.extend(get_today_nba_games(hours_ahead))
    all_matches.extend(get_today_mlb_games(hours_ahead))
    return all_matches


def build_match_context(matches: list[dict]) -> str:
    """Gemini 프롬프트에 주입할 경기 목록 텍스트 생성"""
    if not matches:
        return ""
    lines = ["=== TODAY'S SPORTS SCHEDULE (verified real data, UTC+0) ==="]
    for m in matches:
        lines.append(
            f"- [{m['sport']}] {m['home']} vs {m['away']}"
            f" | {m['competition']} | kick-off {m['kickoff_utc']}"
            f" | search: {m.get('search_url', '')}"
        )
    lines.append("=== END OF SCHEDULE ===")
    return "\n".join(lines)
