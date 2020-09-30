#!/usr/bin/env python3

import telnetlib


class AttrDict(dict):
  def __init__(self, *args, **kwargs):
    super(AttrDict, self).__init__(*args, **kwargs)
    self.__dict__ = self


class ReverseBeaconClient(object):
  TELNET_HOST = "telnet.reversebeacon.net"
  def __init__(self, callsign="N0CALL", host=TELNET_HOST, port=7000, timeout=10):
    self.conn = telnetlib.Telnet(host, port)
    self.conn.read_until(b"Please enter your call: ", timeout)
    self.conn.write("{0}\n".format(callsign).encode('ascii'))
    info = self.conn.read_until(callsign.upper().encode('ascii'), timeout)

    tokens = info.decode('ascii').split('\r\n')
    print(info.decode('ascii'))
    self.local_users = tokens[3].split()[-1]
    self.spot_rate = tokens[5].split()[4]
    
    info = self.conn.read_until(b'\r\n', timeout)
    tokens = info.decode('ascii').split(' ')
    self.skimmer = tokens[1]
    self.connect_time = "{0} {1}".format(tokens[2], tokens[3])


  @staticmethod
  def parse_line(raw):
    (start, end) = raw.split(':')
    skimmer = start[6:-2]
    
    end_parts = end.split()
    if len(end_parts) < 9:
      print("Not enough tokens ({0}): '{1}'".format(len(end_parts), raw))
    freq = end_parts[0]
    dx = end_parts[1]
    mode =  end_parts[2]
    snr = int(end_parts[3])
    rate = int(end_parts[5])
    units = end_parts[6]
    match = end_parts[7]
    time = end_parts[8]
    
    data = { 
      'skimmer' : skimmer,
      'frequency' : freq,
      'callsign' : dx,
      'mode' : mode,
      'snr' : snr,
      'rate' : rate,
      'units' : units,
      'match' : match,
      'time' : time
    }

    return AttrDict(data)

  def read_chunk(self):
    raw = self.conn.read_very_eager().decode('ascii')
    if raw == '':
      return []

    tokens = raw.split('\r\n')
    lines = []
    for line in tokens:
      if ':' in line:
        lines.append(ReverseBeaconClient.parse_line(line))
    return lines

  def close(self):
    self.conn.close()

if __name__ == '__main__':
  client = ReverseBeaconClient("KF3RRY")
  import time
  import pprint

  while True:
    try:
      chunk = client.read_chunk()
      skimmer_line = "(via {skimmer}, {rate} {units} @ {snr} dB, {time})"
      for line in chunk:
        print(skimmer_line.format(**line))

      #pprint.pprint(chunk)
      time.sleep(1)
    except KeyboardInterrupt:
      client.conn.close()
      exit()


