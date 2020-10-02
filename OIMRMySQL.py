import MySQLdb as sql
from MySQLdb._exceptions import OperationalError
import hashlib
import json

def load_creds():
    with open('sql_secret.json') as infile:
        creds = json.load(infile)
    return creds

def hash_student(registrantId, courseId):
    string_to_hash = registrantId + courseId
    hashed_string = hashlib.md5(string_to_hash.encode()).hexdigest()
    return hashed_string

class SQL():
    def __init__(self, host, userName, dbPass, dbName):
        self.creds = {
            'host': host,
            'user': userName,
            'passwd': dbPass,
            'db': dbName
        }
        self.connect(self.creds)

    def connect(self, creds):
        self.conn = sql.connect(**creds)

    def ping(self):
        try:
            self.conn.ping()
        except OperationalError:
            self.connect(self.creds)
        finally:
            try:
                self.conn.ping()
                return True
            except:
                return False

    @property
    def cursor(self):
        """ Make sure the connection is still alive and get a cursor """
        if self.ping():
            cur = self.conn.cursor()
        else:
            raise Exception

        return cur

    def get_sekrets(self):
        cur = self.cursor
        q = 'SELECT * FROM sekrets'
        try:
            cur.execute(q)
            result = cur.fetchall()
            result = {x: json.loads(y) for x,y in result}
        except:
            result = None
        finally:
            cur.close()
        
        return result

    def update_course_invites(self, pending_invites):
        cur = self.cursor
        q1 = """SELECT invitation_Id FROM oimr_invitations WHERE invitation_Status = 'SENT'"""
        q2 = """UPDATE oimr_invitations SET invitatation_status = 'ACCEPTED' WHERE invitation_Id = %s"""

        try:
            cur.execute(q1)
            result = [r[0] for r in cur.fetchall()]
        except:
            result = None
        
        if result:
            accepted = [(i,) for i in result if i not in pending_invites]
            cur.executemany(q2, accepted)
            self.conn.commit()
            
                
    
    def get_student_in_course(self, studentId, courseId):
        cur = self.cursor
        q = "SELECT * FROM oimr_invitations WHERE registrant_Id = %s AND course_Id = %s"
        val = (studentId, courseId)

        try:
            cur.execute(q, val)
            result = cur.fetchall()
        except:
            result = None
        finally:
            cur.close()
        
        return result

    def get_commons_invitations(self):
        return self.get_invitations_for_course('commons1')

    def get_invitations_for_course(self, courseId):
        cur = self.cursor
        q = "SELECT registrant_email FROM oimr_invitations WHERE course_Id = %s"
        val = (courseId,)

        try:
            cur.execute(q, val)
            result = cur.fetchall()
            result = [r[0] for r in result]
        except:
            result = None
        finally:
            cur.close()

        return result

    def add_invitation(self, registrantId, registrantEmail, courseId, invitationId=None, status='SENT'):
        q = """INSERT INTO oimr_invitations 
                  (hash, registrant_Id, registrant_email, course_Id, invitation_Id, invitation_status)
               VALUES (%s, %s, %s, %s, %s, %s)"""
        val = (hash_student(registrantId, courseId), registrantId, registrantEmail, courseId, invitationId, status)

        cur = self.cursor

        cur.execute(q, val)
        self.conn.commit()


if __name__ == '__main__':
    pass