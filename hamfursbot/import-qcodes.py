import json
from pymongo import MongoClient

client = MongoClient()
db = client.hamfurs.definitions

with open('qcodes.json') as f:
  codes = json.load(f)

export = []

for code in codes:
  data = {
    "term" : code['code'],
    "index" : code['code'].lower(),
    "keywords" : [code['code'].lower(),],
    "definition" : "*Question:* _{0}_\n*Answer:* {1}\n[Source](https://en.wikipedia.org/wiki/Q_code#Q_codes_as_adapted_for_use_in_amateur_radio)".format(code['query'], code['answer']),
    "metaphone": ['', ''],
    "contributor" : "HamFursBot",
    "last_edit" : "2017-01-02 12:00:00"
  }

  export.append(data)


rv = db.insert_many(export)
print("Inserted: {0}".format(db.count()))
