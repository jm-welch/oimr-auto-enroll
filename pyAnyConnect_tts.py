import mysql.connector
from mysql.connector import Error as mysqlConnErr
import sshtunnel
import hashlib
import time
import json
import collections
import sys

sshtunnel.SSH_TIMEOUT = 5.0
sshtunnel.TUNNEL_TIMEOUT = 5.0


def load_creds():
    with open('sql_secret.json') as infile:
        creds = json.load(infile)
    return creds


def hash_student(registrantId, courseId):
    string_to_hash = registrantId + courseId
    hashed_string = hashlib.md5(string_to_hash.encode()).hexdigest()
    return hashed_string


def multi_dimensions(n, type):
    """
    Creates an n-dimension dictionary where the n-th dimension is of type 'type'
    """
    if n <= 1:
        return type()
    return collections.defaultdict(lambda: multi_dimensions(n - 1, type))


def get_tunnel_creds():
    creds = load_creds()
    sshCreds = creds
    sshCreds['ssh_username'] = creds['user']
    sshCreds['ssh_password'] = creds['userPass']
    del creds['userPass']
    sshCreds['ssh'] = "ssh.pythonanywhere.com"
    sshCreds["dbUrl"] = "oimr.mysql.pythonanywhere-services.com"
    sshCreds["dbPort"] = 3306
    sshCreds["host"] = '127.0.0.1'
    return creds, sshCreds
    TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"


collections.Counter()


