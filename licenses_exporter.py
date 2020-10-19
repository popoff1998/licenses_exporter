"""
licenses_exporter: A prometheus client to export lsmon & lmutil licenses
Tonin 2018. University of Cordoba
"""

import commands
from prometheus_client import Gauge, start_http_server
import time
import sys
import re
import ruamel.yaml as yaml

#Licenses & config file
CONFIG_FILE = 'config.yml'


class User(object):
    def __init__(self, name):
        self.name = name
        self.hostName = None
        self.device = None
        self.date = None

    def printUser(self):
        print "\t",self.name," ",self.hostName," ",self.device," ",self.date

    def printUserToError(self):
        print >> sys.stderr, "\t",self.name," ",self.hostName," ",self.device," ",self.date

class Feature(object):
    def __init__(self, name, app):
        self.name = name
        self.maxLicenses = 0
        self.inUse = 0
        self.app = app
        self.userList = []

    def printFeature(self):
        print "app=",self.app," feature=",self.name," max=",self.maxLicenses," current=",self.inUse
        for user in self.userList:
            user.printUser()

class App(object):
    def __init__(self, parent, name, server, type, include, monitor_users):
        self.parent = parent
        self.name = name
        self.server = server
        self.type = type
        self.include = str(include)
        self.monitorUsers = monitor_users
        self.featureList = []
        if(self.type == 'lsmon'):
            self.parse = self.parseLsmon
        elif(self.type == 'lmutil'):
            self.parse = self.parseLmutil
        self.online = False

    def parseLsmon(self):
        self.featureList = []
        self.online = False
        output = commands.getstatusoutput(self.parent.LSMONCMD + ' ' + self.server)
        for _output in output:
            if type(_output) == type(''):
                lines = _output.split('\n')
                for line in lines:
                    if 'Feature name' in line:
                        aux = line.split(":",1)[1][1:-3].replace('"','')
                        if aux in self.include.split(","):
                            feature = Feature(aux, self.name)
                            self.online = True
                            self.featureList.append(feature)
                        else:
                            feature = None
                    if 'Maximum concurrent user' in line and feature:
                        feature.maxLicenses = float(line.split(":",1)[1][1:])
                    if 'Unreserved tokens in use' in line and feature:
                        feature.inUse = float(line.split(":",1)[1][1:])
                    if 'User name' in line and feature and self.monitorUsers:
                        user = User(line.split(":",1)[1][1:])
                        feature.userList.append(user)
                    if 'Host name' in line and feature and self.monitorUsers:
                        user.hostName =  line.split(":",1)[1][1:]

    def parseLmutil(self):
        self.featureList = []
        self.online = False
        output = commands.getstatusoutput(self.parent.LMUTILCMD + ' ' + self.server)
        for _output in output:
            if type(_output) == type(''):
                lines = _output.split('\n')
                for line in lines:
                    if 'Users of' in line:
                        r = re.search('Users of (.*):  \(Total of (.*)licenses? issued;  Total of (.*) licenses? in use\)',line)
                        if r.group(1) in self.include.split(","):
                            feature = Feature(r.group(1), self.name)
                            self.online = True
                            feature.maxLicenses = float(r.group(2))
                            feature.inUse = float(r.group(3))
                            self.featureList.append(feature)
                        else:
                            feature = None
                    if ', start' in line and feature and self.monitorUsers:
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
        self.parent.license_server_status.labels(app=self.name,fqdn=self.server,
                                                 master='true',port='port',
                                                 version='version').set(self.online)
        for feature in self.featureList:
            self.parent.license_feature_issued.labels(app=feature.app,name=feature.name).set(feature.maxLicenses)
            self.parent.license_feature_used.labels(app=feature.app,name=feature.name).set(feature.inUse)
            for user in feature.userList:
                try:
                    self.parent.license_feature_used_users.labels(app=feature.app,name=feature.name,user=user.name,
                                                                  host=user.hostName,device=user.device).set(1)
                except:
                    print >> sys.stderr, "Error en used_users.label"
                    user.printUserToError()

class Apps(object):
    def __init__(self,cfgFile):
        self.appList = []
        with open(cfgFile, 'r') as yamlFile:
            self.cfg = yaml.safe_load(yamlFile)
        for appCfg in self.cfg['licenses']:
            app = App(self, appCfg['name'], appCfg['license_server'],
                            appCfg['type'], appCfg['features_to_include'], appCfg['monitor_users'])
            self.appList.append(app)
        self.license_feature_used = Gauge('license_feature_used','number of licenses used',['app','name'])
        self.license_feature_issued = Gauge('license_feature_issued','max number of licenses',['app','name'])
        self.license_feature_used_users = Gauge('license_feature_used_users','license used by user',['app','name','user','host','device'])
        self.license_server_status = Gauge('license_server_status','status of the license server',['app','fqdn','master','port','version'])
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
        self.license_feature_used_users._metrics.clear()
        for app in self.appList:
            app.updateMetric()

if __name__ == '__main__':
    apps = Apps(CONFIG_FILE)
    start_http_server(apps.PORT)
    while True:
        apps.updateMetric()
        time.sleep(apps.SLEEP)
