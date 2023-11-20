FROM python:3.9-slim-buster
WORKDIR /usr/src/app
ENV NEXTCLOUD_CONTAINER_NAME=nextcloud
ENV QBITTORRENT_DONE_TAG=qbnc_done
RUN pip3 install --no-cache-dir requests docker
COPY main.py main.py
CMD ["python3", "main.py"]