#!/usr/bin/env python

"""doc"""

import logging

import sqlitebackend

MODULELOG = logging.getLogger(__name__)

class SeshatClient(sqlitebackend.SqliteBackend):
    """Provide an interface for web clients to send and receive
    message, start chats, and otherwise interact with the
    SeshatServer"""
    
    def getmessage(self, chatid):
        """Get the first queued message for the remoteuser in the given chatid"""
        return self._getfirstqueuedremotemessage(chatid)
    
    def isavailable(self):
        """Returns True if at least one localuser is online, or else False"""
        return bool(self._getonlineusers())

    def sendmessage(self, chatid, message):
        """Send a Jabber message to the chat's localuser. Return True
        if the message was sent, otherwise False."""
        if self._getopenchatinfo(chatid) is None:
            return False
        self._queuelocal(chatid, message)
        return True

    def startchat(self, remoteuser):
        """Issue a new chat request and return its chatid"""
        return self._openchat(remoteuser)
