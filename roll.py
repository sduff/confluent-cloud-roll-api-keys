#!/usr/bin/env python3

# confluent-cloud-roll-api-keys
# Simon Duff <sduff@confluent.io>
#
# v0.1 MVP

import sys, datetime, json, subprocess, re

# Make a .netrc file if one doesnt exist
# read environment variables and login

def ccloud():
    return "/usr/local/bin/ccloud"

def login():
    return [ccloud(), "login"]

def list_env():
    return [ccloud(), "environment", "list", "-o", "json"]

def list_cluster():
    return [ccloud(), "kafka", "cluster", "list", "-o", "json"]

def list_svc_acct():
    return [ccloud(), "service-account", "list", "-o", "json"]

def list_api_key():
    return [ccloud(), "api-key", "list", "-o", "json"]

def new_api_key(environment, resource, service_account, description):
    # make sure args are quoted
    return [ccloud(), "api-key", "create", "-o", "json", "--environment", environment, "--resource", resource, "--service-account", service_account, "--description", description]

def del_api_key(api_key):
    # make sure arg is quoted
    return [ccloud(), "api-key", "delete", api_key]

created_date_format = "%Y-%m-%dT%H:%M:%SZ"

# today
now = datetime.datetime.now()

# validity
validity = 1

ignore_age = False

verbose = False

dry_run = False

roll_message="[AutoRolled]"

# all processed_keys
processed_keys = [] # {env, service_account, api_key, secret}

ccloud_environments = {}
ccloud_clusters = {}
ccloud_service_accounts = {}

sa_allow_list = [".*sduff.*"]
sa_ignore_list = ["zzz.*"]

# By default, allow all resources to be managed
if len(sa_allow_list) == 0:
    sa_allow_list = [".*"]

# build list patterns
sa_allow_re = []
sa_ignore_re = []
try:
    for i in sa_allow_list:
        sa_allow_re.append(re.compile(i))
    for i in sa_ignore_list:
        sa_ignore_re.append(re.compile(i))
except Exception as e:
    print(e)
    sys.exit(1)

try:
# login
    p = subprocess.run(login(), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError("Error with login\n\n%s"%p.stderr)

# list environments
    p = subprocess.run(list_env(), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError("Error listing environments\n\n%s"%p.stderr)
    for e in json.loads(p.stdout):
        id = e["id"] if "id" in e else None
        if id == None:
            raise ValueError("Error parsing environments\n\n%s"%e)
        ccloud_environments[id] = e

    print(ccloud_environments)

# list all service accounts
    p = subprocess.run(list_svc_acct(), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError("Error listing service-accounts\n\n%s"%p.stderr)
    for sa in json.loads(p.stdout):
        id = sa["resource_id"] if "resource_id" in sa else None
        if id == None:
            raise ValueError("Error parsing service-accounts\n\n%s"%sa)
        ccloud_service_accounts[id] = sa

# get all API keys
    p = subprocess.run(list_api_key(), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError("Error getting api-keys\n\n%s"%p.stderr)
    json_data = json.loads(p.stdout)

# iterate over each key
    for k in json_data:
        # check if we can operate on this account
        res_id = k["resource_id"] if "resource_id" in k else None
        sa_id = k["owner_resource_id"] if "owner_resource_id" in k else None

        if sa_id in ccloud_service_accounts:
            sa_name = ccloud_service_accounts[sa_id]["name"] if "name" in ccloud_service_accounts[sa_id] else None

            # regex against allow list, block list
            # check ignore list
            is_allowed = True
            for p in sa_ignore_re:
                if p.match(sa_name):
                    is_allowed = False
            if not is_allowed:
#                print(sa_name, "was not allowed due to ignore list")
                continue
            # check allow list
            is_allowed = False
            for p in sa_allow_re:
                if p.match(sa_name):
                    is_allowed = True
            if not is_allowed:
#                print(sa_name, "was not allowed thru allow list")
                continue

            # get the API key
            api_key = k["key"] if "key" in k else None
            if api_key == None:
                raise ValueError("Error in JSON structure, missing API key\n\n%s"%k)

            # calculate if this api-key is old enough to roll
            created = k["created"] if "created" in k else now
            created_date = datetime.datetime.strptime(created, created_date_format)
            date_diff = now - created_date
            if date_diff.days <= validity and not ignore_age:
                print(f"Skip account:\"{sa_name}\" api-key:\"{api_key}\" age:{date_diff.days}")
                continue    # key is still valid, continue processing

            # Update description
            description = k["description"] if "description" in k else ""
            if not description.endswith(roll_message):
                description += roll_message

            # XXX: Hardcoded for now
            environment = "XXXXXXXXX"
            resource = k["resource_id"] if "resource_id" in k else None
            if resource == None:
                raise ValueError("Error in JSON structure, missing resource\n\n%s"%k)

            if dry_run:
                # Just print what we would do
                #print("Would roll ",sa_name, "API key", api_key, date_diff.days, "days old", environment, resource, sa_id, description)
                print(f"Roll account:\"{sa_name}\" api-key:\"{api_key}\" age:{date_diff.days} env:{environment} resource:{resource} description:\"{description}\"")
            else:
                # OK, we're doing this for reals

                # remove the old api-key
                p = subprocess.run(
                del_api_key(api_key),
                capture_output=True, text=True, timeout=60)
                if p.returncode != 0:
                    raise ValueError("Error deleting API-key",p.stderr)
                else:
                    print("Removed old API-key, ", api_key)

                # create a new api-key
                # keep the same description, but include that it was rolled
                p = subprocess.run(
                new_api_key(environment, resource, sa_id, description),
                capture_output=True, text=True, timeout=60)
                if p.returncode != 0:
                    raise ValueError("Error creating a new API-key",p.stderr)
                jd = json.loads(p.stdout)
                processed_keys.append(
                    {
                        "environment": environment,
                        "environment_name": None, # environment_name, for clarity
                        "resource_id": resource,
                        "resource_name": None,  # resource name, for clarity
                        "service_account_id": sa_id,
                        "service_account_name": sa_name,
                        "api-key": jd["key"],
                        "secret": jd["secret"]
                    }
                )


except ValueError as e:
    print(e)
except json.JSONDecodeError as e:
    print(e)
except subprocess.TimeoutExpired:
    print("Timeout expired")

# Regardless if any exceptions are thrown, print out all the API keys
# TODO: Need to look at ways at storing this in a secure, external repository
for k in processed_keys:
    print(k)
