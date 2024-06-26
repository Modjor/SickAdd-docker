 #!/usr/bin/env python
#
##################################################################################
### SickAdd V3  - THIS IS AN ALPHA RELEASE
#
# This script downloads your IMDb favorites and adds them to your SickBeard shows
#
# NOTE: This script requires Python to be installed on your system
#
#
# Changelog
# Version 3.2
# - Now stores all IDs from IMDb watchlists with a new show_type db field to differentiate TV shows
# - Dramatically reduces the number of requests to IMDb by ignoring any known IMDb ID
# - Provides a foundation for future movie support.
# - Rewrite the IMDB parser to detect additional shows, such as Mini-Series, and to support various types of IMDB lists.
#
# Version 3.1
# Supports IMDb lists with over 100 items
#
# Version 3.0
# Full rewrite, now supports multiple IMDb watchlists to be monitored, various command-line arguments including browsing &
# deleting items from the SQLite database
###########################################################

# Settings
settings = {
    "watchlist_urls": [
        "https://www.imdb.com/list/ls123456789", "https://www.imdb.com/list/ls987654321"
    ],
    "sickchill_url": "http://sickchill_ip:port",
    "sickchill_api_key": "your_sickchill_api_key",
    "database_path": "",
    "debug_log_path": "",
    "debug": 1,
    "debug_max_size_mb": "20"
}


#########    NO MODIFICATION UNDER THAT LINE
##########################################################
import sys
import argparse
import sqlite3
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os
import html
import time
import re
import gzip

def debug_log(message, level=1, force=False):
    if settings["debug"] >= level or force:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        log_file_path = settings["debug_log_path"]

        # Set a default log file name if the path is empty
        if not log_file_path:
            log_file_path = "sickadd.log"

        # Create the directory if it doesn't exist and if the directory path is not empty
        directory_path = os.path.dirname(log_file_path)
        if directory_path:
            os.makedirs(directory_path, exist_ok=True)

        # Check the log file size and compress it if necessary
        try:
            max_size_bytes = float(settings["debug_max_size_mb"]) * 1024 * 1024
        except (ValueError, TypeError):
            max_size_bytes = None

        if max_size_bytes and os.path.exists(log_file_path) and os.path.getsize(log_file_path) > max_size_bytes:
            backup_file_path = f"sickadd.log_{timestamp}.log"
            with open(log_file_path, "rb") as input_file, gzip.open(backup_file_path + ".gz", "wb") as output_file:
                output_file.writelines(input_file)
            os.remove(log_file_path)
            with open(log_file_path, "w") as log_file:
                log_file.write(log_message + "\n")
        else:
            with open(log_file_path, "a") as log_file:
                log_file.write(log_message + "\n")




# Check if IMDb Watchlists are reachable
def check_watchlists():
    # Create a list to store unreachable watchlists
    unreachable_watchlists = []

    # Create a list to store reachable watchlists
    reachable_watchlists = []

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
    }

    for url in settings["watchlist_urls"]:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            reachable_watchlists.append(url)
        else:
            unreachable_watchlists.append(url)

    # Log unreachable watchlists in debug mode
    if unreachable_watchlists:
        debug_log(f"Unreachable IMDb watchlists: {', '.join(unreachable_watchlists)}")

    # Log reachable watchlists in debug mode
    if reachable_watchlists:
        debug_log(f"Reachable IMDb watchlists: {', '.join(reachable_watchlists)}")

    # Check if the count of reachable watchlists is 0. If so, stop the script.
    if len(reachable_watchlists) == 0:
        print("Error: None of the IMDb watchlists are reachable.")
        sys.exit(1)

    debug_log("IMDb watchlists check completed.")

# Check if SickChill is reachable
def check_sickchill():
    url = f"{settings['sickchill_url']}/api/{settings['sickchill_api_key']}/?cmd=shows"
    try:
        response = requests.get(url)
        response.raise_for_status()
        if not response.json().get("data"):
            debug_log("Error: SickChill API key is incorrect.")
            print("Error: SickChill API key is incorrect.")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        debug_log("Error: SickChill is not reachable.")
        print("Error: SickChill is not reachable. Check your SickChill server IP, Port, and API key.")
        sys.exit(1)
    debug_log("SickChill is reachable.")

