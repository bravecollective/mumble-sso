#!/usr/bin/env python

import os, sys, time, re
import MySQLdb, ConfigParser

import Ice
try:
        Ice.loadSlice('-I/usr/share/Ice/slice/ /usr/share/slice/Murmur.ice')
except RuntimeError, e:
        print(format(e))
        sys.exit(0)
        Ice.loadSlice("--all -I/usr/share/Ice/slice/ /usr/share/slice/Murmur.ice")
import Murmur

# -------------------------------------------------------------------------------

cfg = 'mumble-sso-auth.ini'
print('Reading config file: {0}'.format(cfg))
config = ConfigParser.RawConfigParser()
config.read(cfg)

server_id = config.getint('murmur', 'server_id')

sql_name = config.get('mysql', 'sql_name')
sql_user = config.get('mysql', 'sql_user')
sql_pass = config.get('mysql', 'sql_pass')
sql_host = config.get('mysql', 'sql_host')

display_name = config.get('misc', 'display_name')
restrict_access_by_ticker = config.get('misc', 'restrict_access_by_ticker')

# -------------------------------------------------------------------------------

try:
    db = MySQLdb.connect(sql_host, sql_user, sql_pass, sql_name)
    db.close()
except Exception, e:
    print("Database intitialization failed: {0}".format(e))
    sys.exit(0)

# -------------------------------------------------------------------------------

class ServerAuthenticatorI(Murmur.ServerUpdatingAuthenticator):
	global server
	def __init__(self, server, adapter):
		self.server = server

	def authenticate(self, name, pw, certificates, certhash, cerstrong, out_newname):
	    try:
		db = MySQLdb.connect(sql_host, sql_user, sql_pass, sql_name)

# ---- Verify Params

		if(not name or len(name) == 0):
			return (-1, None, None)

		print("Info: Trying '{0}'".format(name))

		if(not pw or len(pw) == 0):
			print("Fail: {0} did not send a passsword".format(name))
			return (-1, None, None)

# ---- Retrieve User

		ts_min = int(time.time()) - (60 * 60 * 24 * 7)
		c = db.cursor(MySQLdb.cursors.DictCursor)
		c.execute("SELECT * FROM user WHERE mumble_username = %s AND updated_at > %s", (name, ts_min))
		row = c.fetchone()
		c.close()

		if not row:
		    print("Fail: {0} not found in database".format(name))
		    return (-1, None, None)

		character_id = row['character_id']
		character_name = row['character_name']
		corporation_id = row['corporation_id']
		corporation_name = row['corporation_name']
		alliance_id = row['alliance_id']
		alliance_name = row['alliance_name']
		mumble_password = row['mumble_password']
		group_string = row['groups']
		nick = row['mumble_fullname']

		groups = []
		groups.append('corporation-' + str(corporation_id))
		groups.append('alliance-' + str(alliance_id))
		if group_string:
		    for g in group_string.split(','):
			groups.append(g.strip())

# ---- Verify Password

		if mumble_password != pw:
		    print("Fail: {0} password does not match for {1}: '{2}' != '{3}'".format(name, character_id, mumble_password, pw))
		    return (-1, None, None)

# ---- Check Bans

		c = db.cursor(MySQLdb.cursors.DictCursor)
		c.execute("SELECT * FROM ban WHERE filter = %s", ('alliance-' + str(alliance_id),))
		row = c.fetchone()
		c.close()

		if row:
		    print("Fail: {0} alliance banned from server: {1} / {2}".format(name, row['reason_public'], row['reason_internal']))
		    return (-1, None, None)

		c = db.cursor(MySQLdb.cursors.DictCursor)
		c.execute("SELECT * FROM ban WHERE filter = %s", ('corporation-' + str(corporation_id),))
		row = c.fetchone()
		c.close()

		if row:
		    print("Fail: {0} corporation banned from server: {1} / {2}".format(name, row['reason_public'], row['reason_internal']))
		    return (-1, None, None)

		c = db.cursor(MySQLdb.cursors.DictCursor)
		c.execute("SELECT * FROM ban WHERE filter = %s", ('character-' + str(character_id),))
		row = c.fetchone()
		c.close()

		if row:
		    print("Fail: {0} character banned from server: {1} / {2}".format(name, row['reason_public'], row['reason_internal']))
		    return (-1, None, None)

# ---- Done

		print("Success: '{0}' as '{1}' in {2}".format(character_id, nick, groups))
		return (character_id, nick, groups)

	    except Exception, e:
			print("Fail: {0}".format(e))
			if db:
			    db.close()
			sys.exit(0)
			return (-1, None, None)
			raise
	    finally:
			if db:
				db.close()

	def createChannel(name, server, id):
		return -2

	def getRegistration(self, id, current=None):
	    return (-2, None, None)

	def registerPlayer(self, name, current=None):
	    print ("Warn: Somebody tried to register player '{0}'".format(name))
	    return -1

	def unregisterPlayer(self, id, current=None):
	    print ("Warn: Somebody tried to unregister player '{0}'".format(id))
	    return -1

	def getRegisteredUsers(self, filter, current=None):
	    return dict()

	def registerUser(self, name, current = None):
	    print ("Warn: Somebody tried to register user '{0}'".format(name))
	    return -1

	def unregisterUser(self, name, current = None):
	    print ("Warn: Somebody tried to unregister user '{0}'".format(name))
	    return -1

	def idToTexture(self, id, current=None):
		return None

	def idToName(self, id, current=None):
		return None

	def nameToId(self, name, current=None):
		return id

	def getInfo(self, id, current = None):
		return (False, None)

	def setInfo(self, id, info, current = None):
	    print ("Warn: Somebody tried to set info for '{0}'".format(id))
	    return -1

	def setTexture(self, id, texture, current = None):
	    print ("Warn: Somebody tried to set a texture for '{0}'".format(id))
	    return -1

# -------------------------------------------------------------------------------

if __name__ == "__main__":
    print('Starting authenticator...')

    ice = Ice.initialize(sys.argv)
    meta = Murmur.MetaPrx.checkedCast(ice.stringToProxy('Meta -e 1.0:tcp -h 127.0.0.1 -p 6502'))
    print('established mumur meta')
    adapter = ice.createObjectAdapterWithEndpoints("Callback.Client", "tcp -h 127.0.0.1")
    adapter.activate()

    server = meta.getServer(1)
    print("Binding to server: {0} {1}".format(server.id, server))
    serverR = Murmur.ServerUpdatingAuthenticatorPrx.uncheckedCast(adapter.addWithUUID(ServerAuthenticatorI(server, adapter)))
    server.setAuthenticator(serverR)
    try:
        ice.waitForShutdown()
    except KeyboardInterrupt:
        print 'Aborting!'

    ice.shutdown()
    print '7o'
