#!/usr/bin/env python3
import logging
import os
import shlex
import signal
import time
from typing import List, Dict, Any, Optional

import docker
import docker.errors
import requests
from docker.models.containers import Container


log_level_str = str(os.environ.get("LOG_LEVEL", "INFO")).upper().strip()
match log_level_str:
    case "DEBUG":
        log_level = logging.DEBUG
    case "INFO":
        log_level = logging.INFO
    case "WARNING":
        log_level = logging.WARNING
    case "ERROR":
        log_level = logging.ERROR
    case "CRITICAL":
        log_level = logging.CRITICAL
    case _:
        log_level = logging.NOTSET
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

# Make the URL that's used for all requests
BASE_URL = str(os.environ.get("QBITTORRENT_URL", ""))
if not BASE_URL.startswith("http://") or not BASE_URL.startswith("https://"):
    logging.warning("QBITTORRENT_URL doesn't specify a protocol, defaulting to plaint http")
    BASE_URL = "http://" + BASE_URL


# Set up docker exit stuff
def exit_handler(sig, frame) -> None:
    """
    Receive the signal from docker that this container should exit
    """
    logging.info("Received exit signal")
    global RUN_FLAG
    RUN_FLAG = False

RUN_FLAG = True
signal.signal(signal.SIGTERM, exit_handler)


def check_env() -> None:
    """
    Check that all of the environment variables that are required to run are
    present
    """
    expected_env_vars = [
        "QBITTORRENT_URL",
        "QBITTORRENT_USERNAME",
        "QBITTORRENT_PASSWORD",
        "QBITTORRENT_DONE_TAG",
        "NEXTCLOUD_USER",
        "NEXTCLOUD_REL_PATH",
        "NEXTCLOUD_CONTAINER_NAME"
    ]
    for env_var in expected_env_vars:
        if env_var not in os.environ:
            logging.error(f"Missing environment variable {env_var}")
            raise Exception(f"Missing environment variable {env_var}")
    r = requests.get(BASE_URL)
    if r.status_code != 200:
        logging.error(f"Could not connect to qBittorrent: {r.text[:100]}")
        raise Exception("Could not connect to qBittorrent")


def get_login_session() -> requests.Session:
    """
    Log in to qbittorrent using the environment variables QBITTORRENT_URL, 
    QBITTORRENT_USERNAME, and QBITTORRENT_PASSWORD.  Return a `requests` session
    object
    """
    session = requests.Session()
    data = {
        "username": os.environ.get("QBITTORRENT_USERNAME"),
        "password": os.environ.get("QBITTORRENT_PASSWORD")
    }
    r = session.post(f"{BASE_URL}/api/v2/auth/login", data=data)
    if r.status_code != 200:
        logging.error("Could not login to qBittorrent")
        raise Exception("Could not login to qBittorrent")
    logging.info("Logged in to qBittorrent")
    return session


def get_completed_torrents(session: requests.Session) -> List[Dict[str, Any]]:
    """
    Poll the passed session and return the list of torrents that are completed,
    but not yet scanned on nextcloud
    """
    # No tag filter here because I want the program to work regardless of if
    # the user already uses tags
    params = {
        "filter": "completed"
    }
    r = session.get(f"{BASE_URL}/api/v2/torrents/info", params=params)
    if r.status_code != 200:
        logging.error(f"Could not get completed torrents: {r.text[:100]}")
        raise Exception("Could not get completed torrents")
    done_tag = str(os.environ.get("QBITTORRENT_DONE_TAG"))
    torrents = r.json()
    torrents = [t for t in torrents if done_tag not in t["tags"]]
    if len(torrents) > 0:
        logging.info(f"Found {len(torrents)} completed untracked torrent(s)")
    else:
        logging.debug(f"Found no completed untracked torrents")
    return torrents


def mark_torrent_as_done(session: requests.Session, torrent_hash: str) -> None:
    """
    Tag a torrent as being scanned into nextcloud
    """
    done_tag = str(os.environ.get("QBITTORRENT_DONE_TAG"))
    data = {
        "hashes": torrent_hash,
        "tags": done_tag
    }
    r = session.post(f"{BASE_URL}/api/v2/torrents/addTags", data=data)
    if r.status_code != 200:
        logging.error(f"Could not mark torrent as completed: {r.text[:100]}")
        raise Exception("Could not mark torrent as completed")
    logging.info(f"Marked torrent with hash {repr(torrent_hash)} as done")


def update_nextcloud_files() -> None:
    """
    Update the nextcloud files
    """
    nextcloud_user = str(os.environ.get("NEXTCLOUD_USER"))
    nextcloud_rel_path = str(os.environ.get("NEXTCLOUD_REL_PATH"))
    nextcloud_container_name = str(os.environ.get("NEXTCLOUD_CONTAINER_NAME"))
    if ".." in nextcloud_rel_path:
        logging.error("Relative path in NEXTCLOUD_REL_PATH")
        raise ValueError("Relative path in NEXTCLOUD_REL_PATH")
    while nextcloud_rel_path.startswith("/"):
        nextcloud_rel_path = nextcloud_rel_path[1:]

    occ_path = "/var/www/html/occ"
    rescan_path = os.path.join(nextcloud_user, "files", nextcloud_rel_path)

    client = docker.from_env()
    try:
        container = client.containers.get(nextcloud_container_name)
    except docker.errors.NotFound as e:
        logging.info(f"Container {repr(nextcloud_container_name)} not found")
        raise e
    # Yay for Any typing
    if container is None or not isinstance(container, Container):
        logging.error(f"Container {repr(nextcloud_container_name)} is None")
        raise Exception(f"Container {repr(nextcloud_container_name)} is None")
    # Ideally the bare minimum of sanitizing
    rescan_command = shlex.join([occ_path, "files:scan", "--path", rescan_path])
    logging.info(f"Command {repr(rescan_command)} issued")
    retval = container.exec_run(rescan_command, user="www-data")
    if retval.exit_code != 0:
        logging.error(f"Failed to rescan {rescan_path}: {retval.output[:100]}")
        raise Exception(f"Failed to rescan {rescan_path}")
    logging.info(f"Rescan success")


def run_forever():
    logging.info("Starting qbnc run_forever")
    check_env()
    logging.info("Env check passed")
    session_start = time.time()
    last_run = 0
    session = get_login_session()  # Expires after 60m
    while RUN_FLAG:
        if time.time() - session_start > 3300:  # 55m
            session = get_login_session()
            session_start = time.time()
        if time.time() - last_run > 15:  # Run every n seconds
            torrents = get_completed_torrents(session)
            for torrent in torrents:
                mark_torrent_as_done(session, torrent["hash"])
            if torrents:
                update_nextcloud_files()
            last_run = time.time()
        time.sleep(1)  # Fast-ish loop so we can exit
    logging.warning("Loop exited, program halting")


if __name__ == "__main__":
    run_forever()
