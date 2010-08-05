#
# CRAB Application
# 
# 08/06/10 @ ubeda
#
import subprocess

from Ganga.GPIDev.Adapters.IApplication import IApplication
from Ganga.GPIDev.Schema import *
from Ganga.Utility.logging import getLogger

from GangaCMS.Lib.ConfParams import *
from GangaCMS.Lib.CRABTools.CRABServer import *

logger = getLogger()

class CRABApp(IApplication):

  comments=[]
  comments.append('crab.cfg file either created by GangaCMS or added by user.')
  comments.append('Workdir.')

  schemadic = {}
  schemadic['cfgfile']        = SimpleItem(defvalue=None,    typelist=['type(None)','str'], doc=comments[0], copiable=0) 
  schemadic['workdir']        = SimpleItem(defvalue=None,    typelist=['type(None)','str'], doc=comments[1], copiable=0) 

  _schema = Schema(Version(1,0), schemadic)
  _category = 'applications'
  _name = 'CRABApp' 

  def __init__(self):
    super(CRABApp,self).__init__()

  def writeCRABFile(self,job,cfg_file):

    file = open(cfg_file,'w')     

#    if not job.inputdata.ui_working_dir:
    job.inputdata.ui_working_dir = job.outputdir
                        
    for params in [CMSSW(),CRAB(),GRID(),USER()]:

      section = params.__class__.__name__
      file.write('['+section+']\n\n')

      for k in params.schemadic.keys():
        attr = getattr(job.inputdata,k)
        if attr != None:  
          file.write('%s=%s\n'%(k,attr))                  
      file.write('\n')

    file.close()

  def master_configure(self):

    #Get job containing this CRABApp 
    job = self.getJobObject()

#    if not job.application.cfgfile:
    #File where crab.cfg is going to be written
    cfg_file = '%scrab.cfg'%(job.inputdir)
    job.application.writeCRABFile(job,cfg_file)
    job.application.cfgfile = cfg_file

    job.application.workdir = job.inputdata.ui_working_dir

    server = CRABServer()
    server.create(job)

    return (1,None)

  def configure(self,masterappconfig):
    return (None,None)
