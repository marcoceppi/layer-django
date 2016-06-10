import os
import yaml
import subprocess

from charmhelpers.core.unitdata import kv
from charmhelpers.core.hookenv import status_set
from charms import layer

def config():
    db = kv()

    if os.path.exists('django.yaml'):
        with open('django.yaml') as f:
            django_cfg = yaml.safe_load(f.read())
    else:
        django_cfg = layer.options('django')

    for k, v in django_cfg.items():
        db.set(k, v)

    return db


def manage(cmd):
    dcfg = config()
    if not isinstance(cmd, list):
        cmd = cmd.split(' ')

    exe = [python(), 'manage.py']
    extra = []
    if dcfg.get('config-import'):
        extra.append('--settings=%s' % dcfg.get('config-import'))

    status_set('maintenance', ' '.join(['manage.py'] + cmd))
    call(exe + cmd + extra)

def call(cmd):
    dcfg = config()
    subprocess.check_call(cmd, cwd=dcfg.get('source-path'))


def pip():
    return config().get('pip', '/usr/bin/pip')


def python():
    return config().get('python', '/usr/bin/python')
