#!/usr/bin/env python3

from xml.etree import ElementTree
import requests

ENDPOINTS = {
  "auth" : "https://www.hamqth.com/xml.php?u={username}&p={password}",
  "callbook" :"https://www.hamqth.com/xml.php?id={id}&callsign={callsign}&prg={agent}" 
}

__version__ = '0.0.1'

USERAGENT = "pyHamQTH v{0}".format(__version__)

class Error(Exception):
  pass

class AuthenticationError(Error):
  pass

class RequestError(Error):
  pass

class NotFoundError(RequestError):
  pass

class HamQTH(object):
  def __init__(self, username, password, agent=USERAGENT):
    self.username = username
    self.password = password
    self.user_agent = agent
    self.session_id = None
    self.retries = None

    self._refresh_session()

  def _check_session(self, tree):
    assert tree.tag == '{https://www.hamqth.com}HamQTH'
    if tree[0].tag == '{https://www.hamqth.com}session':
      if tree[0][0].tag == '{https://www.hamqth.com}error':
        error = tree[0][0].text
        if error == 'Wrong user name or password':
          raise AuthenticationError(error)
        elif error == 'Session does not exist or expired':
          self._refresh_session()
          return True
        elif error == 'Callsign not found':
          raise NotFoundError(error)
    return False

  def _refresh_session(self):
    endpoint = ENDPOINTS['auth']
    arguments = {
      'username' : self.username,
      'password' : self.password
    }
    response = requests.get(endpoint.format(**arguments))

    tree = ElementTree.fromstring(response.content)
    assert tree.tag == '{https://www.hamqth.com}HamQTH'

    if tree[0][0].tag == '{https://www.hamqth.com}session_id':
      self.session_id = tree[0][0].text
    elif tree[0][0].tag == '{https://www.hamqth.com}error':
      raise AuthenticationError(tree[0][0].text)

  def _increment_retry(self):
    if self.retries is None:
      self.retries = 0
    else:
      self.retries += 1
    if self.retries > 3:
      raise RequestError('Maximum retries exceeded')

  def callbook(self, callsign):
    self._increment_retry()
    endpoint = ENDPOINTS['callbook']
    arguments = {
      'id' : self.session_id,
      'callsign' : callsign,
      'agent' : self.user_agent
    }
    response = requests.get(endpoint.format(**arguments))
    #import pdb; pdb.set_trace()
    tree = ElementTree.fromstring(response.content)

    try:
      retry = self._check_session(tree)
    except NotFoundError as e:
      return None

    if retry:
      # Re-try request
      return self.callbook(callsign)

    self.retries = None

    data = { child.tag[24:] : child.text for child in tree[0].getchildren() }
    return data

if __name__ == '__main__':
  import pprint
  api = HamQTH("kf3rry", "super sekrit")
  pprint.pprint(api.callbook('kf3rry'))

  while True:
    pprint.pprint(api.callbook(raw_input(' > ')))
