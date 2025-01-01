import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
from datetime import datetime
import pytz
from pymongo import MongoClient


# ----------------------------------------------------------------------
# 1) SCRAPE MAIN FIXTURE LIST (live, upcoming, concluded)
# ----------------------------------------------------------------------
def get_match_data():
    """
    Scrapes the main fixture list page (https://crex.live/fixtures/match-list).
    Returns three lists:
      - live_data: Info about currently live matches
      - upcoming_data: Info about future matches
      - concluded_data: Info about recently finished matches
    """
    webdriver_path = "chromedriver.exe"
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    url = "https://crex.live/fixtures/match-list"
    driver.get(url)

    live_data = []
    upcoming_data = []
    concluded_data = []

    try:
        # Wait up to 10 seconds for the match cards
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "match-card-container"))
        )

        # Parse the page
        soup = BeautifulSoup(driver.page_source, "html.parser")
        matches = soup.find_all(class_="match-card-container")

        for match in matches:
            # 1) Check if match is LIVE
            if match.find(class_="liveTag"):
                link_tag = match.find("a", href=True)
                href = "https://crex.live" + link_tag["href"] if link_tag else ""

                # Extract team info
                teams_div = match.find_all("div", class_="team-info")
                team_name = []
                team_overs = []
                team_scores = []

                for t_div in teams_div:
                    name_el = t_div.find(class_="team-name")
                    over_el = t_div.find(class_="total-overs")
                    score_el = t_div.find(class_="team-score")

                    name = name_el.text.strip() if name_el else "N/A"
                    over = over_el.text.strip() if over_el else "Yet to bat"
                    score = score_el.text.strip() if score_el else "N/A"

                    team_name.append(name)
                    team_overs.append(over)
                    team_scores.append(score)

                live_data.append(
                    {
                        "status": "Live",
                        "name": team_name,
                        "over": team_overs,
                        "scores": team_scores,
                        "link": href,
                    }
                )

            # 2) Check if match is UPCOMING
            elif match.find(class_="not-started"):
                link_tag = match.find("a", href=True)
                href = "https://crex.live" + link_tag["href"] if link_tag else ""

                time_start_el = match.find(class_="start-text")
                match_type_el = match.find(class_="time")

                time_start = time_start_el.text.strip() if time_start_el else "N/A"
                match_type = match_type_el.text.strip() if match_type_el else "N/A"

                teams_div = match.find_all("div", class_="team-info")
                team_name = []
                for t_div in teams_div:
                    name_el = t_div.find(class_="team-name")
                    team_name.append(name_el.text.strip() if name_el else "N/A")

                upcoming_data.append(
                    {
                        "status": "Upcoming",
                        "time_start": time_start,
                        "type": match_type,
                        "name": team_name,
                        "link": href,
                    }
                )

            # 3) Otherwise, consider it CONCLUDED if there's a .result block
            else:
                result_div = match.find(class_="result")
                if result_div:
                    link_tag = match.find("a", href=True)
                    href = "https://crex.live" + link_tag["href"] if link_tag else ""

                    # Winner info in the .result <span>
                    winner_span = result_div.find("span")
                    winner_text = winner_span.text.strip() if winner_span else "N/A"

                    # Reason or match info (like "4th T20, BPL 2024-25")
                    reason_span = result_div.find("span", class_="reason")
                    reason_text = reason_span.text.strip() if reason_span else "N/A"

                    # Extract final scores from both teams
                    teams_div = match.find_all("div", class_="team-info")
                    team_names = []
                    team_scores = []
                    team_overs = []

                    for t_div in teams_div:
                        name_el = t_div.find(class_="team-name")
                        score_el = t_div.find(class_="team-score")
                        over_el = t_div.find(class_="total-overs")

                        name = name_el.text.strip() if name_el else "N/A"
                        score = score_el.text.strip() if score_el else "N/A"
                        overs = over_el.text.strip() if over_el else "N/A"

                        team_names.append(name)
                        team_scores.append(score)
                        team_overs.append(overs)

                    concluded_data.append(
                        {
                            "status": "Concluded",
                            "winner": winner_text,
                            "reason": reason_text,
                            "teams": team_names,
                            "scores": team_scores,
                            "overs": team_overs,
                            "link": href,
                        }
                    )
                else:
                    # If you want to handle any other edge case, do it here
                    pass

    finally:
        driver.quit()

    return live_data, upcoming_data, concluded_data


