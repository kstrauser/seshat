#!/usr/bin/env python

# Copyright 2011 Daycos

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see
# <http://www.gnu.org/licenses/>.

"""This module implements the broker bot portion of the Seshat system

It handles chat requests and relays conversations between web visitors
and defined Jabber accounts."""

import logging
import re
import time
import xmpp
from collections import namedtuple

import sqlitebackend

MODULELOG = logging.getLogger(__name__)

# This stores the list of methods decorated by _handlecommand
COMMANDPATTERNS = []
COMMANDDEF = namedtuple('CommandDefinition', ('function', 'pattern', 'help'))

def _handlecommand(pattern):
    """Associate the decorated function with the given regular
    expression. All commands start with '!', followed immediately by
    the pattern, then optional whitespace until the end of the
    line."""
    def register(function):
        """Register the function"""
        MODULELOG.debug("Registering %s to handle %s" % (function, pattern))
        COMMANDPATTERNS.append(COMMANDDEF(function, re.compile('^!%s\s*$' % pattern, re.IGNORECASE), function.__doc__))
        return function
    return register

class SeshatServer(sqlitebackend.SqliteBackend):
    """The broker bot acts as an intermediary between a web chat and a
    Jabber session. It passes messages both ways and handles all
    bookkeeping."""
    
    #### Public methods

    def __init__(self, username, password, localusers, sqlitedb):
        """Establish a connection to a Jabber server and prepare to
        manage it"""
        super(SeshatServer, self).__init__(sqlitedb)
        
        self.localusers = localusers
        self.password = password
        self.jid = xmpp.protocol.JID(username)
        self.xmppserver = self.jid.getDomain()

        # Set all users to offline. Their real status will be updated
        # by _presencehandler as soon as we connect and send our
        # presence.
        self._clearonlineusers()
        self.online = {}
        for localuser in self.localusers:
            self.online[localuser] = False
            self._setonlinestatus(localuser, False)
        
        # Establish a Jabber connection
        self.client = xmpp.Client(self.xmppserver, debug=[])
        self._connect()
        self.client.RegisterHandler('message', self._messagehandler)
        self.client.RegisterHandler('presence', self._presencehandler)

    def run(self):
        """Continually handle events until an error occurs"""
        while True:
            # Look for new chat requests and notify all online
            # localusers of each one
            for chat in self._getchatswithstatus(self.STATUS_WAITING):
                availableusers = self._getavailablelocalusers()
                if availableusers:
                    message = "Remote user '%s' wants to start a conversation." % chat.remoteuser
                    if chat.startmessage:
                        message += " The starting message is: '%s'" % chat.startmessage
                    message += " To accept this request, reply with the message '!ACCEPT %d'." % chat.chatid
                    for localuser in availableusers:
                        basemessage = message
                        if len(availableusers) > 1:
                            message += " Requests were also sent to: %s." % ', '.join(user for user in availableusers if user != localuser)
                        self._localsend(localuser, message)
                        MODULELOG.info("A chat request from %s was sent to %s" % (chat.remoteuser, localuser))
                        message = basemessage
                    self._setchatstatus(chat.chatid, self.STATUS_NOTIFIED)
                else:
                    self._queueremote(chat.chatid, "No one is available to answer your chat request right now.")
                    self._setchatstatus(chat.chatid, self.STATUS_FAILED)

            # Look for new queued messages for localusers and send them
            for message in self._getallqueuedlocalmessages():
                self._localsend(message.localuser, message.message)
                MODULELOG.info("%s said to %s in chat #%d: '%s'", message.remoteuser, message.localuser, message.chatid, message.message)
                self._markmessagesent(message.messageid)
            
            if self.client.Process(1) == 0:
                MODULELOG.info("Disconnected from the server. Reconnecting soon.")
                time.sleep(20)
                self._connect()


    #### Internal methods
                
    def _connect(self):
        """Connect to the Jabber server"""
        self.client.connect()
        self.client.auth(self.jid.getNode(), self.password)
        self.client.sendInitPresence()

    def _replywithhelp(self, localuser, message):
        """Append a help text to the end of the message, then send
        it"""
        self._localsend(localuser, message + " Send '!HELP' for more options.")

    def _localsend(self, localuser, message):
        """Send a Jabber message to the localuser"""
        self.client.send(xmpp.protocol.Message(localuser, message, typ='chat'))


    #### Event handlers
        
    def _messagehandler(self, con, event):
        """Handle an incoming message from a localuser"""
        if event.getType() not in ['message', 'chat', None]:
            return
        localuser = event.getFrom().getStripped()
        message = event.getBody()
        for pattern in COMMANDPATTERNS:
            matchresult = pattern.pattern.match(message)
            if matchresult is not None:
                pattern.function(self, localuser, *matchresult.groups())
                return
        currentchat = self._getlocaluserchat(localuser)
        if currentchat is None:
            self._localsend(localuser, "You are not currently in a chat. Send '!WAITING' to see a list of available chats, or '!HELP' for other options.")
            return
        self._queueremote(currentchat.chatid, message)
        MODULELOG.info("%s said to %s in chat #%d: '%s'", localuser, currentchat.remoteuser, currentchat.chatid, message)

    def _presencehandler(self, con, presence):
        """Update a localuser's online status"""
        localuser = presence.getFrom().getStripped()
        if localuser not in self.localusers:
            return
        online = presence.getType() != 'unavailable' and presence.getShow() is None
        MODULELOG.debug("%s changed status to '%s'" % (localuser, 'online' if online else 'offline'))
        self.online[localuser] = online
        self._setonlinestatus(localuser, online)

    #### Command handlers - these act on commands from localusers

    @_handlecommand('ACCEPT (\d+)')
    def _command_accept(self, localuser, chatid):
        """!ACCEPT n - Accept chat request #n"""
        chatid = int(chatid)

        # Don't let users accept more than one chat
        currentchat = self._getlocaluserchat(localuser)
        if currentchat is not None:
            self._replywithhelp(localuser, "You are already handling chat #%d with %s." % (currentchat.chatid, currentchat.remoteuser))
            return
        
        chatinfo = self._getchatinfo(chatid)
        if chatinfo is None:
            self._replywithhelp(localuser, "Chat #%d does not exist." % chatid)
            return
        if chatinfo.status == self.STATUS_OPEN:
            if chatinfo.localuser == localuser:
                self._replywithhelp(localuser, "You are already handling chat #%d." % chatid)
                return
            self._replywithhelp(localuser, "Chat #%d is already handled by %s." % (chatid, chatinfo.localuser))
            return
        if chatinfo.status == self.STATUS_CLOSED:
            self._replywithhelp(localuser, "Chat #%d is already finished." % chatid)
            return
        self._acceptchat(chatid, localuser)
        self._localsend(localuser, "You are now handling chat #%d. Send '!FINISH' when you are done." % chatid)
        self._queueremote(chatid, "Your chat has started.")
        MODULELOG.info("%s accepted chat #%d with %s" % (localuser, chatinfo.chatid, chatinfo.remoteuser))

    @_handlecommand('CANCEL (\d+)')
    def _command_cancel(self, localuser, chatid):
        """!CANCEL n - Cancel chat request #n"""
        chatid = int(chatid)
        chatinfo = self._getchatinfo(chatid)
        if chatinfo is None:
            self._replywithhelp(localuser, "Chat #%d does not exist." % chatid)
            return
        if chatinfo.status == self.STATUS_OPEN:
            if chatinfo.localuser == localuser:
                self._replywithhelp(localuser, "You have already accepted chat #%d. Send '!FINISH' to close it." % chatid)
            else:
                self._replywithhelp(localuser, "Chat #%d has already been accepted by %s." % (chatid, chatinfo.localuser))
            return
        if chatinfo.status == self.STATUS_CLOSED:
            self._replywithhelp(localuser, "Chat #%d is already closed." % chatid)
            return
        self._closechat(chatid, self.STATUS_CANCELEDLOCALLY)
        self._localsend(localuser, "You canceled chat #%d." % chatid)
        self._queueremote(chatid, "Your chat was canceled.")
        MODULELOG.info("%s canceled chat #%d" % (localuser, chatid))
        
    @_handlecommand('FINISH')
    def _command_finish(self, localuser):
        """!FINISH - Close your current chat"""
        currentchat = self._getlocaluserchat(localuser)
        if currentchat is None:
            self._replywithhelp(localuser, "You are not currently active in a chat.")
            return
        self._closechat(currentchat.chatid, self.STATUS_CLOSED)
        self._localsend(localuser, "The chat is now closed.")
        self._queueremote(currentchat.chatid, "The chat is now closed.")

    @_handlecommand('HELP')
    def _command_help(self, localuser):
        """!HELP - Show available commands"""
        self._localsend(localuser,
                        "Available options:\n" + '\n'.join(sorted(pattern.help for pattern in COMMANDPATTERNS)))

    @_handlecommand('STATUS')
    def _command_status(self, localuser):
        """!STATUS - Show your current chat status"""
        currentchat = self._getlocaluserchat(localuser)
        if currentchat is None:
            self._replywithhelp(localuser, "You are not in a chat.")
        else:
            self._localsend(localuser, "You are in chat #%d with %s. Send '!FINISH' when you are done." % (
                    currentchat.chatid, currentchat.remoteuser))
        
    @_handlecommand('WAITING')
    def _command_waiting(self, localuser):
        """!WAITING - Show all open chat requests"""
        waitingchats = self._getchatswithstatus(self.STATUS_WAITING) + self._getchatswithstatus(self.STATUS_NOTIFIED)
        if not waitingchats:
            self._localsend(localuser, "There aren't any open chat requests.""")
        else:
            chats = '\n'.join('%s | %s' % (chat.chatid, chat.remoteuser) for chat in waitingchats)
            self._localsend(localuser,
                           "Chats waiting to be accepted:\n\n"
                           "ID | Remote user\n"
                           "---|------------------\n%s\n\n"
                           "Send '!ACCEPT n' to accept a chat request. "
                           "Send '!CANCEL n' to cancel a chat request." % chats)
        MODULELOG.info("%s asked for a list of waiting chats" % localuser)

def main(configfile, section):
    """Launch a broker bot using settings found in the named
    configuration (.ini) file, in the specified section"""
    import ConfigParser
    
    logging.basicConfig()
    logging.getLogger('').setLevel(logging.DEBUG)
    config = ConfigParser.ConfigParser()
    config.read(configfile)
    setting = {}

    # Prefer keys named like "seshat_username", but fall back to
    # "username" if they don't exist. This is so that Seshat settings
    # can be embedded in Pyramid config files with little risk of
    # conflicts.
    for key in ('username', 'password', 'localusers', 'sqlitedb'):
        try:
            setting[key] = config.get(section, 'seshat_%s' % key)
        except ConfigParser.NoOptionError:
            setting[key] = config.get(section, '%s' % key)
    setting['localusers'] = [localuser.strip() for localuser in setting['localusers'].split(',')]
    SeshatServer(setting['username'], setting['password'], setting['localusers'], setting['sqlitedb']).run()
        
if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        print "You must give a config file and section name"
        sys.exit()
    main(sys.argv[1], sys.argv[2])
