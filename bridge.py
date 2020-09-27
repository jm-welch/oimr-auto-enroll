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

logging.basicConfig(
    level=logging.DEBUG,
    #filename='bridge.log',
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

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
        if r.email_addr not in already_enrolled:
            result.append(r)

    logging.info('{} students to enroll in commons'.format(len(result)))
    logging.debug(result)
    return result

def enroll_student(registrant, course):
    """
    Enroll $registrant in $course using the courses.student.invite method
    """
    logging.debug('enroll_student() started with params: registrant={}, course={}'.format(registrant, course))

    try:
        #result = enrollment.add_student(courseId=course, studentEmail=registrant.email_addr)
        result = 'enrollment.add_student(courseId={}, studentEmail={})'.format(course, registrant.email_addr)
        if registrant.email_addr == 'jeremy.m.welch@gmail.com': raise(Exception)
        logging.debug(result)
        # DB insert to add student to students table with studentId from response
    except Exception as e:
        logging.exception('Encountered error enrolling student ({}) to course ({})'.format(registrant, course))

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
    
    # Get registered students from RegFox
    registrants = get_regfox_data(regfox_api)

    # Deal with The Commons
    #enroll_in_commons = make_commons_enrollment_list(registrants)
    enroll_in_commons = []
    if enroll_in_commons:
        for student in enroll_in_commons:
            enroll_student(student, 'd:commons1')

    change_list = dict(generate_change_list(registrants))
    logging.debug(change_list)

    
    return


if __name__ == '__main__':
    regfox_api = registration.RegFoxAPI('regfox_secret.json')
    google_api = enrollment.API()
    main(regfox_api, google_api)