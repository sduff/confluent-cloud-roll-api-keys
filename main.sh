#!/bin/sh

# Dockerized API Key Roller for Confluent Cloud
# Simon Duff <sduff@confluent.io>

# check creds for confluent login
confluent login --no-browser ${CONFLUENT_LOGIN_ARGS:-}
if [ $? -ne 0 ]
then
   echo "Couldn't login to confluent cloud, exiting"
   exit 1
fi

# Run the rolling script
python3 roll.py
