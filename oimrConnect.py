
import sqlalchemy as sa
import sshtunnel
#import pandas as pd
#from os import getenv
import json
import logging
import time
import collections
#import odo
import registration_mysql as reg

sshtunnel.SSH_TIMEOUT = 5.0
sshtunnel.TUNNEL_TIMEOUT = 5.0
api, registrants = reg.makeRegistrationList('regfox_secret.json')

def multi_dimensions(n, type):
    """ Creates an n-dimension dictionary where the n-th dimension is of type 'type'
    """
    if n<=1:
        return type()
    return collections.defaultdict(lambda:multi_dimensions(n-1, type))
collections.Counter()

class PyAnywhereAPI():
    def __init__(self,inputFile=None,tunnel=None,arrConn=None):
        """ If an inputFile is passed, use that,
            otherwise, look for explicit values """

        if inputFile:
            with open(inputFile, 'r') as infile:
                pyAInfo = json.load(infile)
                #print(apiInfo)

                self.userName = pyAInfo['userName']    # 'oimr'
                self.userPass = pyAInfo['userPass']    # 'Ke$haJig1'
                self.dbPass = pyAInfo['dbPass']        # '0IMRData$t0r3' #again lazy, shortining concatenation.
                self.dbName = pyAInfo['dbName']        # 'oimr$OIMR'
                #arrConn = self.make_arrConnParams()
                #tunnel = self.make_tunnel(arrConn)

    def make_arrConnParams(self):
        # This is multi dimensional so we can use it for other connections to any other databases we may want to set up.
        arrConnParams = multi_dimensions(5,collections.Counter)
        arrConnParams['pa']['OIMR']['userName'] = self.userName
        arrConnParams['pa']['OIMR']['userPass'] = self.userPass
        arrConnParams['pa']['OIMR']['dbPass'] = self.dbPass
        arrConnParams['pa']['OIMR']['dbName'] = self.dbName
        arrConnParams['pa']['OIMR']['ssh'] = 'ssh.pythonanywhere.com'
        arrConnParams['pa']['OIMR']['dbUrl'] = 'oimr.mysql.pythonanywhere-services.com'
        arrConnParams['pa']['OIMR']['dbPort'] =  3306
        arrConnParams['pa']['OIMR']['host'] =  '127.0.0.1'
        arrConnParams['pa']['OIMR']['localBind'] = 'dynamic after tunnel start'
        arrConnParams['pa']['OIMR']['connection'] =  r'mysql+mysqldb://'
        return arrConnParams
   
    def make_tunnel(self,arrConn) -> object:
        tunnel = sshtunnel.SSHTunnelForwarder(
        (arrConn['pa']['OIMR']['ssh'])
        ,ssh_username=arrConn['pa']['OIMR']['userName']
        , ssh_password=arrConn['pa']['OIMR']['userPass']
        ,remote_bind_address=(arrConn['pa']['OIMR']['dbUrl'], arrConn['pa']['OIMR']['dbPort'])
            );
        tunnel.start()
        TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"
        return tunnel

    def make_connection_str(self,arrConn,tunnel):
        # now we capture the tunnel local bind port and use with sqlalchemy mysql dialect and the local port to create a connection string
        arrConn['pa']['OIMR']['localBind'] = str(tunnel.local_bind_port)
        arrConn['pa']['OIMR']['connection'] = \
        arrConn['pa']['OIMR']['connection'] + \
        arrConn['pa']['OIMR']['userName']  + ":" + \
        arrConn['pa']['OIMR']['dbPass'] +  "@" + \
        arrConn['pa']['OIMR']['host']  + ":" + \
        arrConn['pa']['OIMR']['localBind'] + "/" + \
        arrConn['pa']['OIMR']['dbName'];

        return arrConn['pa']['OIMR']['connection']

    def close_connection(self,mysqlConn,tunnel):
        if not mysqlConn.closed:
            mysqlConn.close()
            print('Connection closed')


    def close_tunnel(self,tunnel):
        if tunnel.is_active:
            print("should we close tunnel?")



    def make_connection(self,arrConn,tunnel):
        #connString = self.make_connection_str(arrConn,tunnel)
        # use make_connection_str to getnerate the correct url for a sqlalchemy connection into PythonAnywhere
        eng = sa.create_engine(self.make_connection_str(arrConn,tunnel),pool_recycle=280);
        test = eng.get_execution_options();
        conn = eng.connect()
        conn.begin()

        metadata = sa.MetaData(bind=conn)
        tblOimrLogging = sa.Table('oimr_logging', metadata,
                                  sa.Column('recno', sa.Integer, primary_key=True),
                                  sa.Column('log_level', sa.VARCHAR),
                                  sa.Column('module', sa.VARCHAR, primary_key=True),
                                  sa.Column('method', sa.VARCHAR, primary_key=True),
                                  sa.Column('line_num', sa.Integer, primary_key=True),
                                  sa.Column('mess_date', sa.DATETIME),
                                  sa.Column('message', sa.VARCHAR)
                                  );

        return conn,eng, tblOimrLogging



def makeLogFile(mess):
    todaysDate = (time.strftime("%d_%m_%Y"))
    pthLog = r".\logs\oimr_"
    logFileName = pthLog
    logFileNameExt = ".log"
    finalFileName = logFileName + todaysDate + logFileNameExt
    # \\cityofmesquite.com\Files\GIS\GISDS\projects\scheduled\Replication\logs\
    logging.basicConfig(filename=finalFileName,  format='%(levelname)s - %(asctime)s: %(message)s',datefmt='%m/%d/%Y %I:%M:%S %p', filemode='a', level=logging.DEBUG)


def makeOimrConnection(secretJson, **kwargs):
    pyAnyApi = PyAnywhereAPI(secretJson)
    arrConn = pyAnyApi.make_arrConnParams()
    tunnel = pyAnyApi.make_tunnel(arrConn)
    mysqlConn,engine,mysqlLog = (pyAnyApi.make_connection(arrConn,tunnel))

    return pyAnyApi,arrConn,tunnel,mysqlConn,engine,mysqlLog


if __name__ == '__main__':
    pyAnyApi,arrConn,tunnel,mysqlConn,engine,mysqlLog = makeOimrConnection('PythonAnywhere_secret.json')
    logging.basicConfig()

    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)



    mysqlClose = (pyAnyApi.close_connection(mysqlConn,tunnel))
#registrants.print_report()







#odo(registrants.data,pd.DataFrame)










