#!/usr/bin/env python3

# confluent-cloud-roll-api-keys
# Simon Duff <sduff@confluent.io>
import sys, datetime, json, subprocess, re, os

# TODO: Check if Azure Creds are provided, and if so, try and connect to Azure KeyVault
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential

# Azure Key Vault Secrets
credential = DefaultAzureCredential()
vault_url = os.environ["VAULT_URI"] if "VAULT_URI" in os.environ else ""
secret_client = SecretClient(vault_url=vault_url, credential=credential)

# Check writability to the key vault before proceeding with key rolling
try:
    secret = secret_client.set_secret("secret-write-test","sduff was here")
except Exception as e:
    print ("Unable to write secret, cancel all api-key rolling")
    print (e)
    sys.exit(1)

# Rolling Configuration
try:
    validity = int(os.environ["KEY_VALIDITY"]) if "KEY_VALIDITY" in os.environ else 14

    ignore_age = os.environ["IGNORE_AGE"] if "IGNORE_AGE" in os.environ else "False"
    ignore_age = True if ignore_age=="True" else False

    verbose = os.environ["VERBOSE"] if "VERBOSE" in os.environ else "False"
    verbose = True if verbose=="True" else False

    dry_run = os.environ["DRY_RUN"] if "DRY_RUN" in os.environ else "False"
    dry_run = True if dry_run=="True" else False

    roll_message = os.environ["ROLL_MESSAGE"] if "ROLL_MESSAGE" in os.environ else "[AutoRolled]"

    sa_allow = os.environ["ALLOW"] if "ALLOW" in os.environ else ".*"
    sa_allow_re = re.compile(sa_allow)

    sa_ignore = os.environ["IGNORE"] if "IGNORE" in os.environ else ""
    sa_ignore_re = re.compile(sa_ignore)

    valid_env = os.environ["CCLOUD_ENV"] if "CCLOUD_ENV" in os.environ else ""
    # if comma separated, replace with space
    valid_env = re.sub("\"|'|,", "", valid_env)
    valid_env = re.sub("\s+", " ", valid_env)
    valid_env = valid_env.split(" ")

    # Keep this as configurable, in case the format ever changes
    created_date_format = os.environ["CREATED_DATE_FORMAT"] if "CREATED_DATE_FORMAT" in os.environ else "%Y-%m-%dT%H:%M:%SZ"

except Exception as e:
    print ("Error parsing configuration")
    print (e)
    sys.exit(1)

if verbose:
    print("# Roll Configuration")
    print(f"VALIDITY= {validity}")
    print(f"IGNORE_AGE= {ignore_age}")
    print(f"VERBOSE= {verbose}")
    print(f"DRY_RUN= {dry_run}")
    print(f"ROLL_MESSAGE= {roll_message}")
    print(f"ALLOW= {sa_allow}")
    print(f"IGNORE= {sa_ignore}")
    print(f"CCLOUD_ENV= {valid_env}")
    print("\n# Azure Key Vault config")
    print(f"VAULT_URL= {vault_url}")

# Today
now = datetime.datetime.now()