# Check if TheTVDB is reachable
def check_thetvdb():
    url = "https://thetvdb.com/api/GetSeriesByRemoteID.php?imdbid=tt0257315"
    debug_log("Testing TheTVDB availability at URL: " + url)
    response = requests.get(url)
    if response.status_code != 200:
        debug_log("Error during TheTVDB availability test at URL: " + url)
        debug_log("Response: " + str(response.status_code) + " - " + response.text)
        print("Error: TheTVDB is not reachable.")
        sys.exit(1)
    else:
        debug_log("TheTVDB is reachable.")

# Create or connect to SQLite database
def setup_database():
    # Check if the database path is specified in the settings
    if "database_path" in settings:
        database_path = settings["database_path"]
    else:
        database_path = os.path.join(os.getcwd(), "sickadd.db")

    # Set a default database file name if the path is empty
    if not database_path:
        database_path = "sickadd.db"

    # Create the directory if it doesn't exist and if the directory path is not empty
    directory_path = os.path.dirname(database_path)
    if directory_path:
        os.makedirs(directory_path, exist_ok=True)

    debug_log(f"Database path: {database_path}")
    conn = sqlite3.connect(database_path)
    debug_log(f"Connected to database at: {conn}")
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shows'")
    table_exists = cur.fetchone()

    if table_exists is None:
        # The "shows" table doesn't exist, create the table with all fields, including "show_type"
        debug_log("Creating the 'shows' table with all fields")
        cur.execute(
            """
            CREATE TABLE shows (
                imdb_id TEXT PRIMARY KEY,
                title TEXT,
                watchlist_url TEXT,
                imdb_import_date TEXT,
                added_to_sickchill INTEGER,
                thetvdb_id INTEGER,
                sc_added_date TEXT,
                show_type INTEGER
            )
            """
        )
        conn.commit()
    else:
        # The "shows" table exists, check if it needs to be upgraded
        upgrade_database(conn, cur)

    return conn, cur
    
########## DB UPGRADE SECTION #######
# Upgrade the database structure if needed
def upgrade_database(conn, cur):
    cur.execute("PRAGMA table_info(shows)")
    columns = cur.fetchall()
    column_names = [column[1] for column in columns]

    # Add the 'show_type' column if it doesn't exist
    if "show_type" not in column_names:
        debug_log("Upgrading the 'shows' table, adding the 'show_type' column")
        cur.execute("ALTER TABLE shows ADD COLUMN show_type INTEGER")
        conn.commit()

        # Set all existing show entries 'show_type' to 1
        cur.execute("UPDATE shows SET show_type = 1")
        conn.commit()
        debug_log("DB Upgrade - Set all existing show show_type to 1 (TV Shows)")



# Retrieve IMDb IDs from a given IMDb watchlist URL
def get_imdb_watchlists(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept-Language": "en-US,en;q=0.5"
    }

    debug_log(f"Fetching watchlist content from URL: {url}")
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        debug_log(f"Request failed for URL: {url}")
        exit()

    imdb_ids = re.findall(r'tt\d{5,8}', response.text)
    imdb_ids = list(set(imdb_ids))
    debug_log(f"URL: {url} - Total IMDb IDs: {len(imdb_ids)}")

    return imdb_ids

# Determine if an IMDb ID corresponds to a TV series or mini-series, and returns the title if it is
def detect_imdb_tv_show(imdb_id, analyzed_items=None):
    if analyzed_items is None:
        analyzed_items = {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept-Language": "en-US,en;q=0.5"
    }

    series_url = f"https://www.imdb.com/title/{imdb_id}/"
    debug_log(f"Fetching series content from URL: {series_url}")
    series_response = requests.get(series_url, headers=headers)

    if series_response.status_code == 200:
        title_search = re.search(r'<title>(.+?)</title>', series_response.text)
        if title_search:
            title = html.unescape(title_search.group(1))
            debug_log(f"ID: {imdb_id} - Title: {title}")
            if "TV Series" in title or "TV Mini Series" in title:
                if imdb_id not in analyzed_items:
                    analyzed_items[imdb_id] = title
                    debug_log(f"ID: {imdb_id} - Title: {title} - Is a TV series")
                    return (True, title)
                else:
                    debug_log(f"ID: {imdb_id} - Title: {title} - Already analyzed")
                    return (False, title)
            else:
                debug_log(f"ID: {imdb_id} - Title: {title} - Is not a TV series")
                return (False, title)
        else:
            debug_log(f"ID: {imdb_id} - Title not found")
            return (False, "")
    else:
        debug_log(f"Request failed for series URL: {series_url}")
        return (False, "")

