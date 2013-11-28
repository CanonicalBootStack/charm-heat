#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Yolanda Robla <yolanda.robla@canonical.com>
#

from collections import OrderedDict

from charmhelpers.contrib.openstack import context, templating

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_install_source,
    os_release)

from charmhelpers.fetch import (
    apt_install,
    apt_update,
)

from charmhelpers.core.hookenv import (
    log
)

import heat_context

TEMPLATES = 'templates/'

BASE_PACKAGES = [
    'python-keystoneclient',
    'uuid',
]

BASE_SERVICES = [
    'heat-api',
    'heat-api-cfn',
    'heat-engine'
]

API_PORTS = {
    'heat-api-cfn': 8000,
    'heat-api': 8004
}

HEAT_CONF = '/etc/heat/heat.conf'
HEAT_API_PASTE = '/etc/heat/api-paste.ini'

CONFIG_FILES = OrderedDict([
    (HEAT_CONF, {
        'services': BASE_SERVICES,
        'contexts': [context.AMQPContext(),
                     context.SharedDBContext(relation_prefix='heat'),
                     context.OSConfigFlagContext(),
                     context.IdentityServiceContext()]
    }),
    (HEAT_API_PASTE, {
        'services': [s for s in BASE_SERVICES if 'api' in s],
        'contexts': [context.IdentityServiceContext()],
    })
])

def register_configs():
    release = os_release('heat-engine')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    confs = [HEAT_CONF, HEAT_API_PASTE]
    for conf in confs:
        configs.register(conf, CONFIG_FILES[conf]['contexts'])

    return configs


def api_port(service):
    return API_PORTS[service]


def determine_packages():
    # currently all packages match service names
    packages = BASE_PACKAGES + BASE_SERVICES
    return list(set(packages))


def do_openstack_upgrade(configs):
    """
    Perform an uprade of heat.  Takes care of upgrading packages,
    rewriting configs and potentially any other post-upgrade
    actions.

    :param configs: The charms main OSConfigRenderer object.

    """
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)

    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]
    apt_update()
    packages = BASE_PACKAGES + BASE_SERVICES
    apt_install(packages=packages, options=dpkg_opts, fatal=True)

    # set CONFIGS to load templates from new release and regenerate config
    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()


def restart_map():
    '''
    Determine the correct resource map to be passed to
    charmhelpers.core.restart_on_change() based on the services configured.

    :returns: dict: A dictionary mapping config file to lists of services
                    that should be restarted when file changes.
    '''
    _map = []
    for f, ctxt in CONFIG_FILES.iteritems():
        svcs = []
        for svc in ctxt['services']:
            svcs.append(svc)
        if svcs:
            _map.append((f, svcs))
    return OrderedDict(_map)