# ----------------------------------------------------------------------
# 2) SCRAPE “MATCH INFO” TAB => /info
# ----------------------------------------------------------------------
def scrape_match_info(info_url):
    """
    Scrapes data from the "Match Info" tab at (match_url + "/info").
    Typically includes toss, venue, series, date, etc.
    """
    webdriver_path = "chromedriver.exe"
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    driver.get(info_url)

    try:
        # Attempt to wait for .match-info-card
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "match-info-card"))
            )
        except TimeoutException:
            # Possibly an upcoming match or different layout
            # We'll still parse whatever is in the page:
            pass

        # We can also do a short sleep to ensure any dynamic content has loaded
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        match_venue_el = soup.find(class_="match-date match-venue")
        match_venue = match_venue_el.text.strip() if match_venue_el else "N/A"

        match_date_el = soup.find(class_="match-info-date") or soup.find(
            "div", class_="match-date"
        )
        match_date = match_date_el.text.strip() if match_date_el else "N/A"

        teams_name = []
        teams_el = soup.find_all(class_="form-team-name")
        for team_el in teams_el:
            teams_name.append(team_el.get_text(strip=True) if team_el else "N/A")

        series_name_el = soup.find(class_="s-name")
        series_name = series_name_el.text.strip() if series_name_el else "N/A"

        toss_el = soup.find(class_="toss-wrap")
        if toss_el:
            toss_p = toss_el.find("p")
            toss_info = toss_p.get_text(strip=True) if toss_p else "N/A"
        else:
            toss_info = "N/A"

        head_to_head = []
        team1_wins_el = soup.find(class_="team1-wins")
        team2_wins_el = soup.find(class_="team2-wins")
        head_to_head.append(team1_wins_el.text if team1_wins_el else "N/A")
        head_to_head.append(team2_wins_el.text if team2_wins_el else "N/A")

        match_result = []
        matches = soup.find_all(class_="global-match-card gmc-without-logo")
        for m in matches:
            match_result.append(m.text.strip() if m else "N/A")

        table_el = soup.find(class_="table table-borderless colHeader")
        table = table_el.text.strip() if table_el else "N/A"

        venue_details_el = soup.find(class_="align-center weather-wrap")
        venue_details = venue_details_el.text.strip() if venue_details_el else "N/A"

        venue_stats_el = soup.find(class_="venue-left-wrapper")
        venue_stats = venue_stats_el.text.strip() if venue_stats_el else "N/A"

        pace_vs_spin_on_venue_el = soup.find(class_="venue-pace-wrap")
        pace_vs_spin_on_venue = (
            pace_vs_spin_on_venue_el.text.strip() if pace_vs_spin_on_venue_el else "N/A"
        )

        match_info_data = {
            "match_venue": match_venue,
            "match_date": match_date,
            "teams_name": teams_name,
            "series_name": series_name,
            "toss_info": toss_info,
            "head_to_head": head_to_head,
            "match_result": match_result,
            "scorecard_table": table,
            "venue_details": venue_details,
            "venue_stats": venue_stats,
            "pace_vs_spin_on_venue": pace_vs_spin_on_venue,
        }

        return match_info_data

    except TimeoutException:
        # If even the body didn't load in time
        return {"Error": "Match Info page did not load in time."}

    finally:
        driver.quit()


# ----------------------------------------------------------------------
# 3) SCRAPE “LIVE” TAB => /live
# ----------------------------------------------------------------------


