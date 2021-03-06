from __future__ import unicode_literals
from __future__ import absolute_import
import logging
from .service import Service

log = logging.getLogger(__name__)


def sort_service_dicts(services):
    # Get all services that are dependant on another.
    dependent_services = [s for s in services if s.get('links')]
    flatten_links = sum([s['links'] for s in dependent_services], [])
    # Get all services that are not linked to and don't link to others.
    non_dependent_sevices = [s for s in services if s['name'] not in flatten_links and not s.get('links')]
    sorted_services = []
    # Topological sort.
    while dependent_services:
        n = dependent_services.pop()
        # Check if a service is dependent on itself, if so raise an error.
        if n['name'] in n.get('links', []):
            raise DependencyError('A service can not link to itself: %s' % n['name'])
        sorted_services.append(n)
        for l in n['links']:
            # Get the linked service.
            linked_service = next(s for s in services if l == s['name'])
            # Check that there isn't a circular import between services.
            if n['name'] in linked_service.get('links', []):
                raise DependencyError('Circular import between %s and %s' % (n['name'], linked_service['name']))
            # Check the linked service has no links and is not already in the
            # sorted service list.
            if not linked_service.get('links') and linked_service not in sorted_services:
                sorted_services.insert(0, linked_service)
    return non_dependent_sevices + sorted_services


class Project(object):
    """
    A collection of services.
    """
    def __init__(self, name, services, client):
        self.name = name
        self.services = services
        self.client = client

    @classmethod
    def from_dicts(cls, name, service_dicts, client):
        """
        Construct a ServiceCollection from a list of dicts representing services.
        """
        project = cls(name, [], client)
        for service_dict in sort_service_dicts(service_dicts):
            # Reference links by object
            links = []
            if 'links' in service_dict:
                for service_name in service_dict.get('links', []):
                    links.append(project.get_service(service_name))
                del service_dict['links']
            project.services.append(Service(client=client, project=name, links=links, **service_dict))
        return project

    @classmethod
    def from_config(cls, name, config, client):
        dicts = []
        for service_name, service in list(config.items()):
            service['name'] = service_name
            dicts.append(service)
        return cls.from_dicts(name, dicts, client)

    def get_service(self, name):
        """
        Retrieve a service by name. Raises NoSuchService
        if the named service does not exist.
        """
        for service in self.services:
            if service.name == name:
                return service

        raise NoSuchService(name)

    def get_services(self, service_names=None):
        """
        Returns a list of this project's services filtered
        by the provided list of names, or all services if
        service_names is None or [].

        Preserves the original order of self.services.

        Raises NoSuchService if any of the named services
        do not exist.
        """
        if service_names is None or len(service_names) == 0:
            return self.services
        else:
            unsorted = [self.get_service(name) for name in service_names]
            return [s for s in self.services if s in unsorted]

    def recreate_containers(self, service_names=None):
        """
        For each service, create or recreate their containers.
        Returns a tuple with two lists. The first is a list of
        (service, old_container) tuples; the second is a list
        of (service, new_container) tuples.
        """
        old = []
        new = []

        for service in self.get_services(service_names):
            (s_old, s_new) = service.recreate_containers()
            old += [(service, container) for container in s_old]
            new += [(service, container) for container in s_new]

        return (old, new)

    def start(self, service_names=None, **options):
        for service in self.get_services(service_names):
            service.start(**options)

    def stop(self, service_names=None, **options):
        for service in self.get_services(service_names):
            service.stop(**options)

    def kill(self, service_names=None, **options):
        for service in self.get_services(service_names):
            service.kill(**options)

    def build(self, service_names=None, **options):
        for service in self.get_services(service_names):
            if service.can_be_built():
                service.build(**options)
            else:
                log.info('%s uses an image, skipping' % service.name)

    def remove_stopped(self, service_names=None, **options):
        for service in self.get_services(service_names):
            service.remove_stopped(**options)

    def containers(self, service_names=None, *args, **kwargs):
        l = []
        for service in self.get_services(service_names):
            for container in service.containers(*args, **kwargs):
                l.append(container)
        return l


class NoSuchService(Exception):
    def __init__(self, name):
        self.name = name
        self.msg = "No such service: %s" % self.name

    def __str__(self):
        return self.msg


class DependencyError(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg