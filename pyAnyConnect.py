import mysql.connector
from mysql.connector import Error as mysqlConnErr
import sshtunnel
import time
import json
import collections
# import odo
import traceback
import gc
import sys
import meta_exc

sshtunnel.SSH_TIMEOUT = 5.0
sshtunnel.TUNNEL_TIMEOUT = 5.0


def multi_dimensions(n, type):
    """
    Creates an n-dimension dictionary where the n-th dimension is of type 'type'
    """
    if n <= 1:
        return type()
    return collections.defaultdict(lambda: multi_dimensions(n - 1, type))


collections.Counter()


class PyAnywhereAPI():
    def __init__(self, inputFile=None):
        """ If an inputFile is passed, use that,
            otherwise, look for explicit values """

        if inputFile:
            with open(inputFile, 'r') as infile:
                pyAInfo = json.load(infile)
                # print(apiInfo)

                self.userName = pyAInfo['userName']
                self.userPass = pyAInfo['userPass']
                self.dbPass = pyAInfo['dbPass']
                self.dbName = pyAInfo['dbName']
        # lets expose global class level objects
        self.arrConnVars = multi_dimensions(5, collections.Counter)
        self.googDict = multi_dimensions(5, collections.Counter)
        self.mysqlDict = multi_dimensions(5, collections.Counter)
        self.gPaTunnel = None
        self.gMysqlCur = None
        self.gMysqlConn = None
        # ok lets make connection array and and use sshTunnel forwarding to grab a port for sqlAlchemy engine
        self.make_arrConnParams()
        # Make the ssh tunnel into pythonAnywhere
        self.make_pyanywhere_ssh_tunnel()
        # now lets use tunnel to create a connection string then
        # create the SqlAlchemy Engine with tunnel,
        # this will create/begin a SqlAlchemy engine, start a connection to oimr$OIMR database
        # and finally expose the mysql log table so that odo can write to it.

    def make_arrConnParams(self, reg=None, course=None, class_id=None, classLabel=None):
        # This is multi dimensional so we can use it for other connections to any other databases we may want to set up.

        self.arrConnVars['pa']['OIMR']['userName'] = self.userName
        self.arrConnVars['pa']['OIMR']['userPass'] = self.userPass
        self.arrConnVars['pa']['OIMR']['dbPass'] = self.dbPass
        self.arrConnVars['pa']['OIMR']['dbName'] = self.dbName
        self.arrConnVars['pa']['OIMR']['ssh'] = 'ssh.pythonanywhere.com'
        self.arrConnVars['pa']['OIMR']['dbUrl'] = 'oimr.mysql.pythonanywhere-services.com'
        self.arrConnVars['pa']['OIMR']['dbPort'] = 3306
        self.arrConnVars['pa']['OIMR']['host'] = '127.0.0.1'
        self.arrConnVars['pa']['OIMR']['localBind'] = 'dynamic after tunnel start'
        self.arrConnVars['pa']['OIMR']['connection'] = r'mysql+mysqldb://'

    def make_pyanywhere_ssh_tunnel(self) -> object:
        self.gPaTunnel = sshtunnel.SSHTunnelForwarder(
            (self.arrConnVars['pa']['OIMR']['ssh'])
            , ssh_username=self.arrConnVars['pa']['OIMR']['userName']
            , ssh_password=self.arrConnVars['pa']['OIMR']['userPass']
            , remote_bind_address=(self.arrConnVars['pa']['OIMR']['dbUrl']
                                   , self.arrConnVars['pa']['OIMR']['dbPort'])
        )
        self.gPaTunnel.start()
        TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"

    def make_pyanywhere_msyql_engine_string(self):
        # now we capture the tunnel local bind port and use with sqlalchemy mysql dialect and the local port to create a connection string
        self.arrConnVars['pa']['OIMR']['localBind'] = str(self.gPaTunnel.local_bind_port)
        # ok have all the pieces to make a sqlAlchemy acceptable connection string
        self.arrConnVars['pa']['OIMR']['connection'] = \
            self.arrConnVars['pa']['OIMR']['connection'] + \
            self.arrConnVars['pa']['OIMR']['userName'] + ":" + \
            self.arrConnVars['pa']['OIMR']['dbPass'] + "@" + \
            self.arrConnVars['pa']['OIMR']['host'] + ":" + \
            self.arrConnVars['pa']['OIMR']['localBind'] + "/" + \
            self.arrConnVars['pa']['OIMR']['dbName']

    def make_mysql_connection(self):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        # self.make_pyanywhere_msyql_engine_string()
        if not self.gMysqlConn == None:
            self.gMysqlConn.close()
            self.gMysqlConn = None
        try:
            self.gMysqlConn = mysql.connector.connect(
                user=self.arrConnVars['pa']['OIMR']['userName'],
                password=self.arrConnVars['pa']['OIMR']['dbPass'],
                host=self.arrConnVars['pa']['OIMR']['host'],
                database=self.arrConnVars['pa']['OIMR']['dbName'],
                port=self.gPaTunnel.local_bind_port,  # self.arrConnVars['pa']['OIMR']['localBind'],
                raise_on_warnings=True)

            if self.gMysqlConn.is_connected():
                self.gMysqlCur = self.gMysqlConn.cursor()
                return self.gMysqlCur


        except mysqlConnErr as e:
            print(e)

        else:
            if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
                self.gMysqlConn.close()

    def close_mysql_conn(self):
        if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
            self.gMysqlConn.close()

    def mysl_insert_update(self, tableName, dataDict):

        colList = tuple(['{}'.format(col) for col in dataDict[0].keys()])
        data_tupled = []
        for x in dataDict:
            data_tupled.append(tuple(x.values()))

        colUpdateVal = tuple(['{} = Values({})'.format(col, col) for col in dataDict[0].keys()])

        query = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(tableName, ', '.join(colList),
                                                                                    ','.join(['%s'.format(colname) for
                                                                                              colname in colList]),
                                                                                    ', '.join(colUpdateVal))
        try:
            self.gMysqlCur = self.make_mysql_connection()

            result = self.gMysqlCur.executemany(query, data_tupled)
            self.gMysqlConn.commit()

            print('insert finished')
            if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
                self.gMysqlConn.close()
        except mysqlConnErr as e:
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()
            if self.gMysqlConn.is_connected:
                self.gMysqlConn.close()

    def mysl_Select(self, tableName, where=None):
        if not where == None:
            sql = 'select * from ' + tableName + where
        else:
            sql = 'select * from ' + tableName
        try:
            self.gMysqlCur = self.gMysqlConn.cursor()
            query = "select * from {}".format('oimr_logging')
            self.gMysqlCur.execute(query)
            rows = self.gMysqlCur.fetchall()
            if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
                self.gMysqlCur.close()
                self.gMysqlConn.close()

            return rows
        except mysqlConnErr as e:
            print(e)

    def make_log_info_entry(self, log_level, module, method, message, err_line=0):
        timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        log_level = 'INFO'
        recno = None  # recno is the id field and autoincrements. odo can use a None object to
        log_string = [[recno, log_level, module, method, err_line, timeStampNow, message]]


def get_pyAnywhereAPI():
    paMysqlDb = PyAnywhereAPI('PythonAnywhere_secret.json')

    return paMysqlDb


if __name__ == '__main__':
    db = PyAnywhereAPI('PythonAnywhere_secret.json')
    rec = ['qwerweroiewoi', 'testid', 'someone@gmail.com', 'TB', 'SOMEID']

    test = db.mysl_insert_update('oimr_invitations', rec)
    print('done')