# Process and analyze IMDb watchlists to retrieve a list of unique TV series and mini-series
def imdb_watchlists_init():
    watchlist_summary = []
    all_series_ids = {}
    unique_series_ids = {}
    unique_unknown_ids = {}

    conn, cur = setup_database()

    # Retrieve IMDb IDs and titles from the 'shows' table with a 'show_type' value of 0 or 1
    cur.execute("SELECT imdb_id, title FROM shows WHERE show_type = 0 OR show_type = 1")
    rows = cur.fetchall()
    existing_ids = {row[0]: row[1] for row in rows}  # Convert to dictionary for faster lookup

    for url in settings["watchlist_urls"]:
        imdb_ids = get_imdb_watchlists(url)
        series_ids = []
        ignored_ids = []

        for imdb_id in imdb_ids:
            if imdb_id in existing_ids:
                debug_log(f"Ignoring. Already in SickAdd database: {imdb_id} - {existing_ids[imdb_id]}")
                continue

            if imdb_id in all_series_ids:
                if all_series_ids[imdb_id] == "TV Series" or all_series_ids[imdb_id] == "TV Mini-Series":
                    series_ids.append(imdb_id)
                else:
                    ignored_ids.append(imdb_id)
            else:
                is_tv_series, title = detect_imdb_tv_show(imdb_id, analyzed_items=all_series_ids)
                if is_tv_series:
                    series_ids.append(imdb_id)
                    all_series_ids[imdb_id] = "TV Series" if "TV Series" in title else "TV Mini-Series" if "TV Mini-Series" in title else "TV Series or Mini-Series"
                    if title is None:
                        title = "Unknown IMDB Title"
                    unique_series_ids[imdb_id] = {"title": title, "watchlist_url": url}
                else:
                    ignored_ids.append(imdb_id)
                    all_series_ids[imdb_id] = "Not a TV Series"
                    if title is None:
                        title = "Unknown IMDB Title"
                    unique_unknown_ids[imdb_id] = {"title": title, "watchlist_url": url}

        watchlist_summary.append({
            "url": url,
            "total_items": len(imdb_ids),
            "series_items": len(series_ids),
            "ignored_items": len(ignored_ids)
        })

    # Convert unique_series_ids and unique_unknown_ids to a list of dictionaries
    series_list = [dict(imdb_id=k, **v) for k, v in unique_series_ids.items()]
    unknown_list = [dict(imdb_id=k, **v) for k, v in unique_unknown_ids.items()]

    # Debug output
    debug_log("\nWatchlist Summary:")
    for summary in watchlist_summary:
        debug_log(f"URL: {summary['url']}")
        debug_log(f"  Total items: {summary['total_items']}")
        debug_log(f"  Series items: {summary['series_items']}")
        debug_log(f"  Ignored items: {summary['ignored_items']}")

        for imdb_id, data in unique_series_ids.items():
            if data["watchlist_url"] == summary["url"]:
                title = data['title'] if data['title'] is not None else "Unknown IMDB Title"
                debug_log(f"  {imdb_id} - {title} (from {data['watchlist_url']})")
            else:
                debug_log(f"  {imdb_id} - Unknown IMDB Title (from {data['watchlist_url']})")

    global_total_items = sum([summary["total_items"] for summary in watchlist_summary])
    global_series_items = sum([summary["series_items"] for summary in watchlist_summary])
    global_ignored_items = sum([summary["ignored_items"] for summary in watchlist_summary])
    global_duplicate_items = global_series_items - len(series_list)
    debug_log("\nGlobal Summary:")
    debug_log(f"  Total items: {global_total_items}")
    debug_log(f"  Series items: {global_series_items}")
    debug_log(f"  Unique series items: {len(series_list)}")
    debug_log(f"  Unique non-series items: {len(unknown_list)}")
    debug_log(f"  Ignored items: {global_ignored_items}")
    debug_log(f"  Duplicate items: {global_duplicate_items}")

    debug_log("")

    # Debug output for series_list
    debug_log("Series to Import into SickAdd:")
    for series in series_list:
        debug_log(f'  IMDb ID: {series["imdb_id"]}, Title: {series["title"]}, Watchlist URL: {series["watchlist_url"]}')

    return series_list, unknown_list
    
