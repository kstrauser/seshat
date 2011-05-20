#!/usr/bin/env python

def main(global_config, **settings):

    # ...

    # These routes handle viewing the chat window and sending/receiving messages
    config.add_route('chat', '/chat', view='myapp.views.chat.chat', renderer='myapp:templates/chatwindow.pt')
    config.add_route('chatrecv', '/chat/recvmessage/{chatid}', view='myapp.views.chat.recvmessage', renderer='json')
    config.add_route('chatsend', '/chat/sendmessage/{chatid}', view='myapp.views.chat.sendmessage', renderer='json')
