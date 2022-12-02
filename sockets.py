#!/usr/bin/env python
# coding: utf-8
# Copyright (c) 2013-2014 Abram Hindle
# Copyright (c) 2022 Michael Huang
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import json

from flask import Flask, request, render_template
from flask_sockets import Sockets
from geventwebsocket.exceptions import WebSocketError
from time import sleep

app = Flask(__name__, template_folder='static')
app.debug = True

sockets = Sockets(app)

class World:
    __slots__ = ['listeners', 'space']

    def __init__(self):
        self.clear()
        # we've got listeners now!
        self.listeners = []

    def add_set_listener(self, listener):
        self.listeners.append(listener)

    def update(self, entity, key, value):
        entry = self.space.get(entity, {})
        entry[key] = value
        self.space[entity] = entry
        self.update_listeners(entity)

    def set(self, entity, data):
        self.space[entity] = data
        self.update_listeners(entity)

    def update_listeners(self, entity):
        '''update the set listeners'''
        for listener in self.listeners:
            listener(entity, self.get(entity))

    def clear(self):
        self.space = {}

    def get(self, entity):
        return self.space.get(entity, {})

    def world(self):
        return self.space

myWorld = World()
subscribers = []

def set_listener(entity, data):
    '''Update all listening websockets'''
    # Can't send entity without name as receiving order is not guaranteed
    for subscriber in subscribers:
        try:
            subscriber.send(json.dumps({entity: data}))
        except WebSocketError as e:
            print(e)

myWorld.add_set_listener(set_listener)

@app.route('/')
def hello():
    '''Show main content'''
    return render_template('index.html')

def read_ws(ws, client):
    '''A greenlet function that reads from the websocket and updates the world'''
    # Read websocket updates
    data = ws.receive()
    if data is None:
        return  # Connection closed

    try:
        world = json.loads(data)
        for entity in world:
            name = entity
            myWorld.set(name, world[entity])
    except json.JSONDecodeError:
        # Bad/No response; do nothing
        return print('Bad JSON received')

@sockets.route('/subscribe')
def subscribe_socket(ws):
    '''Fufill the websocket URL of /subscribe, every update notify the
       websocket and read updates from the websocket'''
    # NOTE: This function runs on its own worker thread
    subscribers.append(ws)

    # Send all existing entities
    for entity, data in myWorld.world():
        ws.send(json.dumps({entity: data}))

    try:
        while True:  # Keep socket alive
            sleep(0.1)
            read_ws(ws, None)
            # TODO: Handle socket timeout
    finally:
        ws.close()

# I give this to you, this is how you get the raw body/data portion of a post in flask
# this should come with flask but whatever, it's not my project.
def flask_post_json():
    '''Ah the joys of frameworks! They do so much work for you
       that they get in the way of sane operation!'''
    if (request.json != None):
        return request.json
    elif (request.data != None and request.data.decode() != u''):
        return json.loads(request.data.decode())
    else:
        return json.loads(request.form.keys()[0])

@app.route("/entity/<entity>", methods=['POST', 'PUT'])
def update(entity):
    '''update the entities via this interface'''
    # Assumes entities don't have an enforced schema
    # Assumes request data is json-compatible
    data = request.json if request.json else {}
    if request.method == 'POST':
        myWorld.set(entity, data)
    elif request.method == 'PUT':
        if (type(data) is not dict):
            # Will not be tested for
            return

        for key, val in data.items():
            myWorld.update(entity, key, val)

    return data

@app.route("/world", methods=['GET', 'POST'])
def world():
    '''Return the world'''
    # No specification on handling differences for GET and POST so just return world
    return myWorld.world()

@app.route("/entity/<entity>")
def get_entity(entity):
    '''This is the GET version of the entity interface, return a representation of the entity'''
    return myWorld.get(entity)

@app.route("/clear", methods=['GET', 'POST'])
def clear():
    '''Clear the world out!'''
    # Again, no specification on handling POST and GET so both behave the same
    myWorld.clear()
    return myWorld.world()


if __name__ == "__main__":
    ''' This doesn't work well anymore:
        pip install gunicorn
        and run
        gunicorn -k flask_sockets.worker sockets:app
    '''
    app.run()