# Insert series into SQLite database
def insert_series_to_db(conn, cur, series_list):
    for series in series_list:
        cur.execute("SELECT * FROM shows WHERE imdb_id=?", (series["imdb_id"],))
        if not cur.fetchone():
            # Insert series with show_type set to 1
            cur.execute(
                "INSERT INTO shows (imdb_id, title, watchlist_url, imdb_import_date, added_to_sickchill, show_type) VALUES (?, ?, ?, ?, ?, ?)",
                (series["imdb_id"], series["title"], series["watchlist_url"], datetime.now().strftime("%Y-%m-%d"), 0, 1),
            )
            conn.commit()
            debug_log(f'Series added to the database: {series["title"]} (IMDb ID: {series["imdb_id"]})')

# Insert unknown items into SQLite database
def insert_unique_unknown_ids(conn, cur, unknown_list):
    for unknown in unknown_list:
        cur.execute("SELECT * FROM shows WHERE imdb_id=?", (unknown["imdb_id"],))
        if not cur.fetchone():
            # Insert unknown item with show_type set to 0
            cur.execute(
                "INSERT INTO shows (imdb_id, title, watchlist_url, imdb_import_date, added_to_sickchill, show_type) VALUES (?, ?, ?, ?, ?, ?)",
                (unknown["imdb_id"], unknown["title"], unknown["watchlist_url"], datetime.now().strftime("%Y-%m-%d"), 0, 0),
            )
            conn.commit()
            debug_log(f'Unknown item added to the database: {unknown["title"]} (IMDb ID: {unknown["imdb_id"]})')

# Get TheTVDB ID for series in the database
def get_thetvdb_ids(conn, cur):
    cur.execute("SELECT imdb_id, title FROM shows WHERE thetvdb_id IS NULL AND show_type=1")
    series_without_thetvdb_id = cur.fetchall()
    for imdb_id, title in series_without_thetvdb_id:
        try:
            url = f"https://thetvdb.com/api/GetSeriesByRemoteID.php?imdbid={imdb_id}"
            debug_log(f"URL used to fetch TheTVDB ID for {title} (IMDb ID: {imdb_id}): {url}")
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers)
            debug_log(f"TheTVDB response for {title} (IMDb ID: {imdb_id}): {response.status_code}")
            if response.status_code != 200 or response.content.strip() == b'':
                debug_log(f"Error fetching TheTVDB ID for {title} (IMDb ID: {imdb_id}): {response.status_code}")
                continue
            soup = BeautifulSoup(response.content, "lxml-xml")
            series = soup.find("Series")
            if series is None:
                debug_log(f"No series found for IMDb ID {imdb_id}")
                continue
            tvdb_id = series.find("id").text
            cur.execute("UPDATE shows SET thetvdb_id=? WHERE imdb_id=?", (tvdb_id, imdb_id))
            conn.commit()
            debug_log(f"TheTVDB ID added for {title} (IMDb ID: {imdb_id}, TheTVDB ID: {tvdb_id})")
        except requests.exceptions.RequestException as e:
            debug_log(f"Error fetching TheTVDB ID for {title} (IMDb ID: {imdb_id}): {e}")

# Get the list of TheTVDB IDs of shows already in SickChill
def get_sickchill_shows():
    url = f"{settings['sickchill_url']}/api/{settings['sickchill_api_key']}/?cmd=shows"
    response = requests.get(url)
    shows = response.json()["data"]
    tvdb_ids = [int(show["tvdbid"]) for show in shows.values()]
    return tvdb_ids

