# QBitTorrent Nextcloud Integration

## Environment variables

* `QBITTORRENT_URL`  The url that the qbittorrent webui can be reached on.  e.g. https://qbittorrent.example.com
* `QBITTORRENT_USERNAME`  The username for the qbittorrent webui.
* `QBITTORRENT_PASSWORD`  The password for the qbuttorrent webui.
* `QBITTORRENT_DONE_TAG`  The tag that will mark downloads that have been scanned, defaults to "qbnc_done".
* `NEXTCLOUD_USER`  The nextcloud user with the downloads path
* `NEXTCLOUD_REL_DOWNLOADS_PATH`  The relative path within the `NEXTCLOUD_USER`'s files.
* `NEXTCLOUD_CONTAINER_NAME`  The container name that is nextcloud, defaults to "nextcloud".