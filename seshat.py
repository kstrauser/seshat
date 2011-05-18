#!/usr/bin/env python

import logging
import re
import sys
import time
import xmpp
import ConfigParser
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

    def __init__(self, configfile):
        """Establish a connection to a Jabber server and prepare to
        manage it"""
        super(SeshatServer, self).__init__(configfile)
        
        self.localusers = [user.strip() for user in self.config.get('Seshat', 'localusers').split(',')]
        self.xmppusername = self.config.get('Seshat', 'xmppusername')
        self.xmpppassword = self.config.get('Seshat', 'xmpppassword')
        self.jid = xmpp.protocol.JID(self.xmppusername)
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
                onlineusers = self._getonlineusers()
                if onlineusers:
                    message = "Remote user %s wants to start a conversation. " \
                        "To accept this request, reply with the message '!ACCEPT %d'." % (chat.remoteuser, chat.chatid)
                    for localuser in onlineusers:
                        basemessage = message
                        if len(onlineusers) > 1:
                            message += " Requests were also sent to: %s" % ', '.join(user for user in onlineusers if user != localuser)
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
        self.client.auth(self.jid.getNode(), self.xmpppassword)
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
        MODULELOG.info("%s accepted chat #%d with %s" % (chatinfo.localuser, chatinfo.chatid, chatinfo.remoteuser))

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
        self._localsend(localuser, "You cancelled chat #%d." % chatid)
        self._queueremote(chatid, "Your chat was cancelled.")
        MODULELOG.info("%s cancelled chat #%d with %s" % (localuser, chatid, chatinfo.remoteuser))
        
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
        MODULELOG.info("%s closed chat #%d with %s" % (localuser, currentchat.chatid, currentchat.remoteuser))

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
        waitingchats = self._getchatswithstatus(self.STATUS_WAITING)
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
        
if __name__ == '__main__':
    if len(sys.argv) != 2:
        print "You must give a config file"
        sys.exit()
    logging.basicConfig()
    MODULELOG.setLevel(logging.DEBUG)
    SeshatServer(sys.argv[1]).run()