#!/usr/bin/env python3

import os
import requests
from pymongo import MongoClient

#DUMP_URL = "http://www.dmr-marc.net/cgi-bin/trbo-database/datadump.cgi?table=users&format=json"
DUMP_URL = "https://www.radioid.net/static/users.json"

client = MongoClient(host=os.environ['HAMFURS_MONGO_HOST'])
db = client.dmr_marc

r = requests.get(DUMP_URL)

dmr_document = r.json()

# Delete and re-insert the entire database
db.users.delete_many({})

db.users.insert_many(dmr_document['users'])
