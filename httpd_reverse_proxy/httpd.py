import argparse
import subprocess
import time
import logging
import os
from collections import namedtuple
from collections import defaultdict

import docker
import pystache

HTTPD_LB_TEMPLATE = """ServerRoot "/usr/local/apache2/"
DefaultRuntimeDir "/usr/local/apache2/"
PidFile "/var/tmp/httpd.pid"
ServerName {{lb_host}}
Listen {{lb_port}}
Mutex posixsem proxy
Mutex posixsem proxy-balancer-shm
LoadModule authz_core_module   modules/mod_authz_core.so
LoadModule slotmem_shm_module  modules/mod_slotmem_shm.so
LoadModule status_module       modules/mod_status.so
LoadModule proxy_module        modules/mod_proxy.so
LoadModule proxy_balancer_module        modules/mod_proxy_balancer.so
LoadModule proxy_http_module  modules/mod_proxy_http.so
LoadModule lbmethod_byrequests_module modules/mod_lbmethod_byrequests.so
LoadModule unixd_module        modules/mod_unixd.so
ErrorLog "/var/log/httpd.log"
LogLevel debug
ProxyPass /server-status !
<Location /server-status>
    SetHandler server-status
</Location>
ProxyPass /balancer-manager !
<Location "/balancer-manager">
    SetHandler balancer-manager
</Location>

{{#backends}}
ProxyPass /{{url}} balancer://backends_{{key}}/{{url}}
<Proxy balancer://backends_{{key}}>
    BalancerMember http://{{host}}:{{port}}
</Proxy>
{{/backends}}
"""

Backend = namedtuple('Backend', ['name', 'port'])

def coroutine(f):
    def wrapper(*args, **kw):
        c = f(*args, **kw)
        c.send(None)
        return c
    return wrapper


def httpd(action):
    if action == 'start':
        logging.info('starting httpd')
        subprocess.call('/usr/local/apache2/bin/httpd -f /usr/local/apache2/conf/httpd.conf -k start', shell=True)
    elif action == 'stop':
        logging.info('stopping httpd')
        subprocess.call('/usr/local/apache2/bin/httpd -f /usr/local/apache2/conf/httpd.conf -k stop', shell=True)
    elif action == 'restart':
        logging.info('restarting httpd')
        subprocess.call('kill -10 $(cat /var/tmp/httpd.pid)', shell=True)


def retrieve_proxied_backends():
    backends = []
    client = docker.from_env()
    for container in client.containers.list():
        if 'Env' in container.attrs['Config']:
            env_vars = defaultdict(lambda: '', dict(env.split('=', 1) for env in container.attrs['Config']['Env']))
            if 'PROXY' in env_vars and env_vars['PROXY'] == 'true':
                backends.append({
                    'url': env_vars['PROXY_URL'],
                    'key': env_vars['PROXY_SERVICE_NAME'],
                    'host': container.name,
                    'port': container.attrs['NetworkSettings']['Ports'].keys()[0].split('/')[0] # FIXME what if a container exposes multiple ports ? ...
                })
    return backends


def configure_httpd_conf(backends, lb_host, lb_port):
    with open('/usr/local/apache2/conf/httpd.conf', 'w') as conf:
        conf.write(pystache.render(HTTPD_LB_TEMPLATE, {'backends':backends, 'lb_host':lb_host, 'lb_port': lb_port}))


def listen_to_docker_events_and_notify(target):
    logging.info('starting the listener')
    client = docker.from_env()
    while True:
        for event in client.events(decode=True):
            try:
                logging.debug(event)
                if 'status' in event and event['status'] in ['start', 'die'] and event['Action'] in ['start', 'die']:
                    target.send((event['Action'], event['Actor']['Attributes']['name']))
            except StopIteration:
                pass
            except:
                logging.exception('unable to process [%s]', event)


@coroutine
def trigger_reconfiguration(host, port):
    client = docker.from_env()
    while True:
        action, container = yield
        logging.info('Received reconfiguration trigger after [%s]:[%s]', action, container)
        time.sleep(2)
        configure_httpd_conf(retrieve_proxied_backends(), host, port)
        httpd('restart')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-x', '--host', action='store', default='127.0.0.1')
    parser.add_argument('-p', '--port', action='store', default=8080, type=int)
    args = vars(parser.parse_args())
    FORMAT = '%(asctime)-15s %(filename)s %(funcName)s - %(levelname)s - %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.DEBUG if args['verbose'] else logging.INFO)
    configure_httpd_conf(retrieve_proxied_backends(), args['host'], args['port'])
    httpd('start')
    listen_to_docker_events_and_notify(trigger_reconfiguration(args['host'], args['port']))
