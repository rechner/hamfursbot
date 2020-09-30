#!/usr/bin/env python3

import os
import sys
import csv
import time
import datetime
from pymongo import MongoClient

if len(sys.argv) != 2:
  print("Usage: {0} <inputfile>".format(sys.argv[0]))
  sys.exit(1)
filename = sys.argv[1]

client = MongoClient(os.environ['HAMFURS_MONGO_HOST'])
db = client.nkom
collection = db.callbook

count = 0
updated = 0

TYPES = {
  'Personlig' : 'Person',
  'Organisasjon' : 'Organisation',
  'Myndighet' : 'Authority',
  'Bedrift' : 'Defense',
  'Skole' : 'School'
}

# Import CSV
try:
  with open(sys.argv[1], encoding='cp865') as csvfile:
    timestamp = int(time.time())
    reader = csv.reader(csvfile, delimiter=';')
    for row in reader:
      if row[9] in TYPES.keys():
        record_type = TYPES[row[9]]
      else:
        record_type = row[9]

      try:
        updated_date = datetime.datetime.strptime(row[12], '%d.%m.%Y').strftime('%Y-%m-%d')
      except:
        updated_date = row[12]

      document = {
        'callsign' : row[0],
        'club' : row[1],
        'name' : row[2],
        'surname' : row[3],
        'address' : row[4],
        'address2' : row[5],
        'city' : row[7],
        'country' : row[8],
        'type' : record_type,
        'postcode' : row[6],
        'cached' : timestamp,
        'updated' : updated_date,
        'valid' : row[10],
        'expiration' : row[11],
        'comment' : row[13]
      }

      # NOTE: Drop all and insert seems to be much faster than update
      #collection.insert_one(document)
      r = collection.replace_one({'callsign' : row[0]}, document, upsert=True)
      updated += r.modified_count

      count += 1
      sys.stderr.write("Processing {0}    \r".format(row[0]))


except FileNotFoundError as e:
  print("No such file: {0}.\n{1}".format(sys.argv[1], e))

print("\n[ OK ]")
print("  Processed: {0}".format(count))
print("    Updated: {0}".format(updated))
print("        New: {0}".format(count - updated))
