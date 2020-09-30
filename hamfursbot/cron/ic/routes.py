#!/usr/bin/env python3

"""
A (cached) JSON API for the Industry Canada Amateur Radio callbook

By callsign:
============

  GET http://rechner.us.to/ic/callbook/<callsign>

    e.g. http://rechner.us.to/ic/ve3fxy

  Response
  --------
  {
    "callsign" : string
    "name" : string
    "surname" : string
    "address" : string
    "city" : string
    "province" : string, two-letter abbreviation
    "postcode" : string
    "qualifications" : {
      "basic" : boolean
      "5wpm" : boolean
      "12wpm" : boolean
      "advanced" : boolean
      "basic_honours" : boolean
    }
    "club" : (null or) {
      "name" : string,
      "name2" : string,
      "address" string,
      "city" : string,
      "province" : string,
      "postcode" : string
    }
    "updated" : float UTC UNIX timestamp
    "_id" : serialised BSON nonsense (don't worry about it)
  }

"""

from pymongo import MongoClient
from flask import Flask, abort, g, jsonify
from flask.json import JSONEncoder
from bson import ObjectId
from bson.json_util import dumps

app = Flask(__name__)

def get_db():
  db = getattr(g, 'database', None)
  if db is None:
    g.client = MongoClient()
    g.database = g.client.ic
  return g.database

@app.route('/')
def index():
  return __doc__, 501, {'Content-Type': 'text/plain'}

@app.route('/callbook/<callsign>')
def by_callsign(callsign):
  db = get_db()
  collection = db.callbook
  
  result = collection.find_one({ 'callsign' : callsign.upper() })
  if result is None:
    abort(404)
  return dumps(result)


class JSONEncoder(JSONEncoder):
  def default(self, obj):
    if isinstance(obj, ObjectId):
      return str(obj)
    return json.JSONEncoder.default(self, obj)

if __name__ == '__main__':
  app.run(host='0.0.0.0', debug=True)
