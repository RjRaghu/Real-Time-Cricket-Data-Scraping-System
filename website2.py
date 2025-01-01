import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


# Function to scrape match data from the main page
def get_match_data():
    # Set up ChromeDriver path
    webdriver_path = "chromedriver.exe"

    # Set up Chrome service and options
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # Initialize Chrome driver
    driver = webdriver.Chrome(service=service, options=options)

    # Navigate to URL
    url = "https://crex.live/fixtures/match-list"
    driver.get(url)

    try:
        # Wait for page content to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "match-card-container"))
        )

        # Get page content
        page_content = driver.page_source

        # Parse HTML content using BeautifulSoup
        soup = BeautifulSoup(page_content, "html.parser")

        # Extract match data
        matches = soup.find_all(class_="match-card-container")
        live_data = []  # Initialize live match data
        upcoming_data = []  # Initialize upcoming match data

        for match in matches:
            # Check if match has 'liveTag' class
            if match.find(class_="liveTag"):
                # Extract link
                link_tag = match.find("a", href=True)
                if link_tag:
                    href = "https://crex.live" + link_tag["href"]
                else:
                    href = ""

                # Extract team information
                teams = match.find_all("div", class_="team-info")
                if teams:
                    team_name = []
                    team_overs = []
                    team_scores = []
                    for team in teams:
                        # Check each element before .text.strip()
                        name_el = team.find(class_="team-name")
                        over_el = team.find(class_="total-overs")
                        score_el = team.find(class_="team-score")

                        name = name_el.text.strip() if name_el else "N/A"
                        over = over_el.text.strip() if over_el else "N/A"
                        score = score_el.text.strip() if score_el else "N/A"

                        team_name.append(name)
                        team_overs.append(over)
                        team_scores.append(score)

                    # Append to live data
                    live_data.append(
                        {
                            "live": 1,
                            "name": team_name,
                            "over": team_overs,
                            "scores": team_scores,
                            "link": href,
                        }
                    )

            # Check if match has 'not-started' class
            elif match.find(class_="not-started"):
                # Extract link
                link_tag = match.find("a", href=True)
                if link_tag:
                    href = "https://crex.live" + link_tag["href"]
                else:
                    href = ""

                # Extract team and match information
                teams = match.find_all("div", class_="team-info")

                time_start_el = match.find(class_="start-text")
                match_type_el = match.find(class_="time")

                time_start = time_start_el.text.strip() if time_start_el else "N/A"
                match_type = match_type_el.text.strip() if match_type_el else "N/A"

                if teams:
                    team_name = []
                    for team in teams:
                        name_el = team.find(class_="team-name")
                        name = name_el.text.strip() if name_el else "N/A"
                        team_name.append(name)

                    # Append to upcoming data
                    upcoming_data.append(
                        {
                            "time_start": time_start,
                            "type": match_type,
                            "name": team_name,
                            "link": href,
                        }
                    )

    finally:
        # Close Chrome driver
        driver.quit()

    return live_data, upcoming_data


# Function to scrape and display scorecard data for a specific match
def get_scorecard_data(match_url):
    # Set up ChromeDriver path
    webdriver_path = "chromedriver.exe"

    # Set up Chrome service and options
    service = Service(webdriver_path)
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    # Initialize Chrome driver
    driver = webdriver.Chrome(service=service, options=options)

    # Navigate to the specific match URL
    driver.get(match_url)

    try:
        # Get page content
        page_content = driver.page_source

        # Parse HTML content using BeautifulSoup
        soup = BeautifulSoup(page_content, "html.parser")

        # Extract match venue
        match_venue_el = soup.find(class_="match-date match-venue")
        match_venue = match_venue_el.text.strip() if match_venue_el else "N/A"

        # Extract match date
        match_date_el = soup.find(class_="match-date")
        match_date = match_date_el.text.strip() if match_date_el else "N/A"

        # Extract teams' names
        teams_name = []
        teams = soup.find_all(class_="form-team-name")
        for team in teams:
            if team:
                teams_name.append(team.text.strip())
            else:
                teams_name.append("N/A")

        # Extract head-to-head data
        head_to_head = []
        team1_wins_el = soup.find(class_="team1-wins")
        team2_wins_el = soup.find(class_="team2-wins")
        head_to_head.append(team1_wins_el.text if team1_wins_el else "N/A")
        head_to_head.append(team2_wins_el.text if team2_wins_el else "N/A")

        # Extract match results
        match_result = []
        matches = soup.find_all(class_="global-match-card gmc-without-logo")
        for m in matches:
            match_result.append(m.text.strip() if m else "N/A")

        # Extract match table (scorecard data)
        table_el = soup.find(class_="table table-borderless colHeader")
        table = table_el.text.strip() if table_el else "N/A"

        # Extract venue details (weather, etc.)
        venue_details_el = soup.find(class_="align-center weather-wrap")
        venue_details = venue_details_el.text.strip() if venue_details_el else "N/A"

        # Extract venue statistics
        venue_stats_el = soup.find(class_="venue-left-wrapper")
        venue_stats = venue_stats_el.text.strip() if venue_stats_el else "N/A"

        # Extract pace vs spin data on the venue
        pace_vs_spin_on_venue_el = soup.find(class_="venue-pace-wrap")
        pace_vs_spin_on_venue = (
            pace_vs_spin_on_venue_el.text.strip() if pace_vs_spin_on_venue_el else "N/A"
        )

        # Compile all the extracted data into a dictionary or return as needed
        scorecard_data = {
            "match_venue": match_venue,
            "match_date": match_date,
            "teams_name": teams_name,
            "head_to_head": head_to_head,
            "match_result": match_result,
            "scorecard_table": table,
            "venue_details": venue_details,
            "venue_stats": venue_stats,
            "pace_vs_spin_on_venue": pace_vs_spin_on_venue,
        }

        return scorecard_data
    finally:
        # Close Chrome driver
        driver.quit()


# Streamlit app
def main():
    st.title("Cricket Match Information")

    # Get match data
    live_data, upcoming_data = get_match_data()

    # Display Live Matches
    if live_data:
        st.write("### Live Matches")
        for i, match in enumerate(live_data):
            st.write(f"Teams: {', '.join(match['name'])}")
            st.write(f"Scores: {', '.join(match['scores'])}")
            st.write(f"Overs: {', '.join(match['over'])}")

            # Unique key to avoid duplication
            button_key = f"scorecard_live_{i}"
            if st.button(
                f"View Scorecard for {', '.join(match['name'])}", key=button_key
            ):
                scorecard = get_scorecard_data(match["link"])
                st.write(f"Scorecard for {', '.join(match['name'])}:")
                st.text(scorecard)
                st.write("------")
    else:
        st.write("No live matches found.")

    # Display Upcoming Matches
    if upcoming_data:
        st.write("### Upcoming Matches")
        for i, match in enumerate(upcoming_data):
            st.write(f"Teams: {', '.join(match['name'])}")
            st.write(f"Match Type: {match['type']}")
            st.write(f"Start Time: {match['time_start']}")

            # Unique key for each upcoming match button
            button_key = f"scorecard_upcoming_{i}"
            if st.button(
                f"View Scorecard for {', '.join(match['name'])}", key=button_key
            ):
                scorecard = get_scorecard_data(match["link"])
                st.write(f"Scorecard for {', '.join(match['name'])}:")
                st.text(scorecard)
                st.write("------")


# Run the Streamlit app
if __name__ == "__main__":
    main()
