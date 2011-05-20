#!/usr/bin/env python

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

"""Client library for the Seshat system

These are all the methods needed for establishing and interacting with
chat sessions"""

import logging

import sqlitebackend

MODULELOG = logging.getLogger(__name__)

class SeshatClient(sqlitebackend.SqliteBackend):
    """Provide an interface for web clients to send and receive
    message, start chats, and otherwise interact with the
    SeshatServer"""
    
    def endchat(self, chatid):
        """Say goodbye"""
        chatinfo = self._getopenchatinfo(chatid)
        if chatinfo is None:
            return
        self._closechat(chatid, self.STATUS_CLOSED)
        self._queuelocal(chatid, "The chat is now closed.")
        self._queueremote(chatid, "The chat is now closed.")

    def getmessage(self, chatid, remoteuser):
        """Get the first queued message for the remoteuser in the given chatid"""
        chatinfo = self._getchatinfo(chatid)
        if chatinfo.remoteuser != remoteuser:
            return
        return self._getfirstqueuedremotemessage(chatid)
    
    def isavailable(self):
        """Returns True if at least one localuser is online, or else False"""
        return bool(self._getavailablelocalusers())

    def sendmessage(self, chatid, remoteuser, message):
        """Send a Jabber message to the chat's localuser. Return True
        if the message was sent, otherwise False."""
        chatinfo = self._getchatinfo(chatid)
        if chatinfo.remoteuser != remoteuser:
            return False
        if chatinfo.status in (self.STATUS_WAITING, self.STATUS_NOTIFIED):
            self._queueremote(chatid, "Your message will be delivered when the chat begins.")
        elif chatinfo.status in (self.STATUS_CLOSED, self.STATUS_FAILED, self.STATUS_CANCELEDLOCALLY):
            self._queueremote(chatid, "This chat is already closed.")
            return False
        self._queuelocal(chatid, message)
        return True

    def startchat(self, remoteuser, message=''):
        """Issue a new chat request and return its chatid"""
        return self._openchat(remoteuser, message)