# Update added_to_sickchill value in the database
def update_added_to_sickchill(conn, cur, sickchill_tvdb_ids):
    cur.execute("SELECT thetvdb_id FROM shows WHERE added_to_sickchill=0")
    shows_to_check = cur.fetchall()
    for show in shows_to_check:
        if show[0] in sickchill_tvdb_ids:
            cur.execute("UPDATE shows SET added_to_sickchill=1 WHERE thetvdb_id=?", (show[0],))
            conn.commit()
            debug_log(f"Updated added_to_sickchill value for the series (TheTVDB ID: {show[0]})")

# Add series to SickChill
def add_series_to_sickchill(conn, cur):
    # Get shows with null or empty thetvdb_id
    cur.execute("SELECT imdb_id, title FROM shows WHERE added_to_sickchill=0 AND show_type=1 AND (thetvdb_id IS NULL OR thetvdb_id='')")
    shows_with_null_thetvdb_id = cur.fetchall()
    message = f"{len(shows_with_null_thetvdb_id)} TV shows will be skipped due to missing TheTVDB IDs."
    debug_log(message, force=True)
    for show in shows_with_null_thetvdb_id:
        message = f"Missing TheTVDB ID for TV show with IMDB ID: {show[0]} and Title: {show[1]}"
        debug_log(message, force=True)

    # Get shows to add to SickChill
    cur.execute("SELECT thetvdb_id, title FROM shows WHERE added_to_sickchill=0 AND show_type=1 AND thetvdb_id IS NOT NULL AND thetvdb_id<>''")
    shows_to_add = cur.fetchall()
    debug_log(f"{len(shows_to_add)} series to add to SickChill")

    added_to_sickchill = False

    for show in shows_to_add:
        thetvdb_id, title = show
        debug_log(f"Attempting to add series to SickChill (TheTVDB ID: {thetvdb_id}, Title: {title})")
        url = f"{settings['sickchill_url']}/api/{settings['sickchill_api_key']}/?cmd=show.addnew&indexerid={thetvdb_id}"
        debug_log(f"URL called to add the series to SickChill: {url}")
        response = requests.get(url)
        if response.status_code == 200 and response.json()["result"] == "success":
            cur.execute("UPDATE shows SET added_to_sickchill=1, sc_added_date=? WHERE thetvdb_id=?", (datetime.now().strftime("%Y-%m-%d"), thetvdb_id))
            conn.commit()
            debug_log(f"Series added to SickChill (TheTVDB ID: {thetvdb_id}, Title: {title})")
            added_to_sickchill = True
        else:
            debug_log(f"Unable to add series to SickChill (TheTVDB ID: {thetvdb_id}, Title: {title}) - Response code: {response.status_code}")

    if added_to_sickchill:
        debug_log("Import to SickChill is complete. SickAdd will now exit.", force=True)
    else:
        debug_log("No new TV series to import. SickAdd will now exit", force=True)




# Show db content
def show_db_content(cursor):
    # Select records where the Type is Unknown (Not TV Shows)
    cursor.execute("SELECT * FROM shows WHERE show_type = 0")
    type_unknowns = cursor.fetchall()

    # Select records where the Type is TV Show or Mini Series
    cursor.execute("SELECT * FROM shows WHERE show_type = 1")
    type_tv_shows = cursor.fetchall()

    # Select records with incomplete data
    cursor.execute("SELECT * FROM shows WHERE show_type NOT IN (0, 1)")
    incomplete_records = cursor.fetchall()

    # Print table of records where the Type is Unknown (Not TV Shows)
    if type_unknowns:
        print("\n\nUnknown Records (Not TV Shows):")
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            column_names = "|".join(columns)
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
            print(f"| {column_names} |")
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        for row in type_unknowns:
            row_values = "|".join([str(value) for value in row])
            print(f"| {row_values} |")
        if cursor.description:
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        print("\n")

    # Print table of records where the Type is TV Show or Mini Series
    if type_tv_shows:
        print("TV Shows and Mini Series:")
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            column_names = "|".join(columns)
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
            print(f"| {column_names} |")
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        for row in type_tv_shows:
            row_values = "|".join([str(value) for value in row])
            print(f"| {row_values} |")
        if cursor.description:
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        print("\n")

    # Print table of records with incomplete data
    if incomplete_records:
        print("Incomplete Records - try to delete the ID using --delete:")
        if cursor.description:
            columns = [column[0] for column in cursor.description]
            column_names = "|".join(columns)
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
            print(f"| {column_names} |")
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        for row in incomplete_records:
            row_values = "|".join([str(value) for value in row])
            print(f"| {row_values} |")
        if cursor.description:
            print(f"+{'-' * len(column_names.replace('|', ''))}+")
        print("\n")
