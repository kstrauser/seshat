#!/usr/bin/env python

"""Allow web visitors to chat with local users logged into a Jabber server"""

from pyramid.security import authenticated_userid
from seshat import client

def getseshatvalues(request):
    """Return a configured Seshat client and the username of the visitor"""
    user = authenticated_userid(request)
    return (client.SeshatClient(request.registry.settings['seshat_sqlitedb']),
            user if user is not None else 'Anonymous')

def chat(request):
    """Get a new chatid and open the chat window"""
    message = 'Coming from page %s' % request.referer if request.referer is not None else None
    seshatclient, user = getseshatvalues(request)
    return {'chatid': seshatclient.startchat(user, message)}

def recvmessage(request):
    """Poll the server for the first queued message in this chat"""
    chatid = int(request.matchdict['chatid'])
    seshatclient, user = getseshatvalues(request)
    message = seshatclient.getmessage(chatid, user)
    if message is None:
        return ''
    return message

def sendmessage(request):
    """Queue the visitor's message for delivery to the chat's localuser"""
    chatid = int(request.matchdict['chatid'])
    seshatclient, user = getseshatvalues(request)
    seshatclient.sendmessage(chatid, user, request.params['text'])