def scrape_live_data(live_url, match_info=None):
    """
    Scrapes data from the "Live" tab for the given match URL.
    Uses the HTML structure from your snippet, extracting:
      - Currently batting players (runs, balls, 4s, 6s, SR, on_strike)
      - Current bowler (figures, overs, economy)
      - Over-by-over timeline
      - (Optional) Win probability
    """
    webdriver_path = "chromedriver.exe"
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    driver.get(live_url)

    try:
        # First, try waiting for the main container .container.live-screen-wrap
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".container.live-screen-wrap")
                )
            )
        except TimeoutException:
            # If that fails, fallback to .live-container-wrapper
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CLASS_NAME, "live-container-wrapper")
                )
            )

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Prepare output structure
        live_data = {
            "batsmen": [],
            "bowler": {},
            "overs_timeline": [],
            "win_probability": "N/A",  # default if not found
        }

        # ----------------------------------------------------------------------
        # 1) Parse Currently Batting (and Bowler)
        # ----------------------------------------------------------------------
        playing_batsmen_wrapper = soup.find("div", class_="playing-batsmen-wrapper")
        if playing_batsmen_wrapper:
            partnership_divs = playing_batsmen_wrapper.find_all(
                "div", class_="batsmen-partnership"
            )

            def parse_batsman_block(div):
                """
                Distinguish between a batsman block vs a bowler block
                based on whether we find `class="batsmen-score bowler"`
                or not.
                """
                # Check if it's the bowler block
                bowler_info = div.find("div", class_="batsmen-score bowler")
                if bowler_info:
                    # BOWLER section
                    name_el = div.find("div", class_="batsmen-name")
                    bowler_name = name_el.get_text(strip=True) if name_el else "N/A"

                    # Usually <p>1-35</p><p>(2.0)</p>
                    p_tags = bowler_info.find_all("p")
                    figures = (
                        p_tags[0].get_text(strip=True) if len(p_tags) > 0 else "N/A"
                    )
                    overs = p_tags[1].get_text(strip=True) if len(p_tags) > 1 else "N/A"

                    # Find economy
                    econ_el = div.find("div", class_="player-strike-wrapper")
                    economy = "N/A"
                    if econ_el:
                        # Look for <span>Econ:</span><span>17.50</span>
                        econ_span = econ_el.find(
                            "span", text=lambda t: t and "Econ:" in t
                        )
                        if econ_span:
                            parent_div = econ_span.find_parent(
                                "div", class_="strike-rate"
                            )
                            if parent_div:
                                econ_vals = parent_div.find_all("span")
                                # e.g. [" Econ: ", " 17.50 "]
                                if len(econ_vals) >= 2:
                                    economy = econ_vals[1].get_text(strip=True)

                    return {
                        "name": bowler_name,
                        "figures": figures,  # e.g. "1-35"
                        "overs": overs,  # e.g. "(2.0)"
                        "economy": economy,  # e.g. "17.50"
                    }
                else:
                    # BATSMAN section
                    name_el = div.find("div", class_="batsmen-name")
                    name_p = name_el.find("p") if name_el else None
                    batter_name = name_p.get_text(strip=True) if name_p else "N/A"

                    score_el = div.find("div", class_="batsmen-score")
                    if score_el:
                        p_tags = score_el.find_all("p")
                        runs = (
                            p_tags[0].get_text(strip=True) if len(p_tags) > 0 else "0"
                        )
                        balls_raw = (
                            p_tags[1].get_text(strip=True) if len(p_tags) > 1 else "(0)"
                        )
                        balls = balls_raw.strip("()")

                        # Is there a circle-strike-icon => on strike
                        on_strike_icon = score_el.find(
                            "div", class_="circle-strike-icon"
                        )
                        on_strike = True if on_strike_icon else False
                    else:
                        runs, balls, on_strike = "0", "0", False

                    # Now parse 4s, 6s, SR
                    wrapper_el = div.find("div", class_="player-strike-wrapper")
                    fours, sixes, sr = "0", "0", "N/A"
                    if wrapper_el:
                        strike_rate_divs = wrapper_el.find_all(
                            "div", class_="strike-rate"
                        )
                        for sdiv in strike_rate_divs:
                            txt = sdiv.get_text(strip=True)
                            # e.g. "4s: 2", "6s: 2", "SR: 300.00"
                            if txt.lower().startswith("4s:"):
                                _, val = txt.split(":")
                                fours = val.strip()
                            elif txt.lower().startswith("6s:"):
                                _, val = txt.split(":")
                                sixes = val.strip()
                            elif txt.lower().startswith("sr:"):
                                _, val = txt.split(":")
                                sr = val.strip()

                    return {
                        "name": batter_name,
                        "runs": runs,
                        "balls": balls,
                        "fours": fours,
                        "sixes": sixes,
                        "sr": sr,
                        "on_strike": on_strike,
                    }

            batsmen_parsed = []
            bowler_parsed = {}

            for partnership_div in partnership_divs:
                parsed_block = parse_batsman_block(partnership_div)
                if "figures" in parsed_block:  # means it's the bowler
                    bowler_parsed = parsed_block
                else:
                    batsmen_parsed.append(parsed_block)

            live_data["batsmen"] = batsmen_parsed
            live_data["bowler"] = bowler_parsed

        # ----------------------------------------------------------------------
        # 2) Parse the overs timeline
        # ----------------------------------------------------------------------
        overs_timeline_div = soup.find("div", class_="overs-timeline")
        if overs_timeline_div:
            slides = overs_timeline_div.find_all("div", class_="overs-slide")
            overs_list = []
            for slide in slides:
                content_div = slide.find("div", class_="content")
                if not content_div:
                    continue

                over_span = content_div.find("span")
                over_title = over_span.get_text(strip=True) if over_span else "N/A"

                # Gather each .over-ball
                ball_divs = content_div.find_all(
                    "div", class_=lambda c: c and "over-ball" in c
                )
                balls = []
                for bd in ball_divs:
                    txt = bd.get_text(strip=True)
                    # skip if it starts with '=' (the total)
                    if txt.startswith("="):
                        continue
                    balls.append(txt)

                total_div = content_div.find("div", class_="total")
                over_total_txt = total_div.get_text(strip=True) if total_div else ""
                over_total = (
                    over_total_txt.replace("=", "").strip() if over_total_txt else "N/A"
                )

                overs_list.append(
                    {
                        "over_title": over_title,
                        "balls": balls,
                        "total": over_total,
                    }
                )
            live_data["overs_timeline"] = overs_list

        # ----------------------------------------------------------------------
        # 3) (Optional) Parse Win Probability
        # ----------------------------------------------------------------------
        # If your site displays a progressBar or percentage bars, handle it here
        prob_container = soup.find("div", class_="progressBarContainer")
        if prob_container:
            # Example logic if you see teamNameScreenText => team names
            # and percentageScreenText => "84%", "16%"
            # This code is illustrative; adjust to your actual markup if different
            team_names = prob_container.find_all("div", class_="teamNameScreenText")
            percents = prob_container.find_all("div", class_="percentageScreenText")
            if len(team_names) >= 2 and len(percents) >= 2:
                team1_name = team_names[0].get_text(strip=True)
                team2_name = team_names[1].get_text(strip=True)
                team1_pct = percents[0].get_text(strip=True).replace("%", "")
                team2_pct = percents[1].get_text(strip=True).replace("%", "")

                live_data["win_probability"] = {
                    team1_name: team1_pct,
                    team2_name: team2_pct,
                }

        return live_data

    except TimeoutException:
        print("Timeout: Could not find live container on the page.")
        return {"live_data": "N/A"}

    finally:
        driver.quit()


