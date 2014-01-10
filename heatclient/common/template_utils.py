# Copyright 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import urllib
import yaml

from heatclient.common import template_format
from heatclient import exc
from heatclient.openstack.common.py3kcompat import urlutils


def set_template_fields(hc, args, fields):
    if args.template_file:
        tpl = open(args.template_file).read()
        try:
            fields['template'] = template_format.parse(tpl)
        except ValueError as e:
            raise exc.CommandError(
                "Cannot parse template file: %s" % e)
        return args.template_file

    if args.template_url:
        fields['template_url'] = args.template_url
        return args.template_url

    if args.template_object:
        template_body = hc.http_client.raw_request('GET', args.template_object)
        if template_body:
            try:
                fields['template'] = template_format.parse(template_body)
            except ValueError as e:
                raise exc.CommandError(
                    "Cannot parse template file: %s" % e)
        else:
            raise exc.CommandError('Could not fetch template from %s'
                                   % args.template_object)
        return args.template_object

    raise exc.CommandError('Need to specify exactly one of '
                           '--template-file, --template-url '
                           'or --template-object')


def get_file_contents(resource_registry, fields, base_url='',
                      ignore_if=None):
    for key, value in iter(resource_registry.items()):
        if ignore_if and ignore_if(key, value):
            continue

        if base_url != '' and not base_url.endswith('/'):
            base_url = base_url + '/'
        str_url = urlutils.urljoin(base_url, value)
        try:
            fields['files'][str_url] = urlutils.urlopen(str_url).read()
        except urlutils.URLError:
            raise exc.CommandError('Could not fetch %s from the environment'
                                   % str_url)
        resource_registry[key] = str_url


def prepare_environment(env_path):
    if (not urlutils.urlparse(env_path).scheme):
        env_path = urlutils.urljoin(
            'file:', urllib.pathname2url(env_path))
    raw_env = urlutils.urlopen(env_path).read()
    env = yaml.safe_load(raw_env)
    remote = urlutils.urlparse(env_path)
    remote_dir = os.path.dirname(remote.path)
    environment_base_url = urlutils.urljoin(env_path, remote_dir)
    return environment_base_url, env


def process_environment_and_files(fields, env_path):
    if not env_path:
        return

    environment_url, env = prepare_environment(env_path)

    fields['environment'] = env
    fields['files'] = {}

    resolve_environment_urls(fields, environment_url)


def resolve_environment_urls(fields, environment_url):
    rr = fields['environment'].get('resource_registry', {})
    base_url = rr.get('base_url', environment_url)

    def ignore_if(key, value):
        if key == 'base_url':
            return True
        if isinstance(value, dict):
            return True
        if '::' in value:
            # Built in providers like: "X::Compute::Server"
            # don't need downloading.
            return True

    get_file_contents(rr, fields, base_url, ignore_if)

    for res_name, res_dict in iter(rr.get('resources', {}).items()):
        res_base_url = res_dict.get('base_url', base_url)
        get_file_contents(res_dict, fields, res_base_url, ignore_if)
