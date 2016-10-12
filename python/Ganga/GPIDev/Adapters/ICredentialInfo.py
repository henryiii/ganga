from __future__ import absolute_import

import copy
import os
from abc import ABCMeta, abstractmethod
from datetime import datetime, timedelta
from functools import wraps

import Ganga.Utility.logging

from Ganga.Core.exceptions import CredentialsError

logger = Ganga.Utility.logging.getLogger()

ENABLE_CACHING = True


def cache(method):
    """
    The cache decorator can be applied to any method in an ``ICredentialInfo` subclass.
    It stores the return value of the function in the ``self.cache`` dictionary
    with the key being the name of the function.
    The cache is invalidated if ``os.path.getmtime(self.location)`` returns
    greater than ``self.cache['mtime']``, i.e. if the file has changed on disk

    Not having to call the external commands comes at the cost of calling ``stat()``
    every time a parameter is accessed but this is still a saving of many orders of
    magnitude.
    """
    @wraps(method)
    def wrapped_function(self, *args, **kwargs):

        # If the mtime has been changed, clear the cache
        if ENABLE_CACHING and os.path.exists(self.location):
            mtime = os.path.getmtime(self.location)
            if mtime > self.cache['mtime']:
                self.cache = {'mtime': mtime}
        else:
            self.cache = {'mtime': 0}

        # If entry is missing from cache, repopulate it
        # This will run if the cache was just cleared
        if method.func_name not in self.cache:
            self.cache[method.func_name] = method(self, *args, **kwargs)

        return self.cache[method.func_name]
    return wrapped_function


class ICredentialInfo(object):
    """
    The interface for all credential types.
    Each object covers one credential file exactly.
    The credential file is central to the object and all information is gathered from there.

    These are only created by the store and should not be persisted.
    """
    __metaclass__ = ABCMeta

    def __init__(self, requirements, check_file=False, create=False):
        # type: (ICredentialRequirement, bool, bool) -> None
        """
        Args:
            requirements (ICredentialRequirement): An object specifying the requirements
            check_file: Raise an exception if the file does not exist
            create: Create the credential file

        Raises:
            IOError: If told to wrap a non-existent file
            CredentialsError: If this object cannot satisfy ``requirements``
        """
        super(ICredentialInfo, self).__init__()

        self.cache = {'mtime': 0}

        self.initial_requirements = copy.deepcopy(requirements)  # Store the requirements that the object was created with. Used for creation

        if check_file:
            logger.debug('Trying to wrap %s', self.location)
            if not self.exists():
                raise IOError('Proxy file {path} not found'.format(path=self.location))
            logger.debug('Wrapping existing file %s', self.location)

        if create:
            logger.debug('Making a new one')
            self.create()

        # If the proxy object does not satisfy the requirements then abort the construction
        if not self.check_requirements(requirements):
            raise CredentialsError('Proxy object cannot satisfy its own requirements')

    def __str__(self):
        return '{class_name} at {file_path} : TimeLeft = {time_left}, Valid = {currently_valid}'.format(\
                        class_name=type(self).__name__, file_path=self.location, currently_valid=self.is_valid(), time_left=self.time_left())

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))

    @property
    def location(self):
        # type: () -> str
        """
        The location of the file on disk
        """
        location = self.default_location()
        encoded_ext = self.initial_requirements.encoded()
        if encoded_ext and not location.endswith(encoded_ext):
            location += ':' + encoded_ext

        return location

    @abstractmethod
    def default_location(self):
        # type: () -> str
        """
        Returns the default location for the credential file.
        This is the location that most tools will look for the file
        or where the file is created without specifying anything.
        """
        pass

    @abstractmethod
    def create(self):
        # type: () -> None
        """
        Create a new credential file
        """
        pass

    def renew(self):
        # type: () -> None
        """
        Renew an existing credential file
        """
        self.create()

    def is_valid(self):
        # type: () -> bool
        """
        Is the credential valid to be used
        """
        # TODO We should check that there's more than some minimum time left on the proxy
        return self.time_left() > timedelta()

    @abstractmethod
    def expiry_time(self):
        # type: () -> datetime.datetime
        """
        Returns the expiry time
        """
        pass

    def time_left(self):
        # type: () -> datetime.timedelta
        """
        Returns the time left
        """
        time_left = self.expiry_time() - datetime.now()
        return max(time_left, timedelta())

    def check_requirements(self, query):
        # type: (ICredentialRequirement) -> bool
        """
        Args:
            query (ICredentialRequirement): The requirements to check ourself against

        Checks all requirements.

        Returns:
            ``True`` if we meet all requirements
            ``False`` if even one requirement is not met or if the credential is not valid
        """
        if not self.exists():
            return False
        return all(self.check_requirement(query, requirementName) for requirementName in query._schema.datadict)

    def check_requirement(self, query, requirement_name):
        # type: (ICredentialRequirement, str) -> bool
        """
        Args:
            query (ICredentialRequirement):
            requirement_name (str): The requirement attribute to check

        Returns:
            ``True`` if ``self`` matches ``query``'s ``requirement``.
        """
        requirement_value = getattr(query, requirement_name)
        if requirement_value is None:
            # If this requirementName is unspecified then ignore it
            return True
        logger.debug('\'%s\': \t%s \t%s', requirement_name, getattr(self, requirement_name), requirement_value)
        return getattr(self, requirement_name) == requirement_value

    def exists(self):
        # type: () -> bool
        """
        Does the credential file exist on disk
        """
        return os.path.exists(self.location)

    def __eq__(self, other):
        return self.location == other.location

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.location)