# ----------------------------------------------------------------------
# 4) SCRAPE “SCORECARD” TAB => /scorecard
# ----------------------------------------------------------------------
def scrape_partnerships(soup):
    """
    Extract the Partnerships section from the scorecard page.
    Returns a list of dictionaries containing partnership data.
    """
    partnerships_data = []

    # Locate the partnerships section by class
    partnership_section = soup.find("div", class_="partnership-section")
    if not partnership_section:
        # print("Partnerships section not found.")
        return partnerships_data

    # Parse each partnership block
    partnership_blocks = partnership_section.find_all("div", class_="p-section-wrapper")
    for block in partnership_blocks:
        # Extract wicket information
        wicket_info = block.find("div", class_="p-wckt-info")
        wicket = wicket_info.text.strip() if wicket_info else "N/A"

        # Extract partnership details
        partnership_info = block.find("div", class_="p-info-wrapper")
        if not partnership_info:
            continue

        data_points = partnership_info.find_all("div", class_="p-data")
        if len(data_points) >= 3:
            batter1 = data_points[0].find("p").text.strip()
            batter1_stats = (
                data_points[0].find("span", class_="run-highlight").text.strip()
            )

            total_runs = data_points[1].find("p", class_="p-runs").text.strip()

            batter2 = data_points[2].find("p").text.strip()
            batter2_stats = (
                data_points[2].find("span", class_="run-highlight").text.strip()
            )

            partnerships_data.append(
                {
                    "wicket": wicket,
                    "batter1": batter1,
                    "batter1_stats": batter1_stats,
                    "total_runs": total_runs,
                    "batter2": batter2,
                    "batter2_stats": batter2_stats,
                }
            )

    return partnerships_data


def scrape_fall_of_wickets(soup):
    """
    Extract the Fall of Wickets section from the scorecard page.
    Returns a list of dictionaries containing fall-of-wickets data.
    """
    fall_of_wickets_data = []

    # Locate the "Fall of Wickets" section by heading
    fall_of_wickets_heading = soup.find("h3", string="FALL OF WICKETS")
    if not fall_of_wickets_heading:
        return fall_of_wickets_data

    # Find the parent container of the "Fall of Wickets" table
    fall_of_wickets_section = fall_of_wickets_heading.find_next(
        "div", class_="card score-card"
    )
    if not fall_of_wickets_section:
        return fall_of_wickets_data

    # Locate the table inside the section
    fall_of_wickets_table = fall_of_wickets_section.find("table", class_="bowler-table")
    if not fall_of_wickets_table:
        return fall_of_wickets_data

    # Parse the table rows
    rows = fall_of_wickets_table.find("tbody").find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 3:
            batsman = cells[0].find("span", class_="player-name")
            batsman_name = batsman.text.strip() if batsman else "N/A"
            score = cells[1].text.strip() if cells[1] else "N/A"
            overs = cells[2].text.strip() if cells[2] else "N/A"

            fall_of_wickets_data.append(
                {
                    "batsman": batsman_name,
                    "score": score,
                    "overs": overs,
                }
            )

    return fall_of_wickets_data


