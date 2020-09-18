#!/usr/bin/python3.7
"""
OIMR: brige project:
author Toar Schell

what id does:
1) creates a ssh tunnel for remoting into PythonAnywhere.
2) Use that tunnel to aquire a locol remote port for a SqlAlchemy connection string.
3) create multiple table hooks for use of Odo which will do bulk inserts rapidly.

requirements: pythonAnywhere_secret json file that holds passwords and usernames.
Modules: sqlAlchemy, pandas odo multipledispatch
globals:
Notes as of 2020:
sshtunnel (requires visual studio build tools so you may have to go to https://visualstudio.microsoft.com/downloads/
PythonAnywhere is uptodate and has installed nicely,but if using locally you may need the c++ build tools.
odo - be careful here the pip install will an older version that does not implement pandas subroutines correctly.
https://github.com/blaze/odo has a version that does so the steps are pip install odo then copy and over-write the odo directory in site-site packages.
as of 09152020 this has been done on the pythonanywhere/user/home/.local/python37 implementation.
so make sure all of your scripts use a #!/usr/bin/python3.7 when running inside pythonAnywhere.
odo requires an input into mysql tables thusly with comma delimited records inside brackets:
[
[None, "Debug", "oimrConnect", "make_db_connect", 12, todaysDate,"All work and no play makes Jeremy a Dull boy"],
[None, "Info", "registration", "make_whoopie", 666, todaysDate,'all Play and no Work makes Jeremy a dull boy'],
[None, "debug", "oimrConnect", "print_all", 34, todaysDate, "I guess Jeremy is dull"]
]
one gotcha for mysql autoincrementing columns is that it requries a value in the identity field.
yours truly found a way around this by using a None object to pass to the database and Lo it Worked.
#TODO: post this solution to pythonAnywhere as well as stackoverflow given that its an undocumented solution.
"""
import sqlalchemy as sa
import sshtunnel
import time
import json
import collections
import odo

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
        self.arrConn = multi_dimensions(5, collections.Counter)
        self.gPaTunnel = None
        self.gPaEngine = None
        self.gMysqlConn = None
        # ok lets make connection array and and use sshTunnel forwarding to grab a port for sqlAlchemy engine
        self.make_arrConnParams()
        # Make the ssh tunnel into pythonAnywhere
        self.make_tunnel()
        # now lets use tunnel to create a connection string then
        # create the SqlAlchemy Engine with tunnel,
        # this will create/begin a SqlAlchemy engine, start a connection to oimr$OIMR database
        # and finally expose the mysql log table so that odo can write to it.
        self.make_connection()

    def make_arrConnParams(self):
        # This is multi dimensional so we can use it for other connections to any other databases we may want to set up.

        self.arrConn['pa']['OIMR']['userName'] = self.userName
        self.arrConn['pa']['OIMR']['userPass'] = self.userPass
        self.arrConn['pa']['OIMR']['dbPass'] = self.dbPass
        self.arrConn['pa']['OIMR']['dbName'] = self.dbName
        self.arrConn['pa']['OIMR']['ssh'] = 'ssh.pythonanywhere.com'
        self.arrConn['pa']['OIMR']['dbUrl'] = 'oimr.mysql.pythonanywhere-services.com'
        self.arrConn['pa']['OIMR']['dbPort'] = 3306
        self.arrConn['pa']['OIMR']['host'] = '127.0.0.1'
        self.arrConn['pa']['OIMR']['localBind'] = 'dynamic after tunnel start'
        self.arrConn['pa']['OIMR']['connection'] = r'mysql+mysqldb://'

    def make_tunnel(self) -> object:
        self.gPaTunnel = sshtunnel.SSHTunnelForwarder(
            (self.arrConn['pa']['OIMR']['ssh'])
            , ssh_username=self.arrConn['pa']['OIMR']['userName']
            , ssh_password=self.arrConn['pa']['OIMR']['userPass']
            , remote_bind_address=(self.arrConn['pa']['OIMR']['dbUrl']
                                   , self.arrConn['pa']['OIMR']['dbPort'])
        )
        self.gPaTunnel.start()
        TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"

    def make_connection_str(self):
        # now we capture the tunnel local bind port and use with sqlalchemy mysql dialect and the local port to create a connection string
        self.arrConn['pa']['OIMR']['localBind'] = str(self.gPaTunnel.local_bind_port)
        # ok have all the pieces to make a sqlAlchemy acceptable connection string
        self.arrConn['pa']['OIMR']['connection'] = \
            self.arrConn['pa']['OIMR']['connection'] + \
            self.arrConn['pa']['OIMR']['userName'] + ":" + \
            self.arrConn['pa']['OIMR']['dbPass'] + "@" + \
            self.arrConn['pa']['OIMR']['host'] + ":" + \
            self.arrConn['pa']['OIMR']['localBind'] + "/" + \
            self.arrConn['pa']['OIMR']['dbName']

    def make_connection(self):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        self.make_connection_str()
        # use make_connection_str results to fire up a sqlAlchemy connection into PythonAnywhere using mysql dialect
        self.gPaEngine = sa.create_engine(self.arrConn['pa']['OIMR']['connection'], pool_recycle=280)
        # TODO: MAKE A CONNECTION POOL HERE FOR VAROUS HOOKS INTO ENGINE
        test = self.gPaEngine.get_execution_options()
        self.gPaMysqlConn = self.gPaEngine.connect()
        self.gPaMysqlConn.begin()

        metadata = sa.MetaData(bind=self.gPaMysqlConn)
        self.mysqlLogTable = sa.Table('oimr_logging', metadata,
                                      sa.Column('recno', sa.Integer, primary_key=True),
                                      sa.Column('log_level', sa.VARCHAR),
                                      sa.Column('module', sa.VARCHAR, primary_key=True),
                                      sa.Column('method', sa.VARCHAR, primary_key=True),
                                      sa.Column('line_num', sa.Integer, primary_key=True),
                                      sa.Column('mess_date', sa.DATETIME),
                                      sa.Column('message', sa.VARCHAR)
                                      )
        self.make_log_entry("Info", "oimrConnect", "make_connection",
                            "Established connection to Mysql database log table")

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

    def close_tunnel(self, tunnel):
        if tunnel.is_active:
            tunnel.is_active = False

            # TODO: write close script
            # TODO: write error code
            print("should we close tunnel?")

    def make_log_entry(self, log_level, module, method, message, err_line=0):
        timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
        recno = None  # recno is the id field and autoincrements. odo can use a None object to
        log_string = [[recno, log_level, module, method, err_line, timeStampNow, message]]
        logDs = odo.discover(self.mysqlLogTable)
        odo.odo(log_string, self.mysqlLogTable, dshape=logDs, bind=self.gPaEngine, raise_on_errors=True)


