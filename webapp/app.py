from flask import Flask
from flask import request
from flask import jsonify
from redis import Redis
redis = Redis(host='redis', port=6379)
redis.set('hits', 0)

import socket

app = Flask(__name__)

@app.route("/")
def index():
    redis.incr('hits')
    return "host: %s - count %s\n" % (socket.gethostname(), redis.get('hits'))

@app.route("/inc", methods=['POST'])
def inc():
    if request.headers['Content-Type'] != 'application/json':
        return 'NOK - json data', 409
    content = request.json
    redis.incr('hits', content['count'])
    return 'OK\n', 201

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
