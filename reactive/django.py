import os
import yaml
import subprocess

from charmhelpers.core.hookenv import (
    status_set,
    open_port,
    config,
)

from charmhelpers.core.templating import render
from charmhelpers.core.host import (
    adduser,
    service_restart,
    service_running,
    service_start,
)

from charmhelpers.fetch import install_remote

from charms import apt
from charms.layer import django

from charms.reactive import (
    hook,
    when,
    when_not,
    is_state,
    set_state,
    remove_state,
)


@when_not('django.installed')
def install():
    adduser('django')
    dcfg = django.config()
    status_set('maintenance', 'installing deps')
    apt.queue_install(dcfg.get('apt-packages', []))

    subprocess.check_call([django.pip(), 'install', 'circus', 'gunicorn', ])
    source_install(dcfg)
    open_port(config('django-port'))
    set_state('django.installed')
    start()

@when('django.ready')
@when('website.available')
def send_port(http):
    http.configure(80)


@when('django.source.available')
@when_not('postgres.connected')
def postgres_blocked():
    status_set('blocked', 'postgres database required')


@when('postgres.database.available')
@when('django.source.available')
@when_not('django.configured')
def connect_db(pgsql):
    dcfg = django.config()

    apt_install(['python-psycopg2'])

    ctx = {
        'database': pgsql,
        'debug': config('django-debug'),
        'settings_import': dcfg.get('settings-import', '.settings'),
        'media_path': os.path.join(dcfg.get('source-path'),
                                   dcfg.get('media-path')),
        'static_path': os.path.join(dcfg.get('source-path'),
                                   dcfg.get('static-path')),
    }

    off = 0 # Offset
    import_settings = dcfg.get('settings-import', '.settings')
    if import_settings.startswith('.'):
        off = 1

    cfg_path = os.path.dirname(import_settings[off:].replace('.', '/'))
    settings_cfg = os.path.join(dcfg.get('source-path'), cfg_path, 'juju.py')

    status_set('maintenance', 'writing Django settings')

    render(source='local.py.j2',
           target=settings_cfg,
           owner='django',
           group='django',
           perms=0o644,
           context=ctx)

    dcfg.set('config-path',
             os.path.join(dcfg.get('source-path'), cfg_path, 'juju.py'))
    dcfg.set('config-import', '.'.join([cfg_path, 'juju']))

    source_install(dcfg)
    set_state('django.configured')


@when('django.configured')
@when_not('django.available')
def load_data():
    django.manage(['migrate', '--noinput'])
    set_state('django.available')


@when('django.ready')
@when_not('circus.running')
def start():
    if service_running('circus'):
        service_restart('circus')
    else:
        service_start('circus')

    set_state('circus.running')


@when('django.ready')
@when('django.restart')
def restart():
    remove_state('circus.running')
    start()
    remove_state('django.restart')


def source_install(dcfg):
    source = dcfg.get('source', {})
    status_set('maintenance', 'installing %s repo' % source['url'])
    if not os.path.exists(dcfg.get('install-path')):
        os.makedirs(dcfg.get('install-path'))

    source_path = install_remote(source['url'],
                                 dest=dcfg.get('install-path'))

    dcfg.set('source-path', source_path)

    status_set('maintenance', 'installing project deps')
    if dcfg.get('pip-requirements'):
        django.call([django.pip(), 'install', '-r',
                     dcfg.get('pip-requirements')])

    render(source='circus.ini.j2',
           target='/etc/circus.ini',
           owner='root',
           group='root',
           perms=0o644,
           context={
            'install_path': source_path,
            'wsgi': dcfg.get('wsgi'),
            'port': config('django-port'),
            'config_import': dcfg.get('config-import'),
        })

    render(source='circus.conf.j2',
           target='/etc/init/circus.conf',
           owner='root',
           group='root',
           perms=0o644,
           context={})

    set_state('django.source.available')
    set_state('django.restart')
