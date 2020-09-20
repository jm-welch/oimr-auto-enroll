#!/usr/bin/python3.7
"""
OIMR: brige project:
author Toar Schell
What id does:
1) Creates a ssh tunnel for remoting into PythonAnywhere.
    make_pyanywhere_ssh_tunnel(self) -> gPaTunnel (used to get to pythonAnywhere Website)
2) Use that tunnel to aquire a locol remote port for a SqlAlchemy connection using concatenated parameter array to make a connection string.
    make_pyanywhere_mysql_connection -> gPaEngine, gPaMysqlConn and finally a target table for logging g
3) create multiple table hooks for use of Odo which will do bulk inserts rapidly.

4) grabs system error tracing and uses traceback to create formated error messages

Requirements: pythonAnywhere_secret json file that holds passwords and usernames.
Modules: sqlAlchemy, pandas odo multipledispatch
globals:
Notes as of 2020:
sshtunnel (requires visual studio build tools so you may have to go to https://visualstudio.microsoft.com/downloads/
PythonAnywhere is uptodate and has installed nicely,but if using locally you may need the c++ build tools.
odo - be careful here the pip install will an older version that does not implement pandas subroutines correctly.
https://github.com/blaze/odo has a version that does so the steps are pip install odo then copy and over-write the odo directory in site-site packages.
as of 09152020 this has been done on the pythonanywhere/user/home/.local/python37 implementation.
so make sure all of your scripts use a #!/usr/bin/python3.7 when running inside pythonAnywhere.
SEE EXAMPLE BELOW FOR HOW TO FORMAT ODO INSERTS

USAGE: At this point its mainly to be used as an import into a script which will expose the pyAnyApi which will
allow access to the mysql database.
IMPORTANT: GIVEN THAT THIS TAKES A FEW SECONDS TO RUN ALL THE CONNECTIONS THROUGH TUNNELS AND ENGINES, I WOULD IMPORT
IT EARLY IN THE STACK SO AS TO ENABLE LOG WRITING EARLY ON.
when importing:

import pythonAnywhereConnect as pa
oimrDb = get_pyAnywhereAPI():
try:
    some code...
    # If level is INFO or you want to document a process
    oimrDb.make_log_info_entry('INFO',..)
exception:
    # First and last line automatic debugging
    oimrDb.make_log_exception_entry()



then in exceptions or when you want to enter into log table
db.make_log_entry(....)
DETAILS ON THAT:
The only not not self called in PyAnywhereAPI is the log writing method
thus is available as a callable object. using the import call above:
in any method or exception you can:
db.make_log_entry(self, log_level(INFO OR DEBUG DEPENDING ON ERROR HANDLING), module(STRING), method(STR), message(STR), err_line=0(MAY WANT TO ONLY ENTER A VALUE HERE IF ITS THE RESULT OF AN ERROR)
THIS CREATES AN INDIVIDUAL RECORD FOR THE LOG FILE.
#TODO: BULK INSERTS REQUIRE THE FOLLOWING FORMAT WE NEED A METHOD THAT ACCEPTS A PRE FORMATED DICTIONARY:
odo requires an input into mysql tables thusly with comma delimited records inside brackets:
[
[None, "Debug", "oimrConnect", "make_db_connect", 12, todaysDate,"All work and no play makes Jeremy a Dull boy"],
[None, "Info", "registration", "make_whoopie", 666, todaysDate,'all Play and no Work makes Jeremy a dull boy'],
[None, "debug", "oimrConnect", "print_all", 34, todaysDate, "I guess Jeremy is dull"]
]
one gotcha for mysql autoincrementing columns is that it requries a value in the identity field.
yours truly found a way around this by using a None object to pass to the database and Lo it Worked.
#TODO: post this solution to pythonAnywhere as well as stackoverflow given that its an undocumented solution.

When imported all connections are made and the log table should be ready for use VIA THE make_log_entry method.

#TODO: MAKE SURE WE HAVE KEEP ALIVE AS WELL AS TESTING FOR ENGINE ACTIVITY.

"""
import sqlalchemy as sa
import sshtunnel
import time
import json
import collections
import odo
import traceback
import gc
import sys
import string

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
        self.gPaTunnel = None
        self.gPaEngine = None
        self.gMysqlConn = None
        # ok lets make connection array and and use sshTunnel forwarding to grab a port for sqlAlchemy engine
        self.make_arrConnParams()
        # Make the ssh tunnel into pythonAnywhere
        self.make_pyanywhere_ssh_tunnel()
        # now lets use tunnel to create a connection string then
        # create the SqlAlchemy Engine with tunnel,
        # this will create/begin a SqlAlchemy engine, start a connection to oimr$OIMR database
        # and finally expose the mysql log table so that odo can write to it.
        self.make_pyanywhere_mysql_connection()

    def make_arrConnParams(self):
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

    def make_pyanywhere_mysql_connection(self):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        self.make_pyanywhere_msyql_engine_string()
        # use make_connection_str results to fire up a sqlAlchemy connection into PythonAnywhere using mysql dialect
        self.gPaEngine = sa.create_engine(self.arrConnVars['pa']['OIMR']['connection'], pool_recycle=280)
        # TODO: MAKE A CONNECTION POOL HERE FOR VAROUS HOOKS INTO ENGINE
        test = self.gPaEngine.get_execution_options()
        self.gPaMysqlConn = self.gPaEngine.connect()
        self.gPaMysqlConn.begin()

        metadata = sa.MetaData(bind=self.gPaMysqlConn)
        self.mysqlOimrLogTable = sa.Table('oimr_logging', metadata,
                                          sa.Column('recno', sa.Integer, primary_key=True),
                                          sa.Column('log_level', sa.VARCHAR),
                                          sa.Column('module', sa.VARCHAR, primary_key=True),
                                          sa.Column('method', sa.VARCHAR, primary_key=True),
                                          sa.Column('line_num', sa.Integer, primary_key=True),
                                          sa.Column('mess_date', sa.DATETIME),
                                          sa.Column('message', sa.VARCHAR)
                                          )

        # self.make_log_info_entry("Info", "PythonAnywhereAPI", "make_connection","Start: Established connection to Mysql database log table", 162)

        # return conn, eng, tblOimrLogging
        def close_connection(self, tun, eng, sqlConn):
            # TODO: SEE HOW THIS HOOKS IN WITH A SESSION WHICH SEEMS TO BE THE PROPER WAY TO CLOSE A SQLALCHEMY CONN.
            if sqlConn:
                if not self.gPaMysqlConn.closed:
                    self.gPaMysqlConn.close()
                    print('Connection closed')
            if eng:
                self.gPaEngine.dispose()
            if tun:
                if self.gPaTunnel.is_active:
                    print("check tunnel here")

    def close_tunnel(self):
        if self.gPaTunnel.is_active:
            # TODO: write close script
            # TODO: write error code
            print("should we close tunnel or connection?")

    def make_log_info_entry(self, log_level, module, method, message, err_line=0):
        timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        recno = None  # recno is the id field and autoincrements. odo can use a None object to
        log_string = [[recno, log_level, module, method, err_line, timeStampNow, message]]
        logDs = odo.discover(self.mysqlOimrLogTable)
        odo.odo(log_string, self.mysqlOimrLogTable, dshape=logDs, bind=self.gPaEngine, raise_on_errors=True)

    def make_log_exception_entry(self):
        timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.clear_frames(exc_traceback)
        gc.collect()
        eMess1 = {}
        eMess2 = {}
        if exc_traceback.tb_next == None:
            tbE = exc_traceback
            eMess1 = str(exc_traceback.tb_frame).replace('>', '').replace('<', '').split(",")
            eModule1 = eMess1[1]
            eModule1 = str(eModule1[eModule1.rindex(r'/'):eModule1.rindex('.')]).replace('/', '')
            eMethod1 = eMess1[3].replace('code ', '').replace(' ', '')

            eLineNo1 = exc_traceback.tb_lineno
            eLineNo = tbE.tb_lineno
            eMethod = eMethod1
            eModule = eModule1
            eMessage = 'ERROR MESSAGE: ' + str(
                exc_value) + ' This error found on ' + eModule1 + '.' + eMethod1 + ' line number: ' + str(eLineNo1)
        else:
            tbE = exc_traceback.tb_next
            # tbF = exc_tracebac' k.tb_frame
            eMess1 = str(exc_traceback.tb_frame).replace('>', '').replace('<', '').split(",")
            eMess2 = str(tbE.tb_frame).replace('>', '').replace('<', '').split(",")
            eMethod1 = eMess1[3].replace('code ', '').replace(' ', '')
            eMethod2 = eMess2[3].replace('code ', '').replace(' ', '')
            eModule1 = eMess1[1]
            eModule1 = str(eModule1[eModule1.rindex(r'/'):eModule1.rindex('.')]).replace('/', '')
            eModule2 = eMess2[1]
            eModule2 = str(eModule2[eModule2.rindex(r'\\'):eModule2.rindex('.')]).replace('\\', '')
            eLineNo = tbE.tb_lineno
            eLineNo1 = exc_traceback.tb_lineno
            eMessage = 'ERROR MESSAGE: ' + str(
                exc_value) + ' This error found on ' + eModule2 + '.' + eMethod2 + ' line number: ' + str(
                eLineNo) + ' was called from ' + eModule1 + '.' + eMethod1 + ' line number: ' + str(eLineNo1)
            eMethod = eMethod2
            eModule = eModule2

        recno = None  # recno is the id field and autoincrements. odo can use a None object to

        log_string = [[recno, 'DEBUG', eModule, eMethod, eLineNo, timeStampNow, eMessage]]
        logDs = odo.discover(self.mysqlOimrLogTable)
        odo.odo(log_string, self.mysqlOimrLogTable, dshape=logDs, bind=self.gPaEngine, raise_on_errors=True)


def get_pyAnywhereAPI():
    paMysqlDb = PyAnywhereAPI('PythonAnywhere_secret.json')
    return paMysqlDb


if __name__ == '__main__':
    db = PyAnywhereAPI('PythonAnywhere_secret.json')
    print('done')
    db.make_log_entry('debug', 'oimrConnect', 'main', 'this is a test of an outside call to log', 191)
