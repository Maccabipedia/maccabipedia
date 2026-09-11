import os

family = 'maccabipedia'
mylang = 'he'

usernames['maccabipedia']['he'] = os.environ['MACCABIPEDIA_BOT_USERNAME']

password_file = "user-password.py"

put_throttle = 0

# maccabipedia's Imunify360 WAF returns HTTP 415 to requests whose Accept header is the
# default wildcard */* (fires for datacenter IPs, so it broke scheduled CI jobs). Pin a
# concrete Accept on every pywikibot request; MediaWiki ignores Accept so no body changes.
extra_headers = {'Accept': 'application/json'}
