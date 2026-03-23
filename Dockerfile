FROM python:3.13

RUN apt-get update && apt-get -y install python3 python3-pip git sqlite3 curl

WORKDIR /shkeeper.io

COPY . .

RUN pip3 install -r requirements.txt

CMD gunicorn \
    --no-control-socket \
    --access-logfile - \
    --error-logfile - \
    --workers 1 \
    --threads 16 \
    --worker-class gthread \
    # --timeout 30 \
    # --graceful-timeout 30 \
    # --keep-alive 5 \
    # --max-requests 2000 \
    # --max-requests-jitter 200 \
    -b 0.0.0.0:5000 \
    "shkeeper:create_app()"