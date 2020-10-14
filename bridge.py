#!/usr/bin/env python3.7
"""
OIMR Auto-Enrollment Bridge

Purpose:
    Read registration data from RegFox, determine enrollments/withdrawals, and
    execute Google API commands to make all necessary updates.

"""

import sys
import traceback
import pyAnyConnect as OIMRMySQL
import registration
import enrollment
import traceback
import courses
import logging
import json
from slack import WebClient
from slack.errors import SlackApiError

logging.basicConfig(
    level=logging.DEBUG,
    filename='bridge.log',
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

logging.info("########### tunnel script started ###########")

# OIMRMySQL checks for the existence tunnel_secrets.json so no need to put it here.
# sql is the returned API not the connection or cursor so we retrieve the connection as pconn and subsequent mysqly calls will open cursors in the sql interface as well as close on completion.
# connection and tunnel will remain open until end of the run of this file.
with OIMRMySQL.get_pyAnywhereAPI() as sql:
    logging.debug('Get PyAnywhere Class (tunnel)...')
    if not sql.gPaTunnel == None:
        # use the tunnel connection which will have the additional port
        try:
            pConn = sql.make_mysql_connection(True)
        except:
            msg = traceback.print_exception()
            print(msg)
        # Do tunnel things
    else:
        try:
            # otherwise use a local connection up in pythonAnywhere using limited local creds
            pConn = sql.make_mysql_connection(False)

        except:
            msg = sys.exc_info()[2]
            # traceback.print_exception(sys.etype,sys.value, sys.tb)
            print(msg)
            # TODO: MAY WANT TO HANDLE HOW

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
    # Post unique reg count to Slack so we can keep an eye on it
    post_to_slack('{} registrants fetched from RegFox'.format(registrants.registrant_count))
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
        post_to_slack(f':heav-check-mark: {registrant} successfully invited to {courseId}')
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


def mysql_update_registrants(registrants):
    """
     Create a hash of the registrant's full name,
     date of birth, and email to serve as a unique ID  and class registration
     """
    studentsRegistered = []
    for student in registrants:
        student_Registered = {
            'First_Name': student.get_path('name.first').get('value'),
            'Last_Name': student.get_path('name.last').get('value'),
            'registrant_id': student.registrationId,
            'Email': student.email_addr,
            'registrant_json': json.dumps(student._raw)
        }
        
        studentsRegistered.append(student_Registered)

    return studentsRegistered

def main(regfox_api, google_api):
    logging.debug('main block started')
    logging.debug(regfox_api)
    logging.debug(google_api)
    summary = [':scroll: Execution summary: :scroll:\n']

    # Get registered students from RegFox
    registrants = get_regfox_data(regfox_api)
    # update registrants in Mysql Database
    regDict = mysql_update_registrants(registrants)
    regUpdate = sql.table_insert_update('oimr_registrations', regDict)
    logging.info(regUpdate)

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
    summary.append(' END SUMMARY')
    post_to_slack('\n:scroll:'.join(summary))
    return
    # lets clean up any stragglers


if __name__ == '__main__':
    post_to_slack(':sparkles: Bridge script started :sparkles:')
    regfox_api = registration.RegFoxAPI(**sekrets['regfox'])
    google_api = enrollment.GoogleAPI(sekrets['google'])
    main(regfox_api, google_api)
    sql.exit_connections