if __name__ == '__main__':
    pyAnyApi = PyAnywhereAPI('PythonAnywhere_secret.json')
    print('done')
    """
    pyAnyApi, arrConn, gPaTunnel, gPaMysqlConn, gPaEngine, mysqlLogTable = makeOimrConnection(
        'PythonAnywhere_secret.json')
    arrConn = pyAnyApi.make_arrConnParams()
    gPaTunnel = pyAnyApi.make_tunnel(arrConn)
    # suppose the database has been restarted.

    timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
    logDs = odo.discover(pyAnyApi.mysqlLogTable)
    errLog = [
        [None, "Debug", "oimrConnect", "make_db_connect", 12, timeStampNow,"All work and no play makes Jeremy a Dull boy"],
        [None, "Info", "registration", "make_whoopie", 666, timeStampNow,'all Play and no Work makes Jeremy a dull boy'],
        [None, "debug", "oimrConnect", "print_all", 34, timeStampNow, "I guess Jeremy is dull"]
    ]
    print(errLog)
    errLog = odo.odo(errLog, pyAnyApi.mysqlLogTable, dshape=logDs, bind=pyAnyApi.gPaEngine, raise_on_errors=True)
    print(errLog)
    closeTunnel = True
    closeEngine = True
    closeMysqlconn = True
    mysqlClose = pyAnyApi.close_connection(closeMysqlconn, closeEngine, closeTunnel)
    
    """
# registrants.print_report()


# odo(registrants.data,pd.DataFrame)
