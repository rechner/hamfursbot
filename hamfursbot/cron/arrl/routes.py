#!/usr/bin/env python3

"""
A hopefully more useful version of http://www.arrl.org/ve-session-counts

By callsign:
============

  GET http://rechner.us.to/arrl/counts/<callsign>

    e.g. http://rechner.us.to/arrl/counts/kf3rry

  Response
  --------
  {
    "callsign" : string
    "name" : string
    "count" : int
    "state" : string 2-letter state abbreviation or 'Non-US'
    "updated" : float UTC UNIX timestamp
    "_id" : serialised BSON nonsense (don't worry about it)
  }

By state:
=========

  GET http://rechner.us.to/arrl/state/<state>

    e.g. http://rechner.us.to/arrl/counts/dc

  Request with no arguments to get the whole shebang

  Response
  --------
  JSON list of elements above
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
    g.database = g.client.arrl
  return g.database

@app.route('/')
def index():
  return __doc__, 501, {'Content-Type': 'text/plain'}

@app.route('/counts/<callsign>')
def by_callsign(callsign):
  db = get_db()
  collection = db.ve_session_counts
  
  result = collection.find_one({ 'callsign' : callsign.upper() })
  if result is None:
    abort(404)
  return dumps(result)

@app.route('/counts/')
@app.route('/counts/state/')
@app.route('/counts/state/<state>')
def by_state(state=None):
  db = get_db()
  collection = db.ve_session_counts

  rows = None
  results = []
  if state is None:
    rows = collection.find({})
  else:
    rows = collection.find({ 'state' : state.upper() })

  if rows is None:
    abort(404)

  for row in rows:
    results.append(row)

  return dumps(results)

class JSONEncoder(JSONEncoder):
  def default(self, obj):
    if isinstance(obj, ObjectId):
      return str(obj)
    return json.JSONEncoder.default(self, obj)

if __name__ == '__main__':
  app.run(host='0.0.0.0', debug=True)
