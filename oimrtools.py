"""
One import to provide all functionality scripted for the retreat, for easy CLI use
"""

import registration as reg
import enrollment as enroll
import OIMRMySQL as SQL
import pyAnyConnect as paSQL
import logging
import json
from collections import Counter
from slack import WebClient
from slack.errors import SlackApiError
import courses

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

logging.debug('Connecting to MySQL server...')

with paSQL.get_pyAnywhereAPI() as sql:
    pConn = sql.make_mysql_connection(False)

sekrets = sql.get_sekrets()
logging.debug('Connecting to Slack...')
slack_client = WebClient(**sekrets['slack'])

def reconnect():
    connected = sql.gMysqlConn.is_connected()
    logging.info(f"SQL connection is {['down', 'up'][connected]}")
    if not connected:
        logging.info('Attempting reconnect')
        sql.gMysqlConn.connect()


def post_to_slack(message, channel='G01BV8478D7'):
    """
    Post $message to Slack in $channel (default=#enrollment-feed)
    """
    logging.debug('post_to_slack() started')

    body = {
        'channel': channel,
        'text': message
    }

    try:
        response = slack_client.chat_postMessage(**body)
    except SlackApiError as e:
        logging.exception('Error sending message to Slack')

logging.debug('Connecting to RegFox and fetching registrant list')
regfox_api = reg.RegFoxAPI(**sekrets['regfox'])

registrants = reg.RegistrantList(regfox_api.get_registrants())

logging.debug("Connecting to Google APIs")
google_api = enroll.GoogleAPI(sekrets['google'])

find_registrant = registrants.find_registrant

### Functions for testing

def list_invitations_for_course(course_id):
    alias = enroll.course_alias(course_id)

    invites = []
    try:
        result = google_api.cls_svc.invitations().list(courseId=alias).execute()
        invites.extend(result.get('invitations', []))
        while result.get('nextPageToken'):
            result = google_api.cls_svc.invitations().list(courseId=alias, pageToken=result['nextPageToken']).execute()
            invites.extend(result.get('invitations', []))
    except:
        invites = []
    logging.info('{} unaccepted invitations for {}'.format(len(invites), course_id))
    return invites

def update_invitation_status():
    db_invites = sql.get_sent_invitations()
    logging.debug(db_invites)
    db_courses = set(x.get('course_Id') for x in db_invites)
    logging.debug(db_courses)

    for course in db_courses:
        g_invites = [i.get('id') for i in list_invitations_for_course(course)]
        for inv in db_invites:
            if all((inv.get('course_Id')==course, inv.get('invitation_Id') not in g_invites)):
                inv['invitation_status'] = 'ACCEPTED'

    sql.table_insert_update('oimr_invitations', db_invites)

    get_invitation_status()

def get_invitation_status():
    q = "select * from invite_totals_vw"
    rows = sql._query(q)
    rows.sort(key=lambda r: r['course_Id'])

    logging.debug(rows)

    result = []

    for row in [{'course_Id': 'ID', 'sent': 'Sent', 'accepted': 'Accepted', 'tot': 'Total', 'unsent': 'Errors'}] + rows:
        result.append(f"{row['course_Id']:10} {row['sent'] or '':<10} {row['accepted']:<10} {row['unsent'] or '':<10} {row['tot']:>10}")

    result.insert(1, '-'*50)

    print('\n'.join(result))

def invitation_accepted(invitation_id):
    try:
        result = google_api.cls_svc.invitations().get(id=invitation_id).execute()
    except:
        result = []

    # If the invitation no loger exists (and the api call therefore throws an exception),
    #  the invitation has been consumed, and therefore is accepted. Otherwise, it's still there.
    #  This is why we invert our result
    return not bool(result)

