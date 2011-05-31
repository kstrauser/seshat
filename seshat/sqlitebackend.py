#!/usr/bin/env python
# pylint: disable=C0301

# Copyright (c) 2011, Daycos
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials
#       provided with the distribution.
#     * Neither the name of Daycos nor the names of its contributors
#       may be used to endorse or promote products derived from this
#       software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
# <COPYRIGHT HOLDER> BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.

"""Implements Seshat's client-server API using an SQLite database

Although this particular implementation uses SQLite, it makes no
assumptions about the underlying data storage."""

import logging
import sqlite3
import sys
import time

CURRENTDBVERSION = 1
    
MODULELOG = logging.getLogger(__name__)

CREATEQUERIES = [
    "CREATE TABLE chat (chatid INTEGER PRIMARY KEY, localuser TEXT, remoteuser TEXT, starttime INTEGER, endtime INTEGER, status INTEGER, startmessage TEXT)",
    "CREATE TABLE localmessagequeue (messageid INTEGER PRIMARY KEY, posttime INTEGER, sendtime INTEGER, chatid INTEGER, message TEXT)",
    "CREATE TABLE onlinestatus (localuser TEXT, resource TEXT, online INTEGER, PRIMARY KEY (localuser, resource))",
    "CREATE TABLE remotemessagequeue (messageid INTEGER PRIMARY KEY, posttime INTEGER, sendtime INTEGER, chatid INTEGER, message TEXT)",
    "CREATE TABLE dbversion (versionid INTEGER PRIMARY KEY, version INTEGER)",
    "INSERT INTO dbversion (versionid, version) VALUES (1, %d)" % CURRENTDBVERSION,
    ]

class ChatInfo(object):
    """A chat's parameters"""
    def __init__(self, chatid, localuser, remoteuser, starttime, endtime, status, startmessage):
        """This would be a namedtuple, but those aren't available in
        all the versions of Python that Pyramid supports and I'd hate
        to leave someone out over something so trivial."""
        self.chatid = chatid
        self.localuser = localuser
        self.remoteuser = remoteuser
        self.starttime = starttime
        self.endtime = endtime
        self.status = status
        self.startmessage = startmessage

class QueuedMessage(object):
    """Everything needed to represent a message that's been stored for
    delivery to a localuser"""
    def __init__(self, chatid, localuser, remoteuser, messageid, message):
        """See: ChatInfo.__init__.__doc__"""
        self.chatid = chatid
        self.localuser = localuser
        self.remoteuser = remoteuser
        self.messageid = messageid
        self.message = message
        
