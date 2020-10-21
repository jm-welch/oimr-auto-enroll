#!/usr/bin/python3.7
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

def post_markdown_to_slack(message, channel='G01BV8478D7'):
    """
    Post $message to Slack in $channel as a markdown block
    """

    body = {
        "channel": channel,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]
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
    post_to_slack(':hash: {} registrants fetched from RegFox'.format(registrants.registrant_count))
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

def list_invitations_for_course(course_id, google_api):
    alias = enrollment.course_alias(course_id)

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

def update_course_invitations(google_api):
    db_invites = sql.get_sent_invitations()
    db_courses = set(x.get('course_Id') for x in db_invites)

    for course in db_courses:
        g_invites = [i.get('id') for i in list_invitations_for_course(course, google_api)]
        for inv in db_invites:
            if all((inv.get('course_Id')==course, inv.get('invitation_Id') not in g_invites)):
                inv['invitation_status'] = 'ACCEPTED'

    sql.table_insert_update('oimr_invitations', db_invites)

def get_invitation_status():
    q = "select * from invite_totals_vw"
    rows = sql._query(q)
    rows.sort(key=lambda r: r['course_Id'])

    logging.debug(rows)

    result = []

    for row in [{'course_Id': 'ID', 'sent': 'Sent', 'accepted': 'Accepted', 'tot': 'Total', 'unsent': 'Errors'}] + rows:
        result.append(f"{row['course_Id']:10} | {row['sent'] or '':<10} | {row['accepted']:<10} | {row['unsent'] or '':<10} | {row['tot']:>10}")

    result.insert(1, '-'*60)

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
        post_to_slack(f':eight_spoked_asterisk: {registrant!r} successfully invited to {courses.course_title_with_code(courseId)}')
        if f"{courseId}L1" in registrant.qa_forums:
            post_to_slack(f":interrobang: @here {registrant} signed up for {courseId} Q&A - notify {courses.ta_for_course(courseId)} to update lessons.")
        return True

def remove_student(registrant, courseId, googleApi):
    """
    Do nothing for now, just post to Slack
    """
    post_to_slack(f':eight_pointed_black_star: Remove {registrant!r} from {courses.course_title_with_code(courseId)}.')

def process_changes(googleApi, registrant, add, remove):
    for courseId in add or []:
        invite_student(registrant, courseId, googleApi)
    for courseId in remove or []:
        remove_student(registrant, courseId, googleApi)

def generate_change_list(registrants):
    """
    GENERATOR METHOD - NOT FUNCTION
    Iterate over registrants, comparing against enrollments from DB
    When changes need to occur, yield result
    """
    logging.debug('generate_change_list() started')

    # DB call to pull all enrollments except commons from DB
    enrollments = sql.get_course_invitations(exclude=('commons1', 'PNM'))

    for r in registrants:
        # Find courses needing enrollment
        courses_to_add = []
        if r.core_courses:
            for course in r.core_courses:
                if OIMRMySQL.hash_student(r.registrationId, course) not in enrollments:
                    courses_to_add.append(course)
        if r.extras and OIMRMySQL.hash_student(r.registrationId, 'tradhall1') not in enrollments:
            courses_to_add.append('tradhall1')

        # Find courses needing withdrawal
        this_enrollment = [v for k,v in enrollments.items() if v.get('registrant_Id') == r.registrationId]
        this_enrollment = [e.get('course_Id') for e in this_enrollment]
        this_core_courses = [c for c in this_enrollment if len(c) == 3]
        logging.debug(this_enrollment)
        if r.core_courses:
            courses_to_remove = [e for e in this_core_courses if e not in r.core_courses]
        else:
            courses_to_remove = [e for e in this_core_courses]
        if all((not r.extras ,'tradhall1' in this_enrollment)):
            courses_to_remove.append('tradhall1')

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
    summary.append(':small_blue_diamond: {} student(s) to invite to Commons'.format(len(enroll_in_commons)))
    if enroll_in_commons:
        status = [0, 0]
        for student in enroll_in_commons:
            if invite_student(student, 'commons1', google_api):
                status[0] += 1
            else:
                status[1] += 1
        summary.append(':small_blue_diamond: Invited {} to commons ({} error{})'.format(status[0], status[1], 's' if any((not(status[1]), status[1] > 1)) else ''))

    # Process the list of tradhall/corecourse changes
    [process_changes(google_api, reg, **changes) for reg, changes in generate_change_list(registrants) or []]

    #summary.append('* {} students with enrollment changes'.format(len(change_list)))
    update_course_invitations(google_api)

    post_to_slack('\n'.join(summary))
    post_to_slack(':small_blue_diamond: Invitation status:')
    post_markdown_to_slack("```\n" + '\n'.join(get_invitation_status()) + "\n```")
    return


if __name__ == '__main__':
    post_to_slack(':sparkles: Bridge script started :sparkles:')
    regfox_api = registration.RegFoxAPI(**sekrets['regfox'])
    google_api = enrollment.GoogleAPI(sekrets['google'])
    main(regfox_api, google_api)
    sql.exit_connections()
