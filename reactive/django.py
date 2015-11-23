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

from charmhelpers.fetch import (
    apt_install,
    install_remote,
)

from charms import django
from charms.reactive import (
    hook,
    when,
    is_state,
    set_state,
    remove_state,
)


@hook('install', 'config-changed')
def install():
    adduser('django')
    dcfg = django.config()
    status_set('maintenance', 'installing system deps')
    apt_install(['build-essential', 'binutils-doc', 'autoconf', 'authbind',
                 'bison', 'libjpeg-dev', 'libfreetype6-dev', 'zlib1g-dev',
                 'libzmq3-dev', 'libgdbm-dev', 'libncurses5-dev', 'automake',
                 'libtool', 'libffi-dev', 'curl', 'git', 'gettext', 'flex',
                 'postgresql-client', 'postgresql-client-common', 'python3',
                 'python3-pip', 'python-dev', 'python3-dev', 'python-pip',
                 'libxml2-dev', 'virtualenvwrapper', 'libxslt-dev', 'git-core',
                 'python-git', 'libpq-dev'] + dcfg.get('apt-packages', []))

    subprocess.check_call(['pip', 'install', 'circus', 'gunicorn', ])
    source_install(dcfg)
    open_port(config('django-port'))
    start()


@when('postgres.database.available')
def connect_db(pgsql):
    dcfg = django.config()

    apt_install(['python-psycopg2'])
    status_set('maintenance', 'writing local.py settings')
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
    render(source='local.py.j2',
           target=os.path.join(dcfg.get('source-path'), cfg_path, 'juju.py'),
           owner='django',
           group='django',
           perms=0o644,
           context=ctx)

    dcfg.set('config-path',
             os.path.join(dcfg.get('source-path'), cfg_path, 'juju.py'))
    dcfg.set('config-import', '.'.join([cfg_path, 'juju']))

    if not is_state('django.data-loaded'):
        source_install(dcfg)
        django.manage(['migrate', '--noinput'])
        set_state('django.data-loaded')
        set_state('django.ready')
    start()


@hook('start')
def start():
    if not is_state('django.data-loaded'):
        return

    if service_running('circus'):
        service_restart('circus')
    else:
        service_start('circus')


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
        django.call([dcfg.get('pip', '/usr/bin/pip'), 'install', '-r',
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
