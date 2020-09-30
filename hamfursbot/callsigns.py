#!/usr/bin/env python3

"""
Tests a callsign for validity according to ITU allocations and format
specification (ITU Article 19.68, 19.69).

A match does not necessarily mean that the callsign is valid or even
available for assignment for amateur operators in that country, but
merely tests if allocation would be allowed under ITU rules.
"""

import re

callsign_regexen = {
  'UNAVALIABLE' : r'^((?:[0-9]{2})|Q)[A-Z]{0,1}[0-9][A-Z]{1,4}$',
  'US' : r'^((?:A[A-L][A-Z]?)|(?:[KNW][A-Z]{0,2}))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'ES' : r'^((?:A[M-O][A-Z]?)|(?:E[A-H][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'PK' : r'^((?:A[P-S][A-Z]?)|(?:6[P-S][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'IN' : r'^((?:A[T-W][A-Z]?)|(?:V[T-W][A-Z]?)|(?:8[T-Y][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'AU' : r'^((?:AX[A-Z]?)|(?:V[H-NZ][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'AR' : r'^((?:A[YZ][A-Z]?)|(?:L[O-W][A-Z]?)|(?:L[2-9][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'CA' : r'^((?:V[A-GOX-Y][A-Z]?)|(?:X[J-O][A-Z]?)(?:C[F-KYZ][A-Z]?))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'NL' : r'^(P[A-J][A-Z]?)([0-9])([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'DE' : r'^((?:D[A-R][A-Z]?)|(?:Y[2-9][A-Z]{1,2}))([0-9])[A-Z0-9]{0,3}[A-Z]$',
  'UK' : r'^((?:[GM2][A-Z]{0,2})|(?:V[P-QS][A-Z]{0,2})|(?:Z[B-JNOQ][A-Z]?)|(?:2[A-Z]{1,2}))([0-9])[A-Z0-9]{0,3}[A-Z]$'
}

COUNTRY_NAMES = {
  'AU' : 'Australia',
  'UK' : 'United Kingdom',
  'US' : 'United States',
  'ES' : 'Spain',
  'PK' : 'Pakistan',
  'IN' : 'India',
  'AU' : 'Australia',
  'AR' : 'Argentina',
  'CA' : 'Canada',
  'NL' : 'Netherlands',
  'DE' : 'Germany'
}

callsign_matches = {}
for key, val in callsign_regexen.items():
  callsign_matches[key] = re.compile(val, re.IGNORECASE)

def get_country(callsign):
  for country, regex in callsign_matches.items():
    match = regex.match(callsign)
    if match is not None:
      return country
  return None

if __name__ == '__main__':
  while True:
    print(get_country(raw_input("Enter callsign > ")))
