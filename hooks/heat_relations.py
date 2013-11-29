#!/usr/bin/python

#
# Copyright 2012 Canonical Ltd.
#
# Authors:
#  Yolanda Robla <yolanda.robla@canonical.com>
#

import os
import shutil
import sys

from subprocess import check_call

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    charm_dir,
    log,
    relation_ids,
    relation_set,
    open_port,
    unit_get
)

from charmhelpers.core.host import (
    restart_on_change
)

from charmhelpers.fetch import (
    apt_install,
    apt_update
)

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available
)

from charmhelpers.contrib.hahelpers.cluster import (
    canonical_url
)

from heat_utils import (
    do_openstack_upgrade,
    restart_map,
    determine_packages,
    register_configs,
    HEAT_CONF,
    HEAT_API_PASTE,
    API_PORTS
)

from charmhelpers.payload.execd import execd_preinstall

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook('install')
def install():
    execd_preinstall()
    configure_installation_source(config('openstack-origin'))
    apt_update()
    apt_install(determine_packages(), fatal=True)

    _files = os.path.join(charm_dir(), 'files')
    if os.path.isdir(_files):
        for f in os.listdir(_files):
            f = os.path.join(_files, f)
            log('Installing %s to /usr/bin' % f)
            shutil.copy2(f, '/usr/bin')

    for key, port in API_PORTS.iteritems():
        open_port(port)


@hooks.hook('config-changed')
@restart_on_change(restart_map())
def config_changed():
    if openstack_upgrade_available('heat-engine'):
        do_openstack_upgrade(CONFIGS)

    if not os.path.isdir('/etc/heat'):
        os.mkdir('/etc/heat')
    CONFIGS.write_all()


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 username=config('rabbit-user'), vhost=config('rabbit-vhost'))


@hooks.hook('amqp-relation-changed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write(HEAT_CONF)


@hooks.hook('shared-db-relation-joined')
def db_joined():
    relation_set(heat_database=config('database'),
                 heat_username=config('database-user'),
                 heat_hostname=unit_get('private-address'))


@hooks.hook('shared-db-relation-changed')
@restart_on_change(restart_map())
def db_changed():
    if 'shared-db' not in CONFIGS.complete_contexts():
        log('shared-db relation incomplete. Peer not ready?')
        return
    CONFIGS.write(HEAT_CONF)
    check_call(['heat-manage', 'db_sync'])


@hooks.hook('identity-service-relation-joined')
def identity_joined(rid=None):
    base_url = canonical_url(CONFIGS)
    api_url = '%s:8004/v1/$(tenant_id)s' % base_url
    cfn_url = '%s:8000/v1' % base_url
    relation_data = {
        'heat_service': 'heat',
        'heat_region': config('region'),
        'heat_public_url': api_url,
        'heat_admin_url': api_url,
        'heat_internal_url': api_url,
        'heat-cfn_service': 'heat-cfn',
        'heat-cfn_region': config('region'),
        'heat-cfn_public_url': cfn_url,
        'heat-cfn_admin_url': cfn_url,
        'heat-cfn_internal_url': cfn_url
    }

    relation_set(relation_id=rid, **relation_data)


@hooks.hook('identity-service-relation-changed')
@restart_on_change(restart_map())
def identity_changed():
    if 'identity-service' not in CONFIGS.complete_contexts():
        log('identity-service relation incomplete. Peer not ready?')
        return
    CONFIGS.write(HEAT_API_PASTE)
    CONFIGS.write(HEAT_CONF)


@hooks.hook('amqp-relation-broken',
            'identity-service-relation-broken',
            'shared-db-relation-broken')
def relation_broken():
    CONFIGS.write_all()


@hooks.hook('upgrade-charm')
def upgrade_charm():
    for r_id in relation_ids('amqp'):
        amqp_joined(relation_id=r_id)


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))


if __name__ == '__main__':
    main()
