FROM python:3.9-slim-buster
WORKDIR /usr/src/app
RUN pip3 install --no-cache-dir requests docker
ENV NEXTCLOUD_CONTAINER_NAME=nextcloud
ENV QBITTORRENT_DONE_TAG=qbnc_done
ENV NEXTCLOUD_REL_PATH=""
ENV LOG_LEVEL=info
COPY main.py main.py
CMD ["python3", "main.py"]
