from Ganga.Core import GangaException
from Ganga.GPIDev.Base import GangaObject
from Ganga.GPIDev.Base.Proxy import getName
from Ganga.GPIDev.Schema import Schema, Version, SimpleItem
from Ganga.Utility.logging import getLogger
from fnmatch import fnmatch
import os
import glob
import re

logger = getLogger()
regex = re.compile('[*?\[\]]')


class IGangaFile(GangaObject):

    """IGangaFile represents base class for output files, such as MassStorageFile, LCGSEFile, DiracFile, LocalFile, etc 
    """
    _schema = Schema(Version(1, 1), {'namePattern': SimpleItem(
        defvalue="", doc='pattern of the file name')})
    _category = 'gangafiles'
    _name = 'IGangaFile'
    _hidden = 1

    def __init__(self):
        super(IGangaFile, self).__init__()

    def setLocation(self):
        """
        Sets the location of output files that were uploaded from the WN
        """
        raise NotImplementedError

    def location(self):
        """
        Return list with the locations of the post processed files (if they were configured to upload the output somewhere)
        """
        raise NotImplementedError

    def get(self):
        """
        Retrieves locally all files that were uploaded before that 
        Order of priority about where a file is going to be placed are:
            1) The localDir as defined in the schema
            2) The Job outpudir of the parent job if the localDir is not defined
            3) raise an exception if neither are defined correctly
        """
        if self.localDir:
            if not os.path.isdir(self.localDir):
                msg = "Folder '%s' doesn't exist. Please construct this before 'get'-ing a file." % self.localDir
                logger.error(msg)
                #os.makedirs(self.localDir)
                raise GangaException(msg)
            to_location = self.localDir
        else:
            should_raise = True
            if self._getParent() is not None:
                try:
                    to_location = self.getJobObject().outputdir
                    should_raise = False
                except AssertionError:
                    should_raise = True

            if should_raise:
                msg = "%s: Failed to get file object. Please set the `localDir` parameter and try again. e.g. file.localDir=os.getcwd();file.get()" % getName(self)
                logger.error(msg)
                logger.debug("localDir value: %s" % self.localDir)
                logger.debug("parent: %s" % self._getParent() )
                raise GangaException(msg)

        if not os.path.isfile(os.path.join(to_location, self.namePattern)):
            return self.copyTo(to_location)
        else:
            logger.debug("File: %s already exists, not performing copy" % (os.path.join(to_location, self.namePattern), ))
            return True


    def getSubFiles(self, process_wildcards=False):
        """
        Returns the sub files if wildcards are used
        """
        # should we process wildcards? Used for inputfiles
        if process_wildcards:
            self.processWildcardMatches()

        # if we have subfiles, return that
        if hasattr(self, 'subfiles'):
            return self.subfiles

        return []

    def getFilenameList(self):
        """
        Returns the filenames of all associated files through a common interface
        """
        raise NotImplementedError

    def getWNScriptDownloadCommand(self, indent):
        """
        Gets the command used to download already uploaded file
        """
        raise NotImplementedError

    def put(self):
        """
        Postprocesses (upload) output file to the desired destination from the client
        """
        raise NotImplementedError

    def copyTo(self, targetPath):
        """
        Copy a the file to the local storage using the appropriate file-transfer mechanism
        Args:
            targetPath (str): Target path where the file is to copied to
        """
        raise NotImplementedError

    def getWNInjectedScript(self, outputFiles, indent, patternsToZip, postProcessLocationsFP):
        """
        Returns script that have to be injected in the jobscript for postprocessing on the WN
        """
        raise NotImplementedError

    def processWildcardMatches(self):
        """
        If namePattern contains a wildcard, populate the subfiles property
        """
        raise NotImplementedError

    def _auto_remove(self):
        """
        Remove called when job is removed as long as config option allows
        """
        self.remove()

    def _readonly(self):
        return False

    def _list_get__match__(self, to_match):
        if isinstance(to_match, str):
            return fnmatch(self.namePattern, to_match)
        # Note: type(DiracFile) = ObjectMetaclass
        # type(ObjectMetaclass) = type
        # hence checking against a class type not an instance
        if isinstance(type(to_match), type):
            return issubclass(self.__class__, to_match)
        return to_match == self

    def execSyscmdSubprocess(self, cmd):

        import subprocess

        exitcode = -999
        mystdout = ''
        mystderr = ''

        try:
            child = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (mystdout, mystderr) = child.communicate()
            exitcode = child.returncode
        finally:
            pass

        return (exitcode, mystdout, mystderr)

    def remove(self):
        """
        Objects should implement something to overload this!
        """
        raise NotImplementedError

    def accessURL(self):
        """
        Return the URL including the protocol used to access a file on a certain storage element
        """
        raise NotImplementedError

    def hasMatchedFiles(self):
        """
        Return if this file has got valid matched files. Default implementation checks for
        subfiles and locations
        """

        # check for subfiles
        if (hasattr(self, 'subfiles') and len(self.subfiles) > 0):
            # we have subfiles so we must have actual files associated
            return True

        # check for locations
        if (hasattr(self, 'locations') and len(self.locations) > 0):
            return True

        return False

    def containsWildcards(self):
        """
        Return if the name has got wildcard characters
        """
        if regex.search(self.namePattern) != None:
            return True

        return False

    def cleanUpClient(self):
        """
        This method cleans up the client space after performing a put of a file after a job has completed
        """

        # For all other file types (not LocalFile) The file in the outputdir is temporary waiting for Ganga to pass it to the storage solution
        job = self.getJobObject()

        for f in glob.glob(os.path.join(job.outputdir, self.namePattern)):
            try:
                os.remove(f)
            except OSError as err:
                if err.errno != errno.ENOENT:
                    logger.error('failed to remove temporary/intermediary file: %s' % f)
                    logger.debug("Err: %s" % err)
                    raise err

