#!/usr/bin/env python3

import os
import sys
import csv
import time
from pymongo import MongoClient

if len(sys.argv) != 2:
  print("Usage: {0} <inputfile>".format(sys.argv[0]))
  sys.exit(1)
filename = sys.argv[1]

client = MongoClient(os.environ['HAMFURS_MONGO_HOST'])
db = client.ic
collection = db.callbook

count = 0
updated = 0

# Import CSV
try:
  with open(sys.argv[1], encoding='iso8859-14') as csvfile:
    timestamp = int(time.time())
    reader = csv.reader(csvfile, delimiter=';')
    for row in reader:
      document = {
        'callsign' : row[0],
        'name' : row[1],
        'surname' : row[2],
        'address' : row[3],
        'city' : row[4],
        'province' : row[5],
        'postcode' : row[6],
        'qualifications' : {
          'basic' : True if row[7] == 'A' else False,
          '5wpm' : True if row[8] == 'B' else False,
          '12wpm' : True if row[9] == 'C' else False,
          'advanced' : True if row[10] == 'D' else False,
          'basic_honours' : True if row[11] == 'E' else False
        },
        'club' : None if row[12] == '' else {
          'name' : row[12],
          'name2' : row[13],
          'address' : row[14],
          'city' : row[15],
          'province' : row[16],
          'postcode' : row[17]
        },
        'updated' : timestamp
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
