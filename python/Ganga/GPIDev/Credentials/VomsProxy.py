from __future__ import absolute_import

import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta

import Ganga.Utility.logging
from Ganga.GPIDev.Schema import SimpleItem
from Ganga.Utility import GridShell
from Ganga.Utility.Config import getConfig

from Ganga.GPIDev.Adapters.ICredentialInfo import ICredentialInfo, cache
from Ganga.GPIDev.Adapters.ICredentialRequirement import ICredentialRequirement
from Ganga.Core.exceptions import CredentialRenewalError, InvalidCredentialError

logger = Ganga.Utility.logging.getLogger()


class VomsProxyInfo(ICredentialInfo):
    """
    A wrapper around a voms proxy file
    """

    def __init__(self, requirements, check_file=False, create=False):
        self._shell = None

        super(VomsProxyInfo, self).__init__(requirements, check_file, create)

    def create(self):
        """
        Creates the grid proxy.

        Raises:
            CredentialRenewalError: If the renewal process returns a non-zero value
        """
        voms_command = ''
        logger.debug('require ' + self.initial_requirements.vo)
        if self.initial_requirements.vo:
            voms_command = '-voms %s' % self.initial_requirements.vo
            if self.initial_requirements.group or self.initial_requirements.role:
                voms_command += ':'
                if self.initial_requirements.group:
                    voms_command += '/%s' % self.initial_requirements.group
                if self.initial_requirements.role:
                    voms_command += '/%s' % self.initial_requirements.role
        logger.debug(voms_command)
        command = 'voms-proxy-init -out "%s" %s' % (self.location, voms_command)
        logger.debug(command)
        try:
            self.shell.check_call(command)
        except subprocess.CalledProcessError:
            raise CredentialRenewalError('Failed to create VOMS proxy')
        else:
            logger.debug('Grid proxy %s created. Valid for %s', self.location, self.time_left())

    @property
    def shell(self):
        if self._shell is None:
            self._shell = GridShell.getShell()
        return self._shell

    def destroy(self):
        self.shell.cmd1('voms-proxy-destroy -file "%s"' % self.location, allowed_exit=[0, 1])

        if os.path.isfile(self.location):
            os.remove(self.location)

    @cache
    def info(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -all -file "%s"' % self.location)
        return output

    def field(self, label):
        # type: (str) -> str
        line = re.search(r'^{0}\s*: (.*)$'.format(label), self.info(), re.MULTILINE)
        if line is None:
            raise InvalidCredentialError()
        return line.group(1)

    @property
    @cache
    def identity(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -identity' % self.location)
        return output.strip()

    @property
    @cache
    def vo(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -vo' % self.location)
        if status != 0:
            return None
        return output.split(':')[0].strip()

    @property
    @cache
    def role(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -vo' % self.location)
        if status != 0:
            return None  # No VO
        vo_list = output.split(':')
        if len(vo_list) <= 1:
            return None  # No command after VO
        return vo_list[1].split('/')[-1].split('=')[-1].strip()

    @property
    @cache
    def group(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -vo' % self.location)
        if status != 0:
            return None  # No VO
        vo_list = output.split(':')
        if len(vo_list) <= 1:
            return None  # No command after VO
        # TODO Make this support multiple groups and subgroups
        group_role_list = vo_list[1].split('/')
        if len(group_role_list) <= 2:
            return None  # No group specified in command
        return group_role_list[-1].strip()

    @cache
    def expiry_time(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -timeleft' % self.location)
        if status != 0:
            return datetime.now()
        return datetime.now() + timedelta(seconds=int(output))

    def default_location(self):
        return os.getenv('X509_USER_PROXY') or os.path.join(tempfile.gettempdir(), 'x509up_u'+str(os.getuid()))


class VomsProxy(ICredentialRequirement):
    """
    An object specifying the requirements of a VOMS proxy file
    """
    _schema = ICredentialRequirement._schema.inherit_copy()
    _schema.datadict['identity'] = SimpleItem(defvalue=None, typelist=[str, None], doc='Identity for the proxy')
    _schema.datadict['vo'] = SimpleItem(defvalue=None, typelist=[str, None], doc='Virtual Organisation for the proxy. Defaults to LGC/VirtualOrganisation')
    _schema.datadict['role'] = SimpleItem(defvalue=None, typelist=[str, None], doc='Role that the proxy must have')
    _schema.datadict['group'] = SimpleItem(defvalue=None, typelist=[str, None], doc='Group for the proxy - either "group" or "group/subgroup"')

    _category = 'CredentialRequirement'

    info_class = VomsProxyInfo

    def __init__(self, **kwargs):
        super(VomsProxy, self).__init__(**kwargs)
        if 'vo' not in kwargs and getConfig('LCG')['VirtualOrganisation']:
            self.vo = getConfig('LCG')['VirtualOrganisation']

    def encoded(self):
        return ':'.join(requirement for requirement in [self.identity, self.vo, self.role, self.group] if requirement)  # filter out the empties
