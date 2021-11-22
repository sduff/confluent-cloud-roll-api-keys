FROM python:3.8-slim

WORKDIR /app

ADD requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

ADD main.sh /app
ADD roll.py /app

RUN apt-get update && apt-get install -y curl
RUN curl -sL --http1.1 https://cnfl.io/cli | sh -s -- latest

CMD [ "/app/main.sh" ]
