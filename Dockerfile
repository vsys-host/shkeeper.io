FROM ubuntu:focal

RUN apt-get update && apt-get -y install python3 python3-pip git sqlite3 curl

WORKDIR /shkeeper.io

COPY . .

RUN pip3 install -r requirements.txt

CMD gunicorn \
    --access-logfile - \
    --reload \
    --workers 1 \
    --threads 16 \
    --worker-class gthread \
    --timeout 600 \
    -b 0.0.0.0:5000 \
    "shkeeper:create_app()"
