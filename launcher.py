import os
import time
import subprocess
import schedule

def run_sickadd():
    watchlist_urls = os.environ.get('WATCHLIST_URLS')
    sickchill_url = os.environ.get('SICKCHILL_URL')
    sickchill_api_key = os.environ.get('SICKCHILL_API_KEY')
    debug_enabled = os.environ.get('DEBUG_ENABLED', 'false').lower() == 'true'

    cmd = f"python SickAdd.py --watchlist_urls {watchlist_urls} --sickchill_url {sickchill_url} --sickchill_api_key {sickchill_api_key}"
    
    if debug_enabled:
        cmd += " --debug"

        # Create the /var directory if it does not exist
        if not os.path.exists("/var"):
            os.makedirs("/var")

        # Create the /var/sickadd.log file if it does not exist
        if not os.path.exists("/var/sickadd.log"):
            with open("/var/sickadd.log", "w") as log_file:
                log_file.write("")

        with open("/var/sickadd.log", "a") as log_file:
            proc = subprocess.Popen(cmd, shell=True, stdout=log_file, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.Popen(cmd, shell=True)

interval = int(os.environ.get('INTERVAL_MINUTES', 1440))
schedule.every(interval).minutes.do(run_sickadd)

# Run SickAdd.py immediately
run_sickadd()

while True:
    schedule.run_pending()
    time.sleep(60)
