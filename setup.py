from distutils.core import setup

setup(
    name = 'Seshat',
    version = '0.3.1',
    packages=['seshat'],
    description = 'Sessioned chat system linking Ajax web interfaces with internal Jabber services',
    author='Kirk Strauser',
    author_email='kirk@strauser.com',
    url='https://github.com/kstrauser/seshat',
    long_description='Seshat provides a simple method for adding real-time chat windows to your (Pyramid) web applications so that visitors can easily talk to any of a configured set of Jabber users. An example use would be allowing customers to chat with internal customer service representatives. The name is short for "sessioned chat", and resemblence to the Egyptian goddess of wisdom, knowledge, and writing is coincidental.',
    keywords=['jabber', 'xmpp', 'chat', 'pyramid', 'ajax'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: No Input/Output (Daemon)',
        'Environment :: Web Environment',
        'Framework :: BFG',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.4',
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Communications :: Chat',
        'Topic :: Internet :: WWW/HTTP',
        ],
    install_requires=['xmpppy'],
    data_files=[('', ['example.ini'])],
    package_data={'seshat': ['pyramid/*']},
        )
