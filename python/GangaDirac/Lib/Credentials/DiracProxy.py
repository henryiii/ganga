from __future__ import absolute_import

import os
import subprocess
from datetime import datetime, timedelta

import Ganga.Utility.logging
from Ganga.Core import GangaValueError
from Ganga.Utility.Config import getConfig
from Ganga.GPIDev.Schema import SimpleItem

from Ganga.GPIDev.Adapters.ICredentialInfo import cache
from Ganga.GPIDev.Adapters.ICredentialRequirement import ICredentialRequirement
from Ganga.Core.exceptions import CredentialRenewalError
from Ganga.GPIDev.Credentials.VomsProxy import VomsProxyInfo

from GangaDirac.Lib.Utilities.DiracUtilities import getDiracEnv

logger = Ganga.Utility.logging.getLogger()


class DiracProxyInfo(VomsProxyInfo):
    """
    A wrapper around a DIRAC proxy file
    """

    def __init__(self, requirements, check_file=False, create=False):
        self._shell = None

        super(DiracProxyInfo, self).__init__(requirements, check_file, create)

    def create(self):
        """
        Creates the grid proxy.

        Raises:
            CredentialRenewalError: If the renewal process returns a non-zero value
        """
        group_command = ''
        logger.debug('require ' + self.initial_requirements.group)
        if self.initial_requirements.group:
            group_command = '--group %s --VOMS' % self.initial_requirements.group
        command = 'dirac-proxy-init --strict --out "%s" %s' % (self.location, group_command)
        logger.debug(command)
        self.shell.env['X509_USER_PROXY'] = self.location
        try:
            self.shell.check_call(command)
        except subprocess.CalledProcessError:
            raise CredentialRenewalError('Failed to create DIRAC proxy')
        else:
            logger.debug('Grid proxy {path} created. Valid for {time}'.format(path=self.location, time=self.time_left()))

    @property
    def shell(self):
        if self._shell is None:
            self._shell = super(DiracProxyInfo, self).shell
            self._shell.env.update(getDiracEnv())
        return self._shell

    def destroy(self):
        if os.path.isfile(self.location):
            os.remove(self.location)

    @cache
    def info(self):
        self.shell.env['X509_USER_PROXY'] = self.location
        status, output, message = self.shell.cmd1('dirac-proxy-info --file "%s"' % self.location)
        return output

    @property
    @cache
    def identity(self):
        return self.field('identity')

    @property
    @cache
    def group(self):
        return self.field('DIRAC group')

    @property
    def encodeDefaultProxyFileName(self):
        return self.initial_requirements.encodeDefaultProxyFileName

    @cache
    def expiry_time(self):
        status, output, message = self.shell.cmd1('voms-proxy-info -file "%s" -timeleft' % self.location)
        if status != 0:
            return datetime.now()
        return datetime.now() + timedelta(seconds=int(output))

    def default_location(self):
        base_proxy_name = os.getenv('X509_USER_PROXY') or '/tmp/x509up_u' + str(os.getuid())
        encoded_ext = self.initial_requirements.encoded()
        if encoded_ext:
            return base_proxy_name + ':' + encoded_ext
        else:
            return base_proxy_name


class DiracProxy(ICredentialRequirement):
    """
    An object specifying the requirements of a DIRAC proxy file
    """
    _schema = ICredentialRequirement._schema.inherit_copy()
    _schema.datadict['group'] = SimpleItem(defvalue=None, typelist=[str, None], doc='Group for the proxy')
    _schema.datadict['encodeDefaultProxyFileName'] = \
        SimpleItem(defvalue=True, doc='Should the proxy be generated with the group encoded onto the end of the proxy filename')

    _category = 'CredentialRequirement'

    info_class = DiracProxyInfo

    def __init__(self, **kwargs):
        super(DiracProxy, self).__init__(**kwargs)
        if self.group is None:
            raise GangaValueError('DIRAC Proxy `group` is not set. Set this in ~/.gangarc in `[defaults_DiracProxy]/group`')

    def encoded(self):
        """
        This returns the encoding used to store a unique DIRAC proxy for each group
        """
        my_config = getConfig('defaults_DiracProxy')
        default_group = my_config['group']
        if (my_config['encodeDefaultProxyFileName'] and self.group == default_group) or self.group != default_group:
            return ':'.join(requirement for requirement in [self.group] if requirement)  # filter out the empties
        else:
            return ''

# A single global check for the DIRAC group setting. This will bail out early and safely during plugin loading.
if getConfig('defaults_DiracProxy')['group'] is None:
    raise GangaValueError('DIRAC Proxy `group` is not set. Set this in ~/.gangarc in `[defaults_DiracProxy]/group`')