class SqliteBackend(object):
    """An implementation of the Seshat backend API that stores
    everything in a SQLite database"""

    STATUS_WAITING = 0
    STATUS_NOTIFIED = 1
    STATUS_OPEN = 2
    STATUS_CLOSED = 3
    STATUS_FAILED = 4
    STATUS_CANCELEDLOCALLY = 5

    def __init__(self, sqlitedb):
        """Establish a database connection and create the tables
        necessary tables if they don't already exist"""
        self.dbconn = sqlite3.connect(sqlitedb)
        initdb = False
        try:
            versionquery = self.dbconn.execute('SELECT version FROM dbversion WHERE versionid = 1')
        except sqlite3.OperationalError:
            # If the 'version' table doesn't exist, then this is a new
            # database and needs to be initialized
            MODULELOG.info('Unable to find the database version table')
            initdb = True
        else:
            dbversionrow = versionquery.fetchone()
            if dbversionrow is None:
                MODULELOG.info('Unable to read the database version')
                # A previous initialization didn't get as far as
                # setting the database version. Wierd, but let's
                # handle it rationally.
                initdb = True
            else:
                dbversion = dbversionrow[0]
                if dbversion < CURRENTDBVERSION:
                    localqueuesize = self.dbconn.execute('SELECT count(1) FROM localmessagequeue WHERE sendtime IS NULL').fetchone()[0]
                    remotequeuesize = self.dbconn.execute('SELECT count(1) FROM remotemessagequeue WHERE sendtime IS NULL').fetchone()[0]
                    unclosedchatcount = self.dbconn.execute('SELECT count(1) FROM chat WHERE STATUS IN (?, ?, ?)',
                                                            (self.STATUS_WAITING, self.STATUS_NOTIFIED, self.STATUS_OPEN)).fetchone()[0]
                    message = 'The Seshat database (%s) is out of date. It has %d queued incoming message(s), %d queued outgoing message(s), and %s unclosed chats.' % (
                        sqlitedb,
                        localqueuesize,
                        remotequeuesize,
                        unclosedchatcount)
                    if localqueuesize or remotequeuesize or unclosedchatcount:
                        message += ' Only delete the database file if you are willing to lose the unsent messages and open chats.'
                    else:
                        message += ' You may safely delete the current database file. It will be created automatically the next time you launch the server.'
                    MODULELOG.critical(message)
                    sys.exit(-1)
        if initdb:
            MODULELOG.info('Creating and populating the database')
            for query in CREATEQUERIES:
                try:
                    self.dbconn.execute(query)
                except sqlite3.OperationalError:
                    pass
                else:
                    MODULELOG.debug('Executed: %s', query)

    def _acceptchat(self, chatid, localuser):
        """Open a chat and set its localuser to the given value"""
        self.dbconn.execute("UPDATE chat SET status = ?, localuser = ? WHERE chatid = ?",
                            (self.STATUS_OPEN, localuser, chatid))
        self.dbconn.commit()
            
    def _clearonlineusers(self):
        """Remove the cache of online user information"""
        self.dbconn.execute("DELETE from onlinestatus")
        self.dbconn.commit()

    def _closechat(self, chatid, status):
        """Mark the chat as closed with the given status code"""
        self.dbconn.execute("UPDATE chat SET status = ?, endtime = ? WHERE chatid = ?", (status, time.time(), chatid))
        self.dbconn.commit()
        chatinfo = self._getchatinfo(chatid)
        MODULELOG.info("Chat #%d between %s and %s is closed." % (chatid, chatinfo.localuser, chatinfo.remoteuser))

    def _getallqueuedlocalmessages(self):
        """Return the (possibly empty) list of messages queued for
        delivery to localusers"""
        rows = self.dbconn.execute("SELECT chat.chatid, chat.localuser, chat.remoteuser, localmessagequeue.messageid, localmessagequeue.message FROM chat JOIN localmessagequeue ON chat.chatid = localmessagequeue.chatid WHERE localmessagequeue.sendtime IS NULL AND chat.localuser IS NOT NULL ORDER BY localmessagequeue.messageid").fetchall()
        if rows is None:
            return []
        return [QueuedMessage(*row) for row in rows]
    
    def _getavailablelocalusers(self):
        """Return a list of localusers who are currently online from
        at least one place, but not involved in a chat"""
        chattingusers = self._getchatswithstatus(self.STATUS_OPEN)
        return [row[0] for row in self.dbconn.execute("SELECT DISTINCT localuser FROM onlinestatus WHERE online = 1").fetchall()
                if row[0] not in chattingusers]

    def _getchatinfo(self, chatid):
        """Return all the stored information about a chat"""
        row = self.dbconn.execute("SELECT chatid, localuser, remoteuser, starttime, endtime, status, startmessage FROM chat WHERE chatid = ?",
                                  (chatid,)).fetchone()
        if row is None:
            return None
        return ChatInfo(*row)

    def _getchatswithstatus(self, status):
        """Return the (possibly empty) list of chats with the given status"""
        rows = self.dbconn.execute("SELECT chatid, localuser, remoteuser, starttime, endtime, status, startmessage FROM chat WHERE status = ?", (status,)).fetchall()
        if rows is None:
            return []
        return [ChatInfo(*row) for row in rows]

    def _getfirstqueuedremotemessage(self, chatid):
        """Return the oldest queued message for a chat"""
        # Lock the tables to prevent a race between two clients trying
        # to check messages at the same time. This guarantees that
        # each queued message will be emitted at most one time.
        self.dbconn.execute("BEGIN IMMEDIATE TRANSACTION")
        row = self.dbconn.execute("SELECT messageid, message FROM remotemessagequeue WHERE chatid = ? AND sendtime IS NULL", (chatid,)).fetchone()
        if row is None:
            self.dbconn.rollback()
            return None
        messageid, message = row
        self.dbconn.execute("UPDATE remotemessagequeue SET sendtime = ? WHERE messageid = ?", (time.time(), messageid))
        self.dbconn.commit()
        return message

    def _getlocaluserchat(self, localuser):
        """Return information about the localuser's current open chat,
        if any (otherwise None)"""
        row = self.dbconn.execute("SELECT chatid, localuser, remoteuser, starttime, endtime, status, startmessage FROM chat WHERE localuser = ? AND status = ?",
                                  (localuser, self.STATUS_OPEN)).fetchone()
        if row is None:
            return None
        return ChatInfo(*row)
    
    def _getopenchatinfo(self, chatid):
        """Like _getchatinfo, but only return information if the chat
        is open"""
        chatinfo = self._getchatinfo(chatid)
        if chatinfo is not None and chatinfo.status == self.STATUS_OPEN:
            return chatinfo
        return None
    
    def _markmessagesent(self, messageid):
        """Record the time that the given message was sent"""
        self.dbconn.execute("UPDATE localmessagequeue SET sendtime = ? WHERE messageid = ?", (time.time(), messageid))
        self.dbconn.commit()
    
    def _openchat(self, remoteuser, message=''):
        """Issue a new chat request and return its chatid"""
        self.dbconn.execute("INSERT INTO chat (remoteuser, starttime, status, startmessage) VALUES (?, ?, ?, ?)",
                            (remoteuser, time.time(), self.STATUS_WAITING, message))
        chatid = self.dbconn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.dbconn.commit()
        self._queueremote(chatid, "Your chat request has been sent. Please wait while it is answered.")
        return chatid
    
    def _queuelocal(self, chatid, message):
        """Queue a message for delivery to a localuser"""
        self.dbconn.execute("INSERT INTO localmessagequeue (posttime, chatid, message) VALUES (?, ?, ?)",
                            (time.time(), chatid, message))
        self.dbconn.commit()
        
    def _queueremote(self, chatid, message):
        """Send a web message to the chat's remoteuser"""
        self.dbconn.execute("INSERT INTO remotemessagequeue (posttime, chatid, message) VALUES (?, ?, ?)",
                            (time.time(), chatid, message))
        self.dbconn.commit()

    def _setchatstatus(self, chatid, status):
        """Change the chat's status"""
        self.dbconn.execute("UPDATE chat SET status = ? WHERE chatid = ?", (status, chatid))
        self.dbconn.commit()
        
    def _setonlinestatus(self, localuser, resource, online):
        """Update (or store) the number of accounts where the
        localuser is online. For example, they might be online with
        both their desktop and laptop."""
        online = int(online)
        try:
            self.dbconn.execute("INSERT INTO onlinestatus (localuser, resource, online) VALUES (?, ?, ?)", (localuser, resource, online))
        except sqlite3.IntegrityError:
            self.dbconn.execute("UPDATE onlinestatus SET online = ? WHERE localuser = ? AND resource = ?", (online, localuser, resource))
        self.dbconn.commit()
