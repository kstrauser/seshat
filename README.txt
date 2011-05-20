Seshat is a realtime chat system for web applications. It consists of
several components:

* HTML and CSS snippets that you can embed in your web templates. They
describe an Ajax-powered chat interface using
* jQuery, which polls your web application via
* A client library, which uses
* A backend API running on SQLite to talk to
* A "broker bot" which relays messages from the backend to
* An account on any Jabber/XMPP server, which carries on conversations
* A set of other Jabber/XMPP accounts of your choosing.

Or more simply:

    Visitor <-> your website <-> broker bot <-> Jabber server <-> employees

# Status

Seshat works, and all the components needed to build a working web chat
system are present. No unit tests are written yet, but those should come
shortly.

# Requirements

server.py requires xmpppy, which can be installed by `pip install xmpppy`.

# Configuration

The server needs:

* A Jabber username to log in as,
* The password for that account,
* A list of localusers to receive chat requests, and
* The path to a SQLite database (which it will create if it doesn't already
exist).

The client needs:

* The path to a SQLite database (which it will create if it doesn't already
exist).

# Usage

[Docs about adding the HTML to your web app]

Create an account on your Jabber server that the "server.py" broker bot can
log into. This is that account that will send messages to the other accounts
defined in "localusers" in the .ini file.

As a convenience, "server.py" can be run from the command line with the name
of a .ini config file and the name of the section to search for its
settings. This is a complete Seshat config file:

    [Seshat]
    sqlitedb = /tmp/seshat.db
    localusers = joe@example.com, bob@customerservice.example.com
    username = webchat@example.com
    password = mypassword

If it were named "sample.ini", you could run the server with the command
line:

    $ ./server.py sample.ini Seshat

# Chatting

When a visitor opens a chat, the broker bot will send a notification to
every online local user. When one of the users "accepts" the chat, any
message they type into their chat window will be displayed on the visitor's
web page. Anything the visitor types will be relayed to the local user's
chat window. The broker bot responds to several commands which can be
entered into the local user's chat window:

* !ACCEPT n - Accept chat request #n
* !CANCEL n - Cancel chat request #n
* !FINISH - Close your current chat
* !HELP - Show available commands
* !STATUS - Show your current chat status
* !WAITING - Show all open chat requests

New commands are extremely easy to add. If you can write Python code, you
can create your own broker bot commands.

# Example chat session

Lines starting with ">" indicate text sent to the local user. Lines starting
with "<" indicate replies sent to the visitor.

    Visitor clicks a link to start a chat
    > Remote user 'customer' wants to start a conversation. To accept this request, reply with the message '!ACCEPT 42'.
    User types: !ACCEPT 42
    > You are now handling chat #42. Send '!FINISH' when you are done.
    < Your chat has started.
    Visitor types: Hi!
    > Hi!
    User types: Hello, customer.
    < Hello, customer.
    Visitor types: Talk to you later!
    > Talk to you later!
    User types: !FINISH
    > The chat is now closed.
    < The chat is now closed.

# About

Seshat was written by Kirk Strauser <kirk@strauser.com> for his employer,
Daycos <http://www.daycos.com/> and released as an open source project with
the permission of Brandon Day.

The name is short for "Sessioned Chat", and refers to the fact that all
conversations are assigned unique "chatid" identifiers, so that many
visitors can chat with many internal users at the same time without
interfering with each other.

Seshat is also the name of the Egyption goddess of wisdom, knowledge, and
writing. This is pure coincidence.

# Credits

Inspiration for building the chat window (and bits of HTML and CSS) came
from:

http://net.tutsplus.com/tutorials/javascript-ajax/how-to-create-a-simple-web-based-chat-application/

# License

The standalone broker bot uses the GPL-licensed xmpppy library, and is thus
also distributed under the GPL (v3 or later).

The client library and SQLite backend are distributed under the terms of the
BSD License.

The practical effect of the distinction is that you can use the Seshat
system in your own web application without licensing that application under
the GPL.
