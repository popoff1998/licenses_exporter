"""
lsmon_exporter: Equivalente a flexlm_exporter como cliente prometheus_client
Tonin 2018
"""

import commands
from prometheus_client import Gauge, start_http_server
import time
import re
import ruamel.yaml as yaml

#Algunas globales para controlar el programa
CMD = './lsmon'
LICENSES_FILE = 'licenses.yml'
SERVER = 'windhcp2'
PORT = 8000
SLEEP = 5

Apps =  {
            "1200" : ("SPSS","windhcp2","v9.1.0.0104"),
            "Grapher" : ("GRAPHER","windhcp2","v9.1.0.0104")
        }

class User(object):
    def __init__(self, name):
        self.name = name
        self.hostName = None
        self.device = None
        self.date = None

    def printUser(self):
        print "\t",user.name," ",user.hostName," ",user.device," ",user.date

class Feature(object):
    def __init__(self, name, app):
        self.name = name
        self.maxLicenses = 0
        self.inUse = 0
        self.app = app
        self.userList = []

        if(self.app == 'lsmon'):
            try:
                self.app = Apps[self.name][0]
            except KeyError:
                self.app = None

    def printFeature(self):
        print "app=",self.app," feature=",self.name," max=",self.maxLicenses," current=",self.inUse
        for user in self.userList:
            user.printUser()

class App(object):
    def __init__(self, parent, name, server, type, include):
        self.parent = parent
        self.name = name
        self.server = server
        self.type = type
        self.include = include
        self.featureList = []
        if(self.type == 'lsmon'):
            self.parse = self.parseLsmon
        elif(self.type == 'lmutil'):
            self.parse = self.parseLmutil
        """
            No se muy bien como comprobar de forma generica si esta online.
            Parece que si al parsear lo encuentra es porque esta online, pero tengo
            que hacer mas comprobaciones de como se comporta en grafanaself.
        """
        self.online = True

    def parseLsmon(self):
        self.featureList = []
        output = commands.getstatusoutput(self.parent.LSMONCMD + ' ' + self.server)
        for _output in output:
            if type(_output) == type(''):
                lines = _output.split('\n')
                for line in lines:
                    if 'Feature name' in line:
                        aux = line.split(":",1)[1][1:-3].replace('"','')
                        if aux in str(self.include):
                            feature = Feature(aux, self.name)
                            self.featureList.append(feature)
                        else:
                            feature = None
                    if 'Maximum concurrent user' in line:
                        if(feature): feature.maxLicenses = float(line.split(":",1)[1][1:])
                    if 'Unreserved tokens in use' in line:
                        if(feature): feature.inUse = float(line.split(":",1)[1][1:])
                    if 'User name' in line:
                        if(feature):
                            user = User(line.split(":",1)[1][1:])
                            feature.userList.append(user)
                    if 'Host name' in line:
                        if(feature): user.hostName =  line.split(":",1)[1][1:]

    def parseLmutil(self):
        self.featureList = []
        output = commands.getstatusoutput(self.parent.LMUTILCMD + ' ' + self.server)
        for _output in output:
            if type(_output) == type(''):
                lines = _output.split('\n')
                for line in lines:
                    if 'Users of' in line:
                        r = re.search('Users of (.*):  \(Total of (.*)licenses? issued;  Total of (.*) licenses? in use\)',line)
                        feature = Feature(r.group(1), self.name)
                        feature.maxLicenses = float(r.group(2))
                        feature.inUse = float(r.group(3))
                        self.featureList.append(feature)
                    if ', start' in line:
                        r = re.search('^\s+(.*) (.*) (.*) \((.*)\) \((.*)/(.*) (.*)\), start (.*)',line)
                        user = User(r.group(1))
                        user.hostName = r.group(2)
                        user.device = r.group(3)
                        user.date = r.group(8)
                        feature.userList.append(user)

    def printFeatures(self):
        for feature in self.featureList:
            feature.printFeature()

    def updateMetric(self):
        self.parse()
        self.parent.flexlm_server_status.labels(app=self.name,fqdn=self.server,
                                         master='true',port='port',
                                         version='version').set(self.online)

        for feature in self.featureList:
            self.parent.flexlm_feature_issued.labels(app=feature.app,name=feature.name).set(feature.maxLicenses)
            self.parent.flexlm_feature_used.labels(app=feature.app,name=feature.name).set(feature.inUse)

            for user in feature.userList:
                self.parent.flexlm_feature_used_users.labels(app=feature.app,name=feature.name,user=user.name,
                                                             host=user.hostName,device=user.device).set(1)

class Apps(object):
    def __init__(self):
        self.appList = []

        with open(LICENSES_FILE, 'r') as fp:
            self.cfg = yaml.safe_load(fp)
        for appCfg in self.cfg['licenses']:
            app = App(self, appCfg['name'], appCfg['license_server'], appCfg['type'], appCfg['features_to_include'])
            self.appList.append(app)

        self.flexlm_feature_used = Gauge('flexlm_feature_used',"dummy",['app','name'])
        self.flexlm_feature_issued = Gauge('flexlm_feature_issued',"dummy",['app','name'])
        self.flexlm_feature_used_users = Gauge('flexlm_feature_used_users','dummy',['app','name','user','host','device'])
        self.flexlm_server_status = Gauge('flexlm_server_status','dummy',['app','fqdn','master','port','version'])
        self.PORT = self.cfg['config']['port']
        self.SLEEP = self.cfg['config']['sleep']
        self.LSMONCMD = self.cfg['config']['lsmon_cmd']
        self.LMUTILCMD = self.cfg['config']['lmutil_cmd']

    def parse(self):
        for app in self.appList:
            app.parse()

    def printApps(self):
        for app in self.appList:
            app.printFeatures()

    def updateMetric(self):
        self.flexlm_feature_used_users._metrics.clear()
        for app in self.appList:
            app.updateMetric()
"""
apps = Apps()
apps.parse()
apps.printApps()
"""


if __name__ == '__main__':
    apps = Apps()
    start_http_server(apps.PORT)
    while True:
        apps.updateMetric()
        time.sleep(apps.SLEEP)