def get_scorecard_data(scorecard_url):
    """
    Scrapes details from the "Scorecard" tab (match_url + "/scorecard").
    Extracts batting, bowling, fall of wickets, partnerships, and
    the 'Yet to bat' section.
    """
    webdriver_path = "chromedriver.exe"
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    driver.get(scorecard_url)

    try:
        # Wait for the scorecard page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "score"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")

        scorecard_data = {
            "batting": [],
            "bowling": [],
            "fall_of_wickets": [],
            "partnerships": [],
            "yet_to_bat": [],  # NEW KEY FOR STORING 'YET TO BAT' PLAYERS
        }

        # ----------------------------------------------------------------
        # 1) SCRAPE BATTING & BOWLING SECTIONS
        # ----------------------------------------------------------------
        table_headings = soup.find_all("div", class_="table-heading")
        for table_heading in table_headings:
            heading_text_el = table_heading.find("h3")
            if not heading_text_el:
                continue
            heading_text = heading_text_el.text.strip().lower()

            # Find the next sibling div containing the score-card
            score_card = table_heading.find_next_sibling(
                "div", class_="card score-card"
            )
            if not score_card:
                continue

            score_table = score_card.find("table", class_="bowler-table")
            if not score_table:
                continue

            rows = score_table.find("tbody").find_all("tr")
            section_data = []

            # Identify batting or bowling by heading text
            if heading_text == "batting":
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 6:
                        section_data.append(
                            {
                                "batter": cells[0]
                                .find("span", class_="player-name")
                                .text.strip(),
                                "runs": cells[1].text.strip(),
                                "balls": cells[2].text.strip(),
                                "fours": cells[3].text.strip(),
                                "sixes": cells[4].text.strip(),
                                "strike_rate": cells[5].text.strip(),
                            }
                        )
                scorecard_data["batting"].append(section_data)

            elif heading_text == "bowling":
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 6:
                        section_data.append(
                            {
                                "bowler": cells[0]
                                .find("span", class_="player-name")
                                .text.strip(),
                                "overs": cells[1].text.strip(),
                                "maidens": cells[2].text.strip(),
                                "runs_conceded": cells[3].text.strip(),
                                "wickets": cells[4].text.strip(),
                                "economy": cells[5].text.strip(),
                            }
                        )
                scorecard_data["bowling"].append(section_data)

        # ----------------------------------------------------------------
        # 2) SCRAPE THE 'YET TO BAT' SECTION
        # ----------------------------------------------------------------
        yet_to_bat_heading = soup.find(
            "h3", text=lambda t: t and "yet to bat" in t.lower()
        )
        if yet_to_bat_heading:
            # Find the next container that holds the 'yet-to-bat' players
            yet_to_bat_wrapper = yet_to_bat_heading.find_next(
                "div", class_="yet-to-bat"
            )
            if yet_to_bat_wrapper:
                # Each player entry seems to be under 'div.custom-width > div.content'
                player_divs = yet_to_bat_wrapper.find_all("div", class_="content")
                for player_div in player_divs:
                    # Extract player name
                    name_div = player_div.find("div", class_="name")
                    player_name = name_div.text.strip() if name_div else "N/A"

                    # Optional: extract batting average (or any other info)
                    # In your snippet, it looks like: <p>Avg: <span>0.00</span></p>
                    avg_p = player_div.find("p")
                    # E.g. "Avg: 0.00" => you can parse the exact text if you prefer
                    # Or just store the entire text in a single field
                    avg_text = "N/A"
                    if avg_p:
                        avg_span = avg_p.find("span")
                        if avg_span:
                            avg_text = avg_span.text.strip() or "N/A"

                    scorecard_data["yet_to_bat"].append(
                        {
                            "name": player_name,
                            "average": avg_text,  # or any other detail
                        }
                    )

        # ----------------------------------------------------------------
        # 3) SCRAPE FALL OF WICKETS
        # ----------------------------------------------------------------
        scorecard_data["fall_of_wickets"] = scrape_fall_of_wickets(soup)

        # ----------------------------------------------------------------
        # 4) SCRAPE PARTNERSHIPS
        # ----------------------------------------------------------------
        scorecard_data["partnerships"] = scrape_partnerships(soup)

        return scorecard_data

    except TimeoutException:
        return {"Error": "Scorecard not available or match not started."}
    finally:
        driver.quit()


# ----------------------------------------------------------------------
# 5) SCRAPE “SQUADS” => /squads (with button clicks)
# ----------------------------------------------------------------------
def scrape_squads_with_clicks(match_url):
    """
    Scrapes the squads via /squads.
    Within .info-right-wrapper there are:
      - Buttons (class 'playingxi-button') for each team.
      - 'playingxi-card' containers for playing XI
      - 'playingxi-card on-bench-wrap' containers for bench
      - Rows with class 'playingxi-card-row', each containing .p-name and .bat-ball-type
    """
    webdriver_path = "chromedriver.exe"
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(service=service, options=options)
    squads_url = match_url
    driver.get(squads_url)

    data = {}

    try:
        # Wait for .info-right-wrapper
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "info-right-wrapper"))
        )

        # Wait for the team buttons
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "playingxi-button"))
        )

        try:
            team_buttons = driver.find_elements(By.CLASS_NAME, "playingxi-button")
        except TimeoutException:
            return {"squads": "N/A"}

        all_teams = []

        # Click each team button to reveal the squads
        for btn in team_buttons:
            team_name = btn.text.strip()

            # Use JavaScript click
            try:
                driver.execute_script("arguments[0].click();", btn)
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", btn)

            # Grab updated DOM
            page_content = driver.page_source
            soup = BeautifulSoup(page_content, "html.parser")

            # Identify containers for playing XI vs bench
            playing_div = soup.find("div", class_="playingxi-card")
            bench_div = soup.find("div", class_="playingxi-card on-bench-wrap")

            playing_players = []
            if playing_div:
                rows = playing_div.find_all("div", class_="playingxi-card-row")
                for row in rows:
                    name_div = row.find("div", class_="p-name")
                    type_div = row.find("div", class_="bat-ball-type")
                    player_name = name_div.get_text(strip=True) if name_div else "N/A"
                    player_type = type_div.get_text(strip=True) if type_div else "N/A"
                    playing_players.append(
                        {
                            "player_name": player_name,
                            "player_type": player_type,
                        }
                    )

            bench_players = []
            if bench_div:
                rows = bench_div.find_all("div", class_="playingxi-card-row")
                for row in rows:
                    name_div = row.find("div", class_="p-name")
                    type_div = row.find("div", class_="bat-ball-type")
                    player_name = name_div.get_text(strip=True) if name_div else "N/A"
                    player_type = type_div.get_text(strip=True) if type_div else "N/A"
                    bench_players.append(
                        {
                            "player_name": player_name,
                            "player_type": player_type,
                        }
                    )

            all_teams.append(
                {
                    "team_name": team_name,
                    "playing_11": playing_players,
                    "on_bench": bench_players,
                }
            )

        data["squads"] = all_teams if all_teams else "N/A"

    finally:
        driver.quit()

    return data


