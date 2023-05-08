import os
import time
import subprocess
import schedule

def run_sickadd():
    watchlist_urls = os.environ.get('WATCHLIST_URLS')
    sickchill_url = os.environ.get('SICKCHILL_URL')
    sickchill_api_key = os.environ.get('SICKCHILL_API_KEY')
    debug_enabled = os.environ.get('DEBUG_ENABLED', 'false').lower() == 'true'
    database_path = os.environ.get('DATABASE_PATH')
    debug_log_path = os.environ.get('DEBUG_LOG_PATH')
    debug_max_size_mb = os.environ.get('DEBUG_MAX_SIZE_MB')

    cmd = f"python SickAdd.py --watchlist_urls {watchlist_urls} --sickchill_url {sickchill_url} --sickchill_api_key {sickchill_api_key}"

    if debug_enabled:
        cmd += " --debug"

    if database_path:
        cmd += f" --database_path {database_path}"

    if debug_log_path:
        cmd += f" --debug_log_path {debug_log_path}"

    if debug_max_size_mb:
        cmd += f" --debug_max_size_mb {debug_max_size_mb}"
        
    print(f"Command to execute: {cmd}")
    proc = subprocess.Popen(cmd, shell=True)

interval = int(os.environ.get('INTERVAL_MINUTES', 1440))
schedule.every(interval).minutes.do(run_sickadd)

# Run SickAdd.py immediately
run_sickadd()

while True:
    schedule.run_pending()
    time.sleep(60)
