FROM ubuntu:latest
RUN apt-get update && \
   DEBIAN_FRONTEND=noninteractive \
   apt-get -y install default-jre-headless && \
   apt-get -y install curl && \
   apt-get -y install python3 python3-pip && \
   apt-get clean && \
   rm -rf /var/lib/apt/lists/*
RUN  curl -sL --http1.1 https://cnfl.io/cli | sh -s -- latest
COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt
CMD "/app/main.sh"
