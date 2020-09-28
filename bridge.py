"""
OIMR Auto-Enrollment Bridge

Purpose: 
    Read registration data from RegFox, determine enrollments/withdrawals, and
    execute Google API commands to make all necessary updates.

"""

import registration
import enrollment
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

with open('google_secret.json', 'r') as infile: client_config = json.load(infile)
with open('regfox_secret.json', 'r') as infile: regfox_auth = json.load(infile)
with open('slack_secret.json', 'r') as tokenfile: slackauth = json.load(tokenfile)
logging.debug(slackauth)

slack_client = WebClient(**slackauth)

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

def make_commons_enrollment_list(registrants):
    """
    Look at registrations and identify students who do not have a commons enrollment in the db
    """
    logging.debug('make_commons_enrollment_list() started')

    result = []

    # already_enrolled = DB query to pull all students with enrollments in the commons
    already_enrolled = []

    for r in registrants:
        if r.email_addr == 'jeremy.m.welch@gmail.com':
        #if r.email_addr not in already_enrolled:
            result.append(r)

    logging.info('{} students to enroll in commons'.format(len(result)))
    logging.debug(result)
    return result

def enroll_student(registrant, course, google_api):
    """
    Enroll $registrant in $course using the courses.student.invite method
    """
    logging.debug('enroll_student() started with params: registrant={}, course={}'.format(registrant, course))

    # Add domain alias prefix
    alias = 'd:' + course

    try:
        if registrant.email_addr != 'jeremy.m.welch@gmail.com': raise(Exception)
        result = google_api.add_student(courseId=alias, studentEmail=registrant.email_addr)
        logging.debug(result)
        #result = 'enrollment.add_student(courseId={}, studentEmail={})'.format(alias, registrant.email_addr)
    except enrollment.HttpError as e:
        headers, details = e.args
        details = json.loads(details.decode())
        msg = 'Encountered error enrolling {!r} to course {} - {}'.format(registrant, course, details['error']['status'])
        logging.exception(msg)
        post_to_slack(':warning: ' + msg)
        return False
    except:
        logging.exception('Encountered an unexpected error')
    else:
        logging.info('{!r} enrolled in course {} with studentId {}'.format(registrant, course, result['id']))
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
    enroll_in_commons = make_commons_enrollment_list(registrants)
    summary.append('* {} student(s) to enroll in commons'.format(len(enroll_in_commons)))
    if enroll_in_commons:
        status = [0, 0]
        for student in enroll_in_commons:
            if enroll_student(student, 'commons1', google_api): 
                status[0] += 1
            else:
                status[1] += 1
        summary.append('* Enrolled {} in commons ({} error{})'.format(status[0], status[1], 's' if any((not(status[1]), status[1] > 1)) else ''))

    # Make the list of tradhall/corecourse changes
    #change_list = dict(generate_change_list(registrants))
    #logging.debug(change_list)
    #summary.append('* {} students with enrollment changes'.format(len(change_list)))
    
    post_to_slack('\n'.join(summary))
    return


if __name__ == '__main__':
    post_to_slack(':sparkles: Bridge script started :sparkles:')
    regfox_api = registration.RegFoxAPI(**regfox_auth)
    google_api = enrollment.GoogleAPI(client_config)
    main(regfox_api, google_api)