#!/usr/bin/python3.7
import mysql.connector
from mysql.connector import Error as mysqlConnErr
import sshtunnel
import hashlib
import time
import json
import collections
import sys
import logging
from os import path

sshtunnel.SSH_TIMEOUT = 5.0
sshtunnel.TUNNEL_TIMEOUT = 5.0


# logging.getLogger()

# logging.basicConfig(
#     level=logging.INFO,
#     filename='bridge.log',
#     format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
# )
# logging.info("########### pyAnyConnect script started ###########")


def load_creds():
    doTunnel = False
    dbCreds = None
    tCreds = None

    try:
        with open('tunnel_secret.json') as tunnelFile:
            doTunnel = True
            tCreds = json.load(tunnelFile)
            logging.info("opened tunnel json files")
    except:
        logging.info("No Tunnel available, opened using PythonAnywhere connection file")
    finally:
        try:
            with open('sql_secret.json') as connFile:
                dbCreds = json.load(connFile)
                logging.info("opened mysql tunnel connection files")
        except EnvironmentError:
            logging.exception('Unable to open DB connection creds')

    return doTunnel, dbCreds, tCreds


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

collections.Counter()

class PyAnywhereAPI():

    def __init__(self, inputFile=None):
        """ If an inputFile is passed, use that,
            otherwise, look for explicit values """

        # lets expose global class level objects
        self.arrConnVars = multi_dimensions(5, collections.Counter)
        self.googDict = multi_dimensions(5, collections.Counter)
        self.mysqlDict = multi_dimensions(5, collections.Counter)
        self.gPaTunnel = None
        self.gMysqlCur = None
        self.gMysqlConn = None
        self.tunnel = None
        self.creds = None
        self.sshCreds = None
        # ok lets make connection array and and use sshTunnel forwarding to grab a port for sqlAlchemy engine

        # Make the ssh tunnel into pythonAnywhere remote and bypass tunnel  running in PythonAnywhere

        logging.info("########### tunnel file found Tunnel Access starting ###########")
        self.tunnel, self.creds, self.sshCreds = load_creds()

        if self.tunnel:
            logging.debug("########### starting tunnel ###########")
            self.make_pyanywhere_ssh_tunnel()
        else:
            logging.info("########### Bypass tunnel: get creds for running in PythonAnywhere###########")

        # add local bind port to the connection string for a mysql.connect through the tunnel
        self.update_creds(self.tunnel)
        # self.make_mysql_connection(True)

        # self.make_mysql_connection(False)

        # now lets use tunnel to create a connection string then
        # create the SqlAlchemy Engine with tunnel,
        # this will create/begin a SqlAlchemy engine, start a connection to oimr$OIMR database
        # and finally expose the mysql log table so that odo can write to it.

    def make_pyanywhere_ssh_tunnel(self) -> object:
        try:
            self.gPaTunnel = sshtunnel.SSHTunnelForwarder(
                (self.sshCreds['ssh'])
                , ssh_username=self.sshCreds['ssh_username']
                , ssh_password=self.sshCreds['ssh_password']
                , remote_bind_address=(self.sshCreds['dbUrl'], self.sshCreds['dbPort'])
            )
            self.gPaTunnel.start()
        except sshtunnel.BaseSSHTunnelForwarderError as e:
            logging.debug("########### starting tunnel Failed to start ###########")
            logging.debug(e)

    def update_creds(self, tunnel=True):
        if tunnel:
            if self.gPaTunnel.is_active:
                self.creds["host"] = '127.0.0.1'
                self.creds["port"] = self.gPaTunnel.local_bind_port
                self.creds["raise_on_warnings"] = True
                logging.debug("########### Creds updated for use through tunnel ###########")
        else:
            # keep original creds
            self.creds["raise_on_warnings"] = True

        TODO: "MAKE A START/STOP TUNNEL INTERFACE TO CLEAN THINGS UP"

    def make_mysql_connection(self, tunnel=False):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        # self.make_pyanywhere_msyql_engine_string()
        if self.gMysqlConn is not None:
            self.gMysqlConn.close()
            self.gMysqlConn = None
        try:
            self.gMysqlConn = mysql.connector.connect(**self.creds)

            return self.gMysqlConn
        except mysqlConnErr as e:
            print(e)
        """
        if self.gMysqlConn.is_connected():
            self.gMysqlCur = self.gMysqlConn.cursor()
            return self.gMysqlCur
        else:
            if self.gMysqlConn is not None and self.gMysqlConn.is_connected():
                self.gMysqlConn.close() """

    def get_mysql_cursor(self, getDict=True, buffered=True):
        # call make oimr$OIMR database connection string to correctly populate value of self.arrConn['pa']['OIMR']['connection']
        # self.make_pyanywhere_msyql_engine_string()
        
        # Reconnect if we're disconnected
        if not self.gMysqlConn.is_connected():
            self.gMysqlConn.connect()
        
        try:
            if self.gMysqlConn is not None:
                self.gMysqlCur = self.gMysqlConn.cursor(buffered=buffered, dictionary=bool(getDict))
            else:
                try:
                    self.__init__()
                    self.gMysqlConn = self.make_mysql_connection(self.tunnel)
                    self.gMysqlCur = self.gMysqlConn.cursor(buffered=buffered, dictionary=bool(getDict))
                except:
                    logging.debug("this bad..cats and dogs living together level bad..")

            return self.gMysqlCur
        except mysqlConnErr as e:
            print(e)
        return self.gMysqlCur

    def get_sekrets(self):
        self.gMysqlCur = self.get_mysql_cursor(False)
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

    def _query(self, query):
        self.gMysqlCur = self.get_mysql_cursor(True)
        self.gMysqlCur.execute(query)
        result = self.gMysqlCur.fetchall()
        if not self.gMysqlCur == None:
            self.gMysqlCur.close()
            self.gMysqlCur = None
        return result

    def update_course_invites(self, pending_invites):
        self.gMysqlCur = self.get_mysql_cursor(True)
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
        self.gMysqlCur = self.get_mysql_cursor(True)
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

    def get_sent_invitations(self):
        self.gMysqlCur = self.get_mysql_cursor(True)
        q = """SELECT * FROM oimr_invitations WHERE invitation_status = 'SENT'"""
        try:
            self.gMysqlCur.execute(q)
            result = self.gMysqlCur.fetchall()
        except mysqlConnErr:
            result = []
            logging.exception('DB ERROR')
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()

        return result

    def get_invitations_for_course(self, courseId):
        self.gMysqlCur = self.get_mysql_cursor(True)
        q = "SELECT * FROM oimr_invitations WHERE course_Id = %s"
        val = (courseId,)

        try:
            self.gMysqlCur.execute(q, val)
            result = self.gMysqlCur.fetchall()
            result = {r['hash']: r for r in result}
        except mysqlConnErr as e:
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()

        return result

    def get_course_invitations(self, exclude=('commons1', 'tradhall1')):
        self.gMysqlCur = self.get_mysql_cursor(True)
        q = f"SELECT * FROM oimr_invitations{f' WHERE course_Id NOT IN {exclude}' if exclude else ''}"

        try:
            self.gMysqlCur.execute(q)
            result = self.gMysqlCur.fetchall()
            result = {r['hash']: r for r in result}
        except mysqlConnErr as e:
            print(e)
        finally:
            if self.gMysqlCur is not None:
                self.gMysqlCur.close()

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

            self.gMysqlCur = self.get_mysql_cursor(True)
            self.gMysqlCur.executemany(query, data_tupled)
            rows = "{} affected rows in {}".format(self.gMysqlCur.rowcount, tableName)
            self.gMysqlConn.commit()
            return rows

        except mysqlConnErr as e:
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()

    def remove_invitation(self, registrantId, courseId):
        """ Remove invitation  """
        invHash = hash_student(registrantId, courseId)
        q = f"""DELETE FROM oimr_invitations WHERE hash = '{invHash}'"""

        self.gMysqlCur = self.get_mysql_cursor(True)
        dbresult = 0
        try:
            self.gMysqlCur.execute(q)
            dbresult = self.gMysqlCur.rowcount
        except mysqlConnErr as e:
            print(e)
        else:
            self.gMysqlConn.commit()
        finally:
            self.gMysqlCur.close()

        return dbresult

    def add_invitation(self, registrantId, registrantEmail, courseId, invitationId=None, status='SENT'):
        q = """INSERT INTO oimr_invitations
                  (hash, registrant_Id, registrant_email, course_Id, invitation_Id, invitation_status)
               VALUES (%s, %s, %s, %s, %s, %s)"""
        val = (hash_student(registrantId, courseId), registrantId, registrantEmail, courseId, invitationId, status)

        self.gMysqlCur = self.get_mysql_cursor(True)
        try:
            self.gMysqlCur.execute(q, val)
            self.gMysqlConn.commit()
        except mysqlConnErr as e:
            print(e)
        finally:
            if not self.gMysqlCur == None:
                self.gMysqlCur.close()

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

    def exit_connections(self):
        if self.gMysqlConn is not None:
            self.gMysqlConn = None
            logging.debug("########### mysql connection is no more ###########")

        if self.gPaTunnel is not None:
            self.gPaTunnel.Stop
            self.gPaTunnel = None
            logging.debug("########### Tunnel Collapsed ###########")
        print("tunnel of love closed")

def get_pyAnywhereAPI():
    paMysqlDb = PyAnywhereAPI()

    return paMysqlDb


if __name__ == '__main__':
    pass