# ----------------------------------------------------------------------
# Example usage (NOT scheduling, just direct calls)
# ----------------------------------------------------------------------
def scrape_all_tabs_for_match(match_dict):
    """
    Build the /info, /squads, /live, /scorecard URLs, scrape each tab,
    and return a structured dictionary with all the data.
    """
    original_url = match_dict["link"]

    # Remove '/live' or '/info' from the end of the URL if present
    if original_url.endswith("/live"):
        base_url = original_url.rsplit("/live", 1)[0]
    elif original_url.endswith("/info"):
        base_url = original_url.rsplit("/info", 1)[0]
    else:
        base_url = original_url

    # Build tab URLs
    info_url = base_url + "/info"
    squads_url = info_url  # or base_url + "/squads" if your site uses that structure
    live_url = base_url + "/live"
    scorecard_url = base_url + "/scorecard"

    # Attempt scraping each tab
    info_data = scrape_match_info(info_url)

    try:
        squads_data = scrape_squads_with_clicks(squads_url)
    except TimeoutException:
        squads_data = "N/A"

    live_data_res = scrape_live_data(live_url, match_info=info_data)
    scorecard_data_res = get_scorecard_data(scorecard_url)

    # Print for clarity in the console
    print("\nMatch:", match_dict.get("name"))
    print("Status:", match_dict.get("status", "Unknown"))
    print("Info:", info_data)
    print("Squads:", squads_data)
    print("Live:", live_data_res)
    print("Scorecard:", scorecard_data_res)
    print("=" * 60)

    # Return structured data
    return {
        "status": match_dict.get("status"),
        "teams": match_dict.get("name"),
        "match_link": match_dict.get("link"),
        "info_data": info_data,
        "squads_data": squads_data,
        "live_data": live_data_res,
        "scorecard_data": scorecard_data_res,
    }


