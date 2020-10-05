#!/usr/bin/env python3.7

"""
OIMR Auto-Enrollment Bridge

Purpose:
    Read registration data from RegFox, determine enrollments/withdrawals, and
    execute Google API commands to make all necessary updates.
"""

import registration
import enrollment
import OIMRMySQL
import courses
import logging
import json
from slack import WebClient
from slack.errors import SlackApiError

logging.basicConfig(
    level=logging.INFO,
    filename='bridge.log',
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

logging.info("########### Bridge script started ###########")

with open('sql_secret.json', 'r') as infile: sql_creds = json.load(infile)
logging.debug('Connecting to MySQL server...')
try:
    sql = OIMRMySQL.SQL(**sql_creds)
except:
    logging.exception('Failed to connect to DB')
else:
    logging.info("DB connection successful")

sekrets = sql.get_sekrets()

slack_client = WebClient(**sekrets['slack'])

def post_to_slack(message, channel='G01BV8478D7'):
    """
    Post $message to Slack in $channel (default=#enrollment-feed)
    """
    logging.debug('post_to_slack() started with arguments:\n message: {}\n channel: {}'.format(message, channel))

    body = {
        'channel': channel,
        'text': message
    }

    try:
        response = slack_client.chat_postMessage(**body)
    except SlackApiError as e:
        logging.exception('Error sending message to Slack')

def get_regfox_data(regfox_api):
    """
    Fetch registrant data from RegFox, and return it as a RegistrantList object
    """
    logging.debug('get_regfox_data() started')
    registrants = regfox_api.get_registrants()
    registrants = registration.RegistrantList(registrants)
    logging.info('Registrant list fetched with {} entries.'.format(len(registrants)))
    return registrants

def make_commons_invite_list(registrants):
    """
    Look at registrations and identify students who do not have a commons enrollment in the db
    """
    logging.debug('make_commons_invite_list() started')

    result = []

    # already_invited = DB query to pull all students with enrollments in the commons
    already_invited = sql.get_commons_invitations()
    logging.debug(already_invited)

    for r in registrants:
        invHash = OIMRMySQL.hash_student(r.registrationId, 'commons1')
        if invHash not in already_invited:
            result.append(r)

    logging.info('{} students to enroll in commons'.format(len(result)))
    logging.debug(result)
    return result

def invite_student(registrant, courseId, google_api):
    """
    Invite $registrant to $course using the courses.student.invite method
    """
    logging.debug('invite_student() started with params: registrant={}, course={}'.format(registrant, courseId))

    # Add domain alias prefix
    alias = 'd:' + courseId

    try:
        result = google_api.add_student(courseId=alias, studentEmail=registrant.email_addr)
        logging.debug(result)
    except enrollment.HttpError as e:
        headers, details = e.args
        details = json.loads(details.decode())
        msg = 'Encountered error inviting {!r} to course {} - {}'.format(registrant, courseId, details['error']['status'])
        # Silence errors on future runs by adding with null invitationId and an error code
        sql.add_invitation(registrant.registrationId, registrant.email_addr, courseId, status='ERR:{}'.format(details['error']['status']))
        logging.exception(msg)
        post_to_slack(':warning: ' + msg)
        return False
    except:
        logging.exception('Encountered an unexpected error')
    else:
        logging.info('{!r} invited to course {} with studentId {}'.format(registrant, courseId, result['id']))
        sql.add_invitation(registrant.registrationId, registrant.email_addr, courseId, invitationId=result['id'])
        # DB insert to add student to students table with studentId from response
        return True

def generate_change_list(registrants):
    """
    GENERATOR METHOD - NOT FUNCTION
    Iterate over registrants, comparing against enrollments from DB
    When changes need to occur, yield result
    """
    logging.debug('change_list() started')

    # DB call to pull all enrollments except commons from DB
    enrollments = []

    for r in registrants:
        # Find courses needing enrollment
        courses_to_add = []
        if r.core_courses:
            for course in r.core_courses:
                if (r.oimr_id, course) not in enrollments:
                    courses_to_add.append(course)
        if r.extras and (r.oimr_id, 'tradhall1') not in enrollments:
            courses_to_add.append('tradhall1')

        # Find courses needing withdrawal
        courses_to_remove = []
        # Iterate enrollments for student
        # Append courses no longer in registration

        # Only yield result if there are changes
        if courses_to_add or courses_to_remove:
            yield r, {'add': courses_to_add, 'remove': courses_to_remove}


def main(regfox_api, google_api):
    logging.debug('main block started')
    logging.debug(regfox_api)
    logging.debug(google_api)

    summary = ['Execution summary:\n']

    # Get registered students from RegFox
    registrants = get_regfox_data(regfox_api)

    # Deal with The Commons
    enroll_in_commons = make_commons_invite_list(registrants)
    summary.append('* {} student(s) to invite to Commons'.format(len(enroll_in_commons)))
    if enroll_in_commons:
        status = [0, 0]
        for student in enroll_in_commons:
            if invite_student(student, 'commons1', google_api):
                status[0] += 1
            else:
                status[1] += 1
        summary.append('* Invited {} to commons ({} error{})'.format(status[0], status[1], 's' if any((not(status[1]), status[1] > 1)) else ''))

    # Make the list of tradhall/corecourse changes
    #change_list = dict(generate_change_list(registrants))
    #logging.debug(change_list)
    #summary.append('* {} students with enrollment changes'.format(len(change_list)))

    post_to_slack('\n'.join(summary))
    return


if __name__ == '__main__':
    post_to_slack(':sparkles: Bridge script started :sparkles:')
    regfox_api = registration.RegFoxAPI(**sekrets['regfox'])
    google_api = enrollment.GoogleAPI(sekrets['google'])
    main(regfox_api, google_api)