#!/usr/bin/env python3
import logging
import os
import shlex
import signal
import time
from typing import List, Dict, Any, Optional

import docker
import requests
from docker.models.containers import Container

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

BASE_URL = str(os.environ.get("QBITTORRENT_URL", ""))
if not BASE_URL.startswith("http://") or not BASE_URL.startswith("https://"):
    BASE_URL = "http://" + BASE_URL

RUN_FLAG = True

def exit_handler(sig, frame) -> None:
    logging.info("Received exit signal")
    RUN_FLAG = False

signal.signal(signal.SIGTERM, exit_handler)


def check_env() -> None:
    expected_env_vars = [
        "QBITTORRENT_URL",
        "QBITTORRENT_USERNAME",
        "QBITTORRENT_PASSWORD",
        "QBITTORRENT_DONE_TAG",
        "NEXTCLOUD_USER",
        "NEXTCLOUD_REL_DOWNLOADS_PATH",
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
    params = {
        "filter": "completed",
        "tag": ""
    }
    r = session.get(f"{BASE_URL}/api/v2/torrents/info", params=params)
    if r.status_code != 200:
        logging.error(f"Could not get completed torrents: {r.text[:100]}")
        raise Exception("Could not get completed torrents")
    torrents = r.json()
    logging.info(f"Found {len(torrents)} completed torrents")
    return torrents


def mark_torrent_as_done(session: requests.Session, torrent_hash: str) -> None:
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
    nextcloud_user = str(os.environ.get("NEXTCLOUD_USER"))
    nextcloud_rel_downloads_path = str(os.environ.get("NEXTCLOUD_REL_DOWNLOADS_PATH"))
    nextcloud_container_name = str(os.environ.get("NEXTCLOUD_CONTAINER_NAME"))

    occ_path = "/var/www/html/occ"
    rescan_path = os.path.join("var", "www", "html", "data", nextcloud_user, "files", nextcloud_rel_downloads_path)

    client = docker.from_env()
    container = client.containers.get("nextcloud")
    if container is None or not isinstance(container, Container):  # Yay for Any typing
        logging.error(f"Failed to find container {nextcloud_container_name}")
        raise Exception(f"Failed to find container {nextcloud_container_name}")
    rescan_command = shlex.join([occ_path, "files:scan", "--path", rescan_path])  # Ideally the bare minimum of sanitizing
    retval = container.exec_run(rescan_command, user="www-data")
    if retval.exit_code != 0:
        logging.error(f"Failed to rescan {rescan_path}: {retval.output[:100]}")
        raise Exception(f"Failed to rescan {rescan_path}")
    logging.info("Rescan command sent")


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
    print("Exiting...")


if __name__ == "__main__":
    run_forever()
