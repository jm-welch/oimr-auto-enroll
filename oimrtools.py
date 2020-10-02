"""
One import to provide all functionality scripted for the retreat, for easy CLI use
"""

import registration as reg
import enrollment as enroll
import OIMRMySQL as SQL
import logging
import json
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
    #try:
    result = google_api.cls_svc.invitations().list(courseId=alias).execute()
    invites.extend(result.get('invitations', []))
    while result.get('nextPageToken'):
        result = google_api.cls_svc.invitations().list(courseId=alias, pageToken=result['nextPageToken']).execute()
        invites.extend(result.get('invitations', []))
    # except:
    #     invites = []
    logging.info('{} unaccepted invitations for {}'.format(len(invites), course_id))

def invitation_accepted(invitation_id):
    try:
        result = google_api.cls_svc.invitations().get(id=invitation_id)
    except:
        result = []
    
    return bool(result)

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
        try:
            google_api.cls_svc.invitations().get(id=dbresult['invitation_Id']).execute()
        except:
            logging.info('Student has accepted invitation.')
        else:
            logging.info('Student has not accepted invitation.')
    try:
        google_api.cls_svc.courses().students().get(courseId=enroll.course_alias(course_id), userId=registrant.email_addr).execute()
    except:
        logging.info('Student email not found in course enrollments.')
    else:
        logging.info('Student email found in course enrollments.')
