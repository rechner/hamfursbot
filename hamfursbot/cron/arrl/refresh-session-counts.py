#!/usr/bin/env python3

"""
Scrape the ARRL website for VE session counts and cache counts
in a nosql thing so we can query that programmatically.

http://www.arrl.org/ve-session-counts?state=VA
"""

import os
import time
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient

STATES = [ "Non-US", "AL", "AK", "AS", "AZ", "AR", "CA",
   "CO", "CT", "DE", "DC", "FL", "GA", "GU", "HI", "ID",
   "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
   "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
   "NM", "NY", "NC", "ND", "MP", "OH", "OK", "OR", "PA",
   "PR", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VI",
   "VA", "WA", "WV", "WI", "WY" ]

def main(collection):
    for state in STATES:
        timestamp = time.time()
        print("Processing {0}... ".format(state), end='')
        final_list = []
        page = requests.get("http://www.arrl.org/ve-session-counts?state={0}".format(state))
        soup = BeautifulSoup(page.text, "html5lib")

        data = []
        try:
            table_body = soup.find_all('table')[0]
        except IndexError:
            print(" ->FAIL<- no table found")
            import pdb; pdb.set_trace()
            #time.sleep(10)
            continue
        rows = table_body.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            cols = [element.text.strip() for element in cols]
            # Strip empty values
            data.append([element for element in cols if element])

        for row in data[1:]:
            parts = row[0].split('(')
            callsign = parts[0].strip()
            name = parts[1].strip(')')
            final_list.append({'callsign' : callsign, 'name' : name, 'count' : int(row[1]), 'state' : state, 'updated' : timestamp})

        # Delete the old collection and re-insert the latest:
        collection.delete_many({'state' : state})
        collection.insert_many(final_list)
        print(' -> OK <- ({0} records)'.format(len(data[1:])))

        time.sleep(5)

if __name__ == '__main__':
    client = MongoClient(host=os.environ['HAMFURS_MONGO_HOST'])
    db = client.arrl
    collection = db.ve_session_counts
    main(collection)