def real_time_scraping_loop(poll_interval=60, db_collection=None):
    """
    Continuously poll the match list by calling get_match_data(),
    detect state changes (live/upcoming -> live),
    and scrape real-time data for ongoing (live) matches.

    Args:
      poll_interval (int): how many seconds to wait between checks of the match list.
      db_collection (pymongo.collection.Collection): If provided, store real-time updates in Mongo.
    """

    tracked_matches = {}

    while True:
        print("\n=== Checking match list by calling get_match_data()... ===")

        # 1) Re-fetch the current list of matches
        live_matches, upcoming_matches, concluded_matches = get_match_data()

        # Show what's live
        print("\n=== LATEST LIVE MATCHES (FROM GET_MATCH_DATA) ===")
        for lm in live_matches:
            print("  ->", lm)

        # 2) Add new live matches
        for m in live_matches:
            link = m["link"]
            if link not in tracked_matches:
                print(f"\nDiscovered new LIVE match => Tracking: {link}")
                tracked_matches[link] = {
                    "status": "Live",
                    "match_dict": m,
                    "last_scraped": None,
                }

        # 2.5) Refresh tracked live matches with the new data
        tracked_links = set(tracked_matches.keys())
        current_live_links = {m["link"] for m in live_matches}
        still_live_links = tracked_links & current_live_links
        for link in still_live_links:
            updated_m = next((x for x in live_matches if x["link"] == link), None)
            if updated_m:
                tracked_matches[link]["match_dict"] = updated_m
                print(f"-> Refreshed match_dict for {link} from get_match_data()")

        # 3) Check upcoming matches => if started, treat as live (pseudo-code)...

        # 4) Remove concluded from tracking
        for m in concluded_matches:
            link = m["link"]
            if link in tracked_matches:
                print(f"Match concluded, removing from tracking: {link}")
                del tracked_matches[link]

        # 5) Re-scrape each tracked live match
        for link, state in list(tracked_matches.items()):
            match_dict = state["match_dict"]
            print(f"\nScraping real-time data for {match_dict['name']} (link={link})")

            # Build live/scorecard URLs
            live_url = link
            if live_url.endswith("/info"):
                live_url = live_url.rsplit("/info", 1)[0] + "/live"
            if live_url.endswith("/scorecard"):
                live_url = live_url.rsplit("/scorecard", 1)[0] + "/live"
            scorecard_url = live_url.rsplit("/live", 1)[0] + "/scorecard"

            # Scrape
            live_data_res = scrape_live_data(live_url)
            scorecard_data_res = get_scorecard_data(scorecard_url)

            # Print
            print("LIVE DATA:", live_data_res)
            print("SCORECARD:", scorecard_data_res)

            # If we have a Mongo collection, insert each real-time doc
            if db_collection:
                live_doc = {
                    "type": "live_update",
                    "match_link": link,
                    "timestamp": datetime.now(),
                    "live_data": live_data_res,
                    "scorecard_data": scorecard_data_res,
                }
                inserted_id = db_collection.insert_one(live_doc).inserted_id
                print(f"[MongoDB] Inserted live update doc _id={inserted_id}")

            tracked_matches[link]["last_scraped"] = datetime.now()

        # 6) Sleep
        print(f"\nSleeping {poll_interval} seconds before next poll...")
        time.sleep(poll_interval)


# ----------------------------------------------------------------------
# MAIN ENTRY POINT
# ----------------------------------------------------------------------
def main():
    """
    1) Connect to MongoDB
    2) Do initial scrape, store in DB
    3) Start the real-time loop
    """
    # ------------------------------------------------------------------
    # A) CONNECT TO MONGODB
    # ------------------------------------------------------------------
    client = MongoClient("mongodb://localhost:27017")  # <--- YOUR MONGODB URI
    db = client["myCricketDB"]  # <--- YOUR DB NAME
    matches_collection = db["matches_data"]  # <--- YOUR COLLECTION NAME

    # ------------------------------------------------------------------
    # B) INITIAL SCRAPE
    # ------------------------------------------------------------------
    print("Performing an initial full scrape of all matches...\n")
    live_matches, upcoming_matches, concluded_matches = get_match_data()

    all_data = {"type": "initial", "live": [], "upcoming": [], "concluded": []}

    for m in live_matches:
        all_data["live"].append(scrape_all_tabs_for_match(m))
    for m in upcoming_matches:
        all_data["upcoming"].append(scrape_all_tabs_for_match(m))
    for m in concluded_matches:
        all_data["concluded"].append(scrape_all_tabs_for_match(m))

    # Optionally save to JSON
    with open("initial_scrape.json", "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    # Insert the entire initial doc into Mongo (or you could store each match individually)
    inserted_id = matches_collection.insert_one(all_data).inserted_id
    print(f"[MongoDB] Inserted initial scrape data with _id={inserted_id}\n")

    # ------------------------------------------------------------------
    # C) START REAL-TIME LOOP
    # ------------------------------------------------------------------
    print("\nStarting real-time loop for live matches...\n")
    # Pass the matches_collection (or a different one) to store real-time updates
    real_time_scraping_loop(poll_interval=60, db_collection=matches_collection)


if __name__ == "__main__":
    main()
