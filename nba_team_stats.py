import os, io, re, time, requests, matplotlib.pyplot as plt
from requests.exceptions import ReadTimeout, RequestException
from nba_api.stats.endpoints import leaguedashteamstats

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_VERSION = "2026-03-11"

TEAM_MAP = {
    'ATL':'Atlanta Hawks','BOS':'Boston Celtics','BKN':'Brooklyn Nets',
    'CHA':'Charlotte Hornets','CHI':'Chicago Bulls','CLE':'Cleveland Cavaliers',
    'DAL':'Dallas Mavericks','DEN':'Denver Nuggets','DET':'Detroit Pistons',
    'GSW':'Golden State Warriors','HOU':'Houston Rockets','IND':'Indiana Pacers',
    'LAC':'LA Clippers','LAL':'Los Angeles Lakers','MEM':'Memphis Grizzlies',
    'MIA':'Miami Heat','MIL':'Milwaukee Bucks','MIN':'Minnesota Timberwolves',
    'NOP':'New Orleans Pelicans','NYK':'New York Knicks','OKC':'Oklahoma City Thunder',
    'ORL':'Orlando Magic','PHI':'Philadelphia 76ers','PHX':'Phoenix Suns',
    'POR':'Portland Trail Blazers','SAC':'Sacramento Kings','SAS':'San Antonio Spurs',
    'TOR':'Toronto Raptors','UTA':'Utah Jazz','WAS':'Washington Wizards'
}

def notion_headers(json_mode=True):
    h = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
    }
    if json_mode:
        h["Content-Type"] = "application/json"
    return h

def extract_page_id(page_url: str) -> str:
    m = re.search(r'([0-9a-fA-F]{32})', page_url)
    if not m:
        raise ValueError("ページURLからpage_idを取得できません")
    raw = m.group(1).lower()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"

def fetch_team_stats(max_retries=3, wait_seconds=5):
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            df = leaguedashteamstats.LeagueDashTeamStats(
                season='2025-26',
                season_type_all_star='Regular Season',
                per_mode_detailed='PerGame',
                measure_type_detailed_defense='Advanced',
                timeout=60
            ).get_data_frames()[0]
            return df
        except (ReadTimeout, RequestException) as e:
            last_error = e
            print(f"NBA.com取得失敗 {attempt}/{max_retries}: {e}")
            if attempt < max_retries:
                time.sleep(wait_seconds)
    raise RuntimeError(f"NBA.com取得に失敗しました: {last_error}")

def make_team_png(team_abbr, df):
    team_name = TEAM_MAP[team_abbr]
    out = df[['TEAM_NAME','W','L','OFF_RATING','DEF_RATING']].copy()
    out['W_RANK'] = out['W'].rank(ascending=False, method='min').astype(int)
    out['L_RANK'] = out['L'].rank(ascending=True, method='min').astype(int)
    out['OFF_RATING_RANK'] = out['OFF_RATING'].rank(ascending=False, method='min').astype(int)
    out['DEF_RATING_RANK'] = out['DEF_RATING'].rank(ascending=True, method='min').astype(int)
    row = out[out['TEAM_NAME'] == team_name].iloc[0]

    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.axis("off")
    lines = [
        f"{team_abbr}  {team_name}",
        f"W: {row['W']}  (Rank {row['W_RANK']})",
        f"L: {row['L']}  (Rank {row['L_RANK']})",
        f"OFF RTG: {row['OFF_RATING']:.1f}  (Rank {row['OFF_RATING_RANK']})",
        f"DEF RTG: {row['DEF_RATING']:.1f}  (Rank {row['DEF_RATING_RANK']})",
    ]
    y = 0.9
    for i, t in enumerate(lines):
        ax.text(0.02, y, t, fontsize=14 if i == 0 else 12, va="top")
        y -= 0.18

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf

def upload_small_file_to_notion(filename, fileobj):
    r1 = requests.post(
        "https://api.notion.com/v1/file_uploads",
        headers=notion_headers(),
        json={"mode": "single_part", "filename": filename, "content_type": "image/png"}
    )
    r1.raise_for_status()
    upload_id = r1.json()["id"]

    r2 = requests.post(
        f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
        },
        files={"file": (filename, fileobj, "image/png")}
    )
    r2.raise_for_status()

    r3 = requests.post(
        f"https://api.notion.com/v1/file_uploads/{upload_id}/complete",
        headers=notion_headers(),
        json={}
    )
    r3.raise_for_status()
    return upload_id

def append_image_block(page_id, file_upload_id, caption):
    payload = {
        "children": [
            {
                "object": "block",
                "type": "image",
                "image": {
                    "type": "file_upload",
                    "file_upload": {"id": file_upload_id},
                    "caption": [{"type": "text", "text": {"content": caption}}]
                }
            }
        ]
    }
    r = requests.patch(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=notion_headers(),
        json=payload
    )
    r.raise_for_status()

def main():
    team1 = input("1つ目の略称: ").upper().strip()
    team2 = input("2つ目の略称: ").upper().strip()
    page_url = input("NotionページURL: ").strip()

    if team1 not in TEAM_MAP or team2 not in TEAM_MAP:
        raise SystemExit("略称エラー")

    page_id = extract_page_id(page_url)
    df = fetch_team_stats()

    for abbr in [team1, team2]:
        png = make_team_png(abbr, df)
        upload_id = upload_small_file_to_notion(f"{abbr}_stats.png", png)
        append_image_block(page_id, upload_id, f"{abbr} team stats")

    print("Notion投稿完了")

if __name__ == "__main__":
    main()