#############################

# Delete series from SQLite database
def delete_series_from_db(conn, cur, imdb_id):
    cur.execute("SELECT imdb_id FROM shows WHERE imdb_id=?", (imdb_id,))
    result = cur.fetchone()
    if result is None:
        debug_log(f"The series does not exist in the database (IMDb ID: {imdb_id})")
    else:
        cur.execute("DELETE FROM shows WHERE imdb_id=?", (imdb_id,))
        conn.commit()
        debug_log(f"Series removed from the database (IMDb ID: {imdb_id})")

# Initial db check
def check_database():
    conn, cur = setup_database()
    conn.close()


# Main function
def main():
    check_database()
    check_watchlists()
    check_sickchill()
    check_thetvdb()
    conn, cur = setup_database()
    series_list, unknown_list = imdb_watchlists_init()
    insert_series_to_db(conn, cur, series_list)    
    insert_unique_unknown_ids(conn, cur, unknown_list)
    get_thetvdb_ids(conn, cur)
    sickchill_tvdb_ids = get_sickchill_shows()
    update_added_to_sickchill(conn, cur, sickchill_tvdb_ids)
    add_series_to_sickchill(conn, cur)
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add series to SickChill from IMDb watchlists",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )
    parser.add_argument(
        "--delete",
        metavar="IMDb_ID",
        help="Remove a series from the SQLite database using its IMDb ID\n"
             'Example: --delete "tt1234567"'
    )
    parser.add_argument(
        "--showdb",
        action="store_true",
        help="Display all series in the database"
    )
    parser.add_argument(
        "--watchlist_urls",
        nargs="+",
        metavar="URL",
        help='List of IMDb watchlist URLs separated by commas\n'
             'Example: --watchlist_urls "https://www.imdb.com/list/ls00000000,https://www.imdb.com/list/ls123456789"'
    )
    parser.add_argument(
        "--sickchill_url",
        help='SickChill URL (example: http://sickchill_ip:port)\n'
             'Example: --sickchill_url "http://192.168.1.2:8081"'
    )
    parser.add_argument(
        "--sickchill_api_key",
        help="SickChill API key\n"
             'Example: --sickchill_api_key "1a2b3c4d5e6f7g8h"'
    )
    parser.add_argument(
        "--database_path",
        help='Path to the SQLite database file\n'
             'Example: --database_path "/var/sickadd.db"'
    )
    parser.add_argument(
        "--debug_log_path",
        help='Path to the log file when debug mode is enabled\n'
             'Example: --debug_log_path "/var/log/sickadd.log"'
    )
    parser.add_argument(
        "--debug_max_size_mb",
        type=int,
        help="Set the maximum size of the debug log file in megabytes"
    )

    args = parser.parse_args()

    if args.debug:
        settings["debug"] = 1
        debug_log("Debug mode enabled")
        if args.debug_log_path:
            settings["debug_log_path"] = args.debug_log_path

    if args.watchlist_urls:
        watchlist_urls = [url.strip() for url in ",".join(args.watchlist_urls).split(",")]
        settings["watchlist_urls"] = watchlist_urls

    if args.sickchill_url:
        settings["sickchill_url"] = args.sickchill_url

    if args.sickchill_api_key:
        settings["sickchill_api_key"] = args.sickchill_api_key

    if args.database_path:
        settings["database_path"] = args.database_path

    if args.delete:
        conn, cur = setup_database()
        delete_series_from_db(conn, cur, args.delete)
        conn.close()
    elif args.showdb:
        conn, cur = setup_database()
        show_db_content(cur)
        conn.close()
    else:
        main()
