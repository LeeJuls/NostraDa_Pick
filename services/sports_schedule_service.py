import requests
from datetime import datetime, timezone, timedelta
from config import config

FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"

# 무료 플랜에서 지원되는 주요 리그 코드
SUPPORTED_COMPETITIONS = [
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
    """
    football-data.org API에서 오늘~hours_ahead 시간 이내 축구 경기 목록을 가져옵니다.
    반환 형식:
      [{"home": "Arsenal", "away": "PSG", "competition": "UEFA Champions League",
        "kickoff_utc": "(UTC+0) 2026-03-13 20:00"}, ...]
    """
    api_key = config.FOOTBALL_DATA_API_KEY
    if not api_key:
        print("⚠️ FOOTBALL_DATA_API_KEY not set. Skipping sports schedule fetch.")
        return []

    now_utc  = datetime.now(timezone.utc)
    date_from = now_utc.strftime('%Y-%m-%d')
    date_to   = (now_utc + timedelta(hours=hours_ahead)).strftime('%Y-%m-%d')

    headers = {"X-Auth-Token": api_key}
    params  = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}

    try:
        resp = requests.get(
            f"{FOOTBALL_DATA_BASE}/matches",
            headers=headers,
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"⚠️ Failed to fetch football matches: {e}")
        return []

    matches = []
    cutoff_utc = now_utc + timedelta(hours=hours_ahead)

    for match in data.get("matches", []):
        # 지원 리그만 필터
        comp_code = match.get("competition", {}).get("code", "")
        if comp_code not in SUPPORTED_COMPETITIONS:
            continue

        # 킥오프 UTC 파싱
        utc_date_str = match.get("utcDate", "")  # "2026-03-13T20:00:00Z"
        try:
            kickoff = datetime.fromisoformat(utc_date_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # 현재 시각 이후 ~ hours_ahead 이내만 포함
        if kickoff <= now_utc or kickoff > cutoff_utc:
            continue

        comp_name = match.get("competition", {}).get("name", comp_code)
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        kickoff_str = kickoff.strftime('(UTC+0) %Y-%m-%d %H:%M')

        matches.append({
            "home": home,
            "away": away,
            "competition": comp_name,
            "kickoff_utc": kickoff_str,
        })

    print(f"⚽ Fetched {len(matches)} upcoming football match(es) within {hours_ahead}h.")
    return matches


def build_match_context(matches: list[dict]) -> str:
    """Gemini 프롬프트에 주입할 경기 목록 텍스트 생성"""
    if not matches:
        return ""
    lines = ["=== TODAY'S FOOTBALL SCHEDULE (verified, UTC+0) ==="]
    for m in matches:
        lines.append(
            f"- {m['home']} vs {m['away']} | {m['competition']} | kick-off {m['kickoff_utc']}"
        )
    lines.append("=== END OF SCHEDULE ===")
    return "\n".join(lines)
