#!/usr/bin/env python3
import requests
import json
import os
import logging
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)


def get_login_session() -> requests.Session:
    session = requests.Session()
    data = {
        "username": os.environ.get("QBITTORRENT_USERNAME"),
        "password": os.environ.get("QBITTORRENT_PASSWORD")
    }
    r = session.post("https://qbittorrent.lizardswimmer.com/api/v2/auth/login", data=data)
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
    r = session.get("https://qbittorrent.lizardswimmer.com/api/v2/torrents/info", params=params)
    if r.status_code != 200:
        logging.error(f"Could not get completed torrents: {r.text[:100]}")
        raise Exception("Could not get completed torrents")
    torrents = r.json()
    logging.info(f"Found {len(torrents)} completed torrents")
    return torrents


def mark_torrent_as_done(session: requests.Session, torrent_hash: str) -> None:
    data = {
        "hashes": torrent_hash,
        "tags": "qbnc_mgr_done"
    }
    r = session.post("https://qbittorrent.lizardswimmer.com/api/v2/torrents/addTags", data=data)
    if r.status_code != 200:
        logging.error(f"Could not mark torrent as completed: {r.text[:100]}")
        raise Exception("Could not mark torrent as completed")
    logging.info(f"Marked torrent with hash {repr(torrent_hash)} as done")


if __name__ == "__main__":
    logging.info("Main")
    session = get_login_session()
    torrents = get_completed_torrents(session)
    for torrent in torrents:
        mark_torrent_as_done(session, torrent["hash"])