def find_student(registrant, course_id):
    try:
        assert(type(registrant) is reg.Registrant)
    except AssertionError:
        logging.exception('registrant must be a registrant object')

    # Check for student in DB
    invHash = paSQL.hash_student(registrant.registrationId, course_id)
    q = f"""SELECT * FROM oimr_invitations WHERE hash = '{invHash}'"""
    dbresult = sql._query(q)
    dbresult = dbresult[0] if dbresult else []
    logging.debug(dbresult)
    logging.info('Student {}found in invitations table{}'.format('not ' if not dbresult else '', ' with error' if 'ERR' in dbresult['invitation_status'] else ''))
    logging.debug(dbresult)

    # Check for student in Classroom
    if dbresult:
        logging.info('Student has {}accepted invitation.'.format('not ' if not invitation_accepted(dbresult['invitation_Id']) else ''))
    try:
        google_api.cls_svc.courses().students().get(courseId=enroll.course_alias(course_id), userId=registrant.email_addr).execute()
    except:
        logging.info('Student email not found in course enrollments.')
    else:
        logging.info('Student email found in course enrollments.')

def remove_student(registrant, courseId):
    inv_hash = paSQL.hash_student(registrant.registrationId, courseId)
    q1 = f"""SELECT invitation_Id FROM oimr_invitations WHERE hash = '{inv_hash}'"""

    logging.info('Invite hash: '+inv_hash)

    rows = sql._query(q1)
    if rows:
        logging.info('{} found in invitations table for course {}'.format(registrant, courseId))
        invitationId = rows[0]['invitation_Id']

        dbresult = sql.remove_invitation(registrant.registrationId, courseId)
        if dbresult:
            logging.info('{} removed from invitations table for course {}'.format(registrant, courseId))
    else:
        logging.info('{} invite to {} not found in invitations table'.format(registrant, courseId))
        invitationId = None

    alias = 'd:'+courseId
    if (invitationId and invitation_accepted(invitationId)) or not invitationId:
        try:
            google_api.cls_svc.courses().students().delete(courseId=alias, userId=registrant.email_addr).execute()
        except:
            logging.warn('{} not found in {} classroom'.format(registrant, courseId))
        else:
            logging.info('{} removed from {} classroom'.format(registrant, courseId))
    else:
        try:
            google_api.cls_svc.invitations().delete(id=invitationId).execute()
        except:
            logging.warn('Invitation not found')
        else:
            logging.info('Invitation deleted - you may re-invite.')

def invite_student(registrant, courseId, force=False):
    alias = 'd:'+courseId

    invHash = paSQL.hash_student(registrant.registrationId, courseId)

    if courseId == 'commons1':
        logging.info('Invite {} to the Commons'.format(registrant))
    elif courseId == 'tradhall1':
        if not registrant.extras:
            logging.warning("{} did not register for extras. Nuh-uh, I won't do it.".format(registrant))
            if not force:
                return
            else:
                logging.info('Use of force authorized. Adding anyway.')
        else:
            logging.info('Invite {} to Trad Hall'.format(registrant))
    else:
        if not registrant.core_courses or courseId not in registrant.core_courses:
            logging.warning("{} did not register for {}. Nuh-uh, I won't do it.".format(registrant, courseId))
            if not force:
                return
            else:
                logging.info('Use of force authorized. Adding anyway.')
        else:
            logging.info('Invite {} to {}'.format(registrant, courseId))

    try:
        result = google_api.add_student(courseId=alias, studentEmail=registrant.email_addr)
    except:
        logging.exception('Unable to add student to classroom')
    else:
        logging.info('Student invited to classroom with id {}'.format(result.get('id')))
        sql.add_invitation(registrant.registrationId, registrant.email_addr, courseId, invitationId=result.get('id'))

def get_invite_errors():
    q = """SELECT * FROM oimr_invitations WHERE invitation_status LIKE 'ERR%'"""

    dbrows = sql._query(q)

    output = {}

    for r in dbrows:
        registrant = registrants.find_registrant(r.get('registrant_Id'))
        logging.info('Course: {} - {!r} - Error: {}'.format(r.get('course_Id'), registrant, r.get('invitation_status')))
        r['registrant'] = registrant
        output[r.get('hash')] = r

    return output

def resend_invite(registrant, courseId):
    remove_student(registrant, courseId)
    invite_student(registrant, courseId)
