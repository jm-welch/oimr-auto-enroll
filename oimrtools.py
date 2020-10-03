"""
One import to provide all functionality scripted for the retreat, for easy CLI use
"""

import registration as reg
import enrollment as enroll
import OIMRMySQL as SQL
import logging
import json
from collections import Counter
from slack import WebClient
from slack.errors import SlackApiError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

logging.debug('Connecting to MySQL server...')

try:
    with open('sql_secret.json', 'r') as infile:
        sql = SQL.SQL(**json.load(infile))
except:
    logging.exception('Failed to connect to DB')
    quit()
else:
    logging.info("DB connection successful")
    sekrets = sql.get_sekrets()

logging.debug('Connecting to Slack...')
slack_client = WebClient(**sekrets['slack'])

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

def update_invitations_for_course(courseId):
    invites = list_invitations_for_course(courseId)
    invites = tuple(i.get('id') for i in invites)

    q = """UPDATE oimr_invitations 
           SET invitation_status='ACCEPTED' 
           WHERE 
               invitation_status='SENT' AND 
               invitation_id NOT IN {}""".format(invites)

    c = sql.cursor()
    try:
        r = c.execute(q)
    except:
        logging.exception('Failed to update DB')
    else:
        sql.commit()
        logging.info('Updated {} rows'.format(r))

    q2 = """SELECT invitation_status FROM oimr_invitations"""
    try:
        r = c.execute(q2)
    except:
        logging.exception("DB Query failed")
    else:
        results = c.fetchall()
        logging.info('Breakdown for {} - {}'.format(courseId, Counter((i[0] for i in results))))
    
    c.close()

def invitation_accepted(invitation_id):
    try:
        result = google_api.cls_svc.invitations().get(id=invitation_id).execute()
    except:
        result = []
    
    return not bool(result)

def find_student(registrant, course_id):
    try:
        assert(type(registrant) is reg.Registrant)
    except AssertionError:
        logging.exception('registrant must be a registrant object')
    
    # Check for student in DB
    q1 = """SELECT * FROM oimr_invitations WHERE registrant_Id = %s"""
    v1 = (registrant.registrationId, )
    cur = sql.cursor(d=True)
    rows = cur.execute(q1, v1)
    dbresult = cur.fetchone()
    logging.info('Student {}found in invitations table'.format('not ' if not rows else ''))
    logging.debug(dbresult)

    # Check for student in Classroom
    if rows:
        logging.info('Student has {}accepted invitation.'.format('not ' if not invitation_accepted(dbresult['invitation_Id']) else ''))
    try:
        google_api.cls_svc.courses().students().get(courseId=enroll.course_alias(course_id), userId=registrant.email_addr).execute()
    except:
        logging.info('Student email not found in course enrollments.')
    else:
        logging.info('Student email found in course enrollments.')

def remove_student(registrant, courseId):
    q1 = """SELECT invitation_Id FROM oimr_invitations WHERE hash = %s"""
    inv_hash = SQL.hash_student(registrant.registrationId, courseId)
    val = (inv_hash, )
    logging.info('Invite hash: '+inv_hash)
    
    c = sql.cursor(d=True)
    rows = c.execute(q1, val)
    if rows:
        logging.info('{} found in invitations table for course {}'.format(registrant, courseId))
        result = c.fetchone()
        invitationId = result['invitation_Id']
    
        q2 = """DELETE FROM oimr_invitations WHERE hash = %s"""
        if c.execute(q2, val):
            logging.info('{} removed from invitations table for course {}'.format(registrant, courseId))
            sql.commit()
    else:
        logging.info('{} invite to {} not found in invitations table'.format(registrant, courseId))
        invitationId = None
        
    c.close()
    
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
    #TODO: Make 'force' force the add, even if it's not in their registration
    alias = 'd:'+courseId

    invHash = SQL.hash_student(registrant.registrationId, courseId)

    if courseId == 'commons1':
        logging.info('Invite {} to the Commons'.format(registrant))
    elif courseId == 'tradhall1':
        if not registrant.extras:
            logging.warning("{} did not register for extras. Nuh-uh, I won't do it.".format(registrant))
            return
        else:
            logging.info('Invite {} to Trad Hall'.format(registrant))
    else:
        if courseId not in registrant.core_courses:
            logging.warning("{} did not register for {}. Nuh-uh, I won't do it.".format(registrant, courseId))
            return
        else:
            logging.info('Invite {} to {}'.format(registrant, courseId))

    try:
        result = google_api.cls_svc.invitations().create(courseId=alias, userId=registrant.email_addr).execute()
    except:
        logging.exception('Unable to add student to classroom')
    else:
        logging.info('Student invited to classroom with id {}'.format(result.get('id')))
        q = """INSERT INTO oimr_invitations (hash, registrant_id, registrant_email, invitation_id, invitation_status, course_id)
               VALUES (%s, %s, %s, %s, %s, %s)"""
        v = (
            invHash, 
            registrant.registrationId,
            registrant.email_addr,
            result.get('id'),
            'SENT',
            courseId
            )
        c = sql.cursor()
        if c.execute(q, v):
            logging.info('Invite added to DB with hash {}'.format('invHash'))
        else:
            logging.error('Invite could not be added to DB')
        c.close()
