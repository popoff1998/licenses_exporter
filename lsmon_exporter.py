"""
lsmon_exporter: Equivalente a flexlm_exporter como cliente prometheus_client
Tonin 2018
"""

import commands
from prometheus_client import Gauge, start_http_server
import time

#Algunas globales para controlar el programa
CMD = './lsmon'
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
        self.hostName = ''

class Feature(object):
    def __init__(self, name, fqdn):
        self.name = name.replace('"','')
        self.fqdn = fqdn
        self.maxLicenses = 0
        self.inUse = 0
        self.userList = []
        try:
            self.app = Apps[self.name][0]
        except KeyError:
            self.app = None

    def printFeature(self):
        print "app=",self.app," feature=",self.name," max=",self.maxLicenses," current=",self.inUse
        for user in self.userList:
            print "\t",user.name," ",user.hostName

class Features(object):
    #de momento lo hago monoservidor
    def __init__(self, fqdn):
        self.fqdn = fqdn
        self.featureList = []
        self.flexlm_feature_issued = Gauge('flexlm_feature_issued',"dummy",['app','name'])
        self.flexlm_feature_used = Gauge('flexlm_feature_used',"dummy",['app','name'])
        self.flexlm_feature_used_users = Gauge('flexlm_feature_used_users','dummy',['app','name','user'])
        self.flexlm_server_status = Gauge('flexlm_server_status','dummy',['app','fqdn','master','port','version'])

    def parse(self):
        output = commands.getstatusoutput(CMD + ' ' + self.fqdn)
        for _output in output:
            if type(_output) == type(''):
                lines = _output.split('\n')
                for line in lines:
                    if 'Feature name' in line:
                        feature = Feature(line.split(":",1)[1][1:-3], self.fqdn)
                        self.featureList.append(feature)
                    if 'Maximum concurrent user' in line:
                        feature.maxLicenses = float(line.split(":",1)[1][1:])
                    if 'Unreserved tokens in use' in line:
                        feature.inUse = float(line.split(":",1)[1][1:])
                    if 'User name' in line:
                        user = User(line.split(":",1)[1][1:])
                        feature.userList.append(user)
                    if 'Host name' in line:
                        user.hostName =  line.split(":",1)[1][1:]

    def isOnline(self, app):
        for feature in self.featureList:
            if app == feature.name:
                return 1
        return 0

    def printFeatures(self):
        for feature in self.featureList:
            feature.printFeature()

    def updateMetric(self):
        features.parse()
        for feature in self.featureList:
            if feature.app:
                self.flexlm_feature_issued.labels(app=feature.app,name=feature.name).set(feature.maxLicenses)
                self.flexlm_feature_used.labels(app=feature.app,name=feature.name).set(feature.inUse)
                for user in feature.userList:
                    self.flexlm_feature_used_users.labels(app=feature.app,name=feature.name,user=user.name).set(1)
        """
            lsmon es un tanto diferente de lmutil da solo info
            de las fetures que estan ejecutandose, por lo que hay que
            comprobar el estado de una licencia en base a conocimiento
            previo de las que deben de estar. Para ello usamos el diccionario
            hardcoded. Mas adelante lo leeremos de un yml
        """
        for app,value in Apps.iteritems():
            self.flexlm_server_status.labels(app=value[0],fqdn=value[1],
                                             master='true',port='5093',
                                             version=value[2]).set(self.isOnline(app))


if __name__ == '__main__':
    features = Features(SERVER)
    start_http_server(PORT)
    while True:
        features.updateMetric()
        time.sleep(SLEEP)