class PyAnywhereAPI():

    def __init__(self, inputFile=None):
        """ If an inputFile is passed, use that,
            otherwise, look for explicit values """

        self.creds, self.sshCreds = get_tunnel_creds()
        # lets expose global class level objects
        self.arrConnVars = multi_dimensions(5, collections.Counter)
        self.googDict = multi_dimensions(5, collections.Counter)
        self.mysqlDict = multi_dimensions(5, collections.Counter)
        self.gPaTunnel = None
        self.gMysqlCur = None
        self.gMysqlConn = None
        # ok lets make connection array and and use sshTunnel forwarding to grab a port for sqlAlchemy engine

        # Make the ssh tunnel into pythonAnywhere
        self.make_pyanywhere_ssh_tunnel(self.sshCreds)
        # now lets use tunnel to create a connection string then
        # create the SqlAlchemy Engine with tunnel,
        # this will create/begin a SqlAlchemy engine, start a connection to oimr$OIMR database
        # and finally expose the mysql log table so that odo can write to it.

    def make_pyanywhere_ssh_tunnel(self, creds) -> object:
        self.gPaTunnel = sshtunnel.SSHTunnelForwarder(
            (creds['ssh'])
            , ssh_username=creds['ssh_username']
            , ssh_password=creds['ssh_password']
            , remote_bind_address=(creds['dbUrl'], creds['dbPort'])
        )
        self.gPaTunnel.start()
        TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"

    def make_mysql_connection(self, creds):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        # self.make_pyanywhere_msyql_engine_string()
        if not self.gMysqlConn == None:
            self.gMysqlConn.close()
            self.gMysqlConn = None
        try:
            self.gMysqlConn = mysql.connector.connect(
                user=self.sshCreds['user'],
                password=self.sshCreds['password'],
                host=self.sshCreds['host'],
                database=self.sshCreds['database'],
                port=self.sshCreds['port'],
                raise_on_warnings=True)
        except mysqlConnErr as e:
            print(e)

        if self.gMysqlConn.is_connected():
            self.gMysqlCur = self.gMysqlConn.cursor()
            return self.gMysqlCur
        else:
            if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
                self.gMysqlConn.close()

    def get_mysql_cursor(self):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        # self.make_pyanywhere_msyql_engine_string()

        try:
            if self.gMysqlConn.is_connected():
                self.gMysqlCur = self.gMysqlConn.cursor()
                return self.gMysqlCur
        except mysqlConnErr as e:
            print(e)
        return self.gMysqlCur

    def get_sekrets(self):
        self.gMysqlCur = self.get_mysql_cursor()
        q = 'SELECT * FROM sekrets'
        try:
            self.gMysqlCur.execute(q)
            result = self.gMysqlCur.fetchall()
            result = {x: json.loads(y) for x, y in result}
        except mysqlConnErr as e:
            result = None
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()
                self.gMysqlCur = None

        return result

    def update_course_invites(self, pending_invites):
        self.gMysqlCur = self.get_mysql_cursor()
        q1 = """SELECT invitation_Id FROM oimr_invitations WHERE invitation_Status = 'SENT'"""
        q2 = """UPDATE oimr_invitations SET invitatation_status = 'ACCEPTED' WHERE invitation_Id = %s"""

        try:
            self.gMysqlCur.execute(q1)
            result = [r[0] for r in self.gMysqlCur.fetchall()]
        except mysqlConnErr as e:
            result = None
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()
                self.gMysqlCur = None

        if result:
            try:
                accepted = [(i,) for i in result if i not in pending_invites]
                self.gMysqlCur.executemany(q2, accepted)
                self.gMysqlConn.commit()
            except mysqlConnErr as e:
                print(e)
            finally:
                if not self.gMysqlCur == None:
                    self.gMysqlCur.close()
                    self.gMysqlCur = None

    def get_student_in_course(self, studentId, courseId):
        self.gMysqlCur = self.get_mysql_cursor()
        q = "SELECT * FROM oimr_invitations WHERE registrant_Id = %s AND course_Id = %s"
        val = (studentId, courseId)

        try:
            self.gMysqlCur.execute(q, val)
            result = self.gMysqlCur.fetchall()
        except:
            result = None
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()
                self.gMysqlCur = None

        return result

    def get_commons_invitations(self):
        return self.get_invitations_for_course('commons1')

    def get_invitations_for_course(self, courseId):
        self.gMysqlCur = self.get_mysql_cursor()
        q = "SELECT registrant_email FROM oimr_invitations WHERE course_Id = %s"
        val = (courseId,)

        try:
            self.gMysqlCur.execute(q, val)
            result = self.gMysqlCur.fetchall()
            result = [r[0] for r in result]
        except mysqlConnErr as e:
            print(e)
            result = None
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()
                self.gMysqlCur = None

        return result

    def table_insert_update(self, tableName, dataDict):

        data_tupled = []
        for x in dataDict:
            data_tupled.append(tuple(x.values()))
        colUpdateStr = ', '.join(['{} = Values({})'.format(col, col) for col in dataDict[0].keys()])
        colList = tuple(['{}'.format(key) for key in dataDict[0].keys()])
        query = "INSERT INTO {} ({}) VALUES ({}) ON DUPLICATE KEY UPDATE {}".format(tableName, ', '.join(colList),
                                                                                    ','.join(['%s'.format(colname) for
                                                                                              colname in colList]),
                                                                                    colUpdateStr)
        try:

            self.gMysqlCur = self.get_mysql_cursor()
            result = self.gMysqlCur.executemany(query, data_tupled)
            self.gMysqlConn.commit()

        except mysqlConnErr as e:
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()

    def add_invitation(self, registrantId, registrantEmail, courseId, invitationId=None, status='SENT'):
        q = """INSERT INTO oimr_invitations 
                  (hash, registrant_Id, registrant_email, course_Id, invitation_Id, invitation_status)
               VALUES (%s, %s, %s, %s, %s, %s)"""
        val = (hash_student(registrantId, courseId), registrantId, registrantEmail, courseId, invitationId, status)

        self.gMysqlCur = self.make_mysql_connection()

        self.gMysqlCur.execute(q, val)
        self.gMysqlConn.commit()
        self.gMysqlConn.close()

    def make_log_info_entry(self, log_level, module, method, message, err_line=0):
        timeStampNow = (time.strftime("%Y-%m-%d %I:%M:%S"))
        exc_type, exc_value, exc_traceback = sys.exc_info()
        log_level = 'INFO'
        recno = None  # recno is the id field and autoincrements. odo can use a None object to
        log_string = [[recno, log_level, module, method, err_line, timeStampNow, message]]

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        pass


def get_pyAnywhereAPI():
    paMysqlDb = PyAnywhereAPI('sql_secret.json')

    return paMysqlDb


if __name__ == '__main__':
    db = PyAnywhereAPI('PythonAnywhere_secret.json')
    rec = ['qwerweroiewoi', 'testid', 'someone@gmail.com', 'TB', 'SOMEID']

    test = db.mysl_insert_update('oimr_invitations', rec)
    print('done')