# Functions
cmd = "/usr/bin/confluent"
#cmd = "/Users/sduff/cli/bin/confluent"
def runcmd(cl,j=True):
    p = subprocess.run(cl, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError(f"Error running command: {cl}\n{p.stderr}")
    if j:
        try:
            return json.loads(p.stdout)
        except:
            raise ValueError(f"Error parsing JSON after {cl}\n{p.stdout}")
    else:
        return p.stdout

def login():
    data = runcmd([cmd,"login"], j=False)
    return data

def list_envs():
    data = runcmd([cmd,"environment","list","-o","json"])
    return data

def switch_env(e):
    data = runcmd([cmd,"environment","use",e],j=False)
    return data

def list_clusters(env=None):
    data = runcmd([cmd,"kafka","cluster","list","-o","json"])
    return data

def list_service_accounts():
    data = runcmd([cmd,"iam","service-account","list","-o","json"])
    return data

def list_ksql():
    data = runcmd([cmd,"ksql","app","list","-o","json"])
    return data

def list_schema_registry():
    data = runcmd([cmd,"schema-registry","cluster","describe","-o","json"])
    return data

def list_api_keys():
    data = runcmd([cmd,"api-key","list","-o","json"])
    return data

def delete_api_key(api_key):
    data = runcmd([cmd,"api-key","delete",api_key],j=False)
    print(f">>> {data}")
    return data

def new_api_key(service_account=None,description=None,environment=None,resource=None):
    args = [cmd,"api-key","create","-o","json"]

    if service_account != None:
        args.extend(['--service-account', service_account])

    if description != None:
        args.extend(['--description', description])

    if environment != None:
        args.extend(['--environment', environment])

    if resource != None:
        args.extend(['--resource', resource])

    data = runcmd(args)
    return data

#
# Actual processing begins here
#

# all processed_keys
processed_keys = [] # {env, service_account, api_key, secret}

ccloud_environments = {}
ccloud_clusters = {}
ccloud_ksql = {}
ccloud_schema_registry = {}
ccloud_service_accounts = {}

try:
    # make sure account is logged in. This should be checked prior
    login()

    # get a list of all the environments
    data = list_envs()
    for item in data:
        id = item["id"] if "id" in item  else None
        if id == None:
            raise ValueError(f"Missing id in environment {id}")
        ccloud_environments[id] = item

    if verbose:
        print("# Environments")
        print (ccloud_environments)

    # Iterate over each environment to collect clusters and other env-level resources
    # TODO: Do this just on select environments
    for e in ccloud_environments:
        data = switch_env(e)

        data = list_clusters()
        for c in data:
            id = c["id"] if "id" in c else None
            if id == None:
                raise ValueError(f"Missing id in cluster {c}")
            c['environment'] = e
            ccloud_clusters[id] = c

        data = list_ksql()
        for c in data:
            id = c["id"] if "id" in c else None
            if id == None:
                raise ValueError(f"Missing id in ksql {c}")
            c['environment'] = e
            ccloud_ksql[id] = c

        data = list_schema_registry()
        id = data["cluster_id"] if "cluster_id" in data else None
        if id == None:
            raise ValueError(f"Missing cluster_id in schema registry {data}")
        data['environment'] = e
        ccloud_clusters[id] = data

    if verbose:
        print("\n# Clusters")
        print(ccloud_clusters)
        print("\n# KSQL")
        print(ccloud_ksql)

    envs_name_to_id = {}
    for k,v in ccloud_environments.items():
        envs_name_to_id[v["name"]] = k

    valid_env_ids = {}
    for e in valid_env:
        if e not in envs_name_to_id:
            print(f"WARNING: User provided environment {e} but not in organisation")
        else:
            env_id = envs_name_to_id[e]
            valid_env_ids[env_id] = e

    # get all service accounts
    data = list_service_accounts()
    for c in data:
        id = c["id"] if "id" in c else None
        if id == None:
            raise ValueError(f"Missing id in service_account {c}")
        ccloud_service_accounts[id] = c

    # get all api-keys
    data = list_api_keys()
    for k in data:
        res_id = k["resource_id"] if "resource_id" in k else None
        res_type = k["resource_type"] if "resource_type" in k else None
        sa_id = k["owner_resource_id"] if "owner_resource_id" in k else None

        # get the API key
        api_key = k["key"] if "key" in k else None
        if api_key == None:
            raise ValueError("Error in JSON structure, missing API key\n\n%s"%k)

        print(f"Analysing key, res_id: {res_id} res_type: {res_type} sa_id: {sa_id} api_key: {api_key}")

        e = None
        cc = None
        svc_name = None

        # Getting some details about this service account and assoicated resources
        if res_id in ccloud_clusters:
            cc = ccloud_clusters[res_id]
            if "environment" in cc:
                e = cc['environment']

        elif res_type == "ksql":
            cc = ccloud_ksql[res_id]
            if "environment" in cc:
                e = cc['environment']

        elif res_type == "cloud":
            pass

        else:
            pass

        # Checking environment id
        if e in valid_env_ids:
            if verbose:
                print("This api-key is in a valid environment")
        else:
            if verbose:
                print("This api-key is not in a valid environment")
            continue

        # Checking Service Account name
        sa = ccloud_service_accounts[sa_id] if sa_id in ccloud_service_accounts else None
        sa = sa["name"] if sa != None and "name" in sa else ""

        if sa_ignore_re.match(sa) and sa_ignore != "":
            if verbose:
                print(f"Service Account '{sa}' matched ignore list, skipping")
            continue

        if not sa_allow_re.match(sa):
            if verbose:
                print(f"Service Account '{sa}' didnt match allow list, skipping")
            continue

        # Checking age of this service account
        created = k["created"] if "created" in k else now
        created_date = datetime.datetime.strptime(created, created_date_format)
        date_diff = now - created_date
        if date_diff.days <= validity and not ignore_age:
            if verbose:
                print(f"API key isnt old enough, account:\"{sa}\" api-key:\"{api_key}\" age:{date_diff.days}, skipping")
            continue    # key is still valid, no need to update it
        else:
            if verbose:
                print(f"All checks passed for account, sa'{sa}', api-key:\"{api_key}\" age:{date_diff.days}")

        # Update description
        description = k["description"] if "description" in k else ""
        if not description.endswith(roll_message):
            description += roll_message

        if dry_run:
            print(f"Dry run, but would roll API-key sa:'{sa}' sa_id:'{sa_id}' resource:'{res_id}' environment:'{e}' desc:'{description}'")
            continue
        else:
            print(f"Roll API-key sa:'{sa}' sa_id:'{sa_id}' resource:'{res_id}' environment:'{e}' desc:'{description}'")
            # actual rolling of the API key
            # delete old key
            if verbose:
                print("Deleteing API key")
            data = delete_api_key(api_key)
            # TODO: Check response code from delete_api_key call to make sure proper delete
            # create new key
            if verbose:
                print("Creating new API key")
            data = new_api_key(service_account=sa_id, description=description, environment=e,resource=res_id)
            sec_key = data["key"]
            sec_value = data["secret"]
            value = f"svc_acct:'{sa}' svc_acct_id:'{sa_id}' api_key:'{sec_key}' api_secret:'{sec_value}'"
            v = {}
            v['service_account'] = sa
            v['service_account_id'] = sa_id
            v['api_key'] = sec_key
            v['api_secret'] = sec_value

            v_json = json.dumps(v)

            # store key safely
            cleaned_sa = re.sub("[^a-zA-Z0-9\-]", "-", sa)
            sec = secret_client.set_secret(cleaned_sa, v_json)
            if verbose:
                print(f"Stored API key '{sec_key}' in Azure Key Vault '{sec.id}'")


    print("All done, bye for now")

except Exception as e:
    print (e)
