import enrollment
import courses
import json
import logging

logging.basicConfig(
    level=logging.DEBUG,
    filename='classes.log',
    format='%(asctime)s %(levelname)s (%(module)s:%(funcName)s:%(lineno)d) - %(msg)s'
)

teacher_list = [
    'lisha.haughton',
    'jeremy.welch',
    'brian.shaw',
    'erica.braverman',
    'sarah.rose',
    'registration',
    'events'
]
teacher_list = [e+'@irishtradmusic.org' for e in teacher_list]

courses_created = []

with open('google_secret.json', 'r') as infile: 
    client_config = json.load(infile)

def course_callback(request_id, response, exception):
    if exception is not None:
        logging.error('Unable to create course {} - {}'.format(request_id, exception))
    else:
        logging.info('Created course {} {}'.format(response.get('name'), response.get('section')))
        courses_created.append(response.get('id'))

def create_courses(api, courses):
    logging.debug('Creating courses')
    batch = api.cls_svc.new_batch_http_request(callback=course_callback)

    for course_id, course_data in courses.items():
        course_alias = 'd:' + course_id
        ta_string = 'Your TA is {}. They will post lessons on behalf of your instructor, and can be contacted with any questions or issues.'.format(course_data['ta'])

        body = {
            'id': course_alias,
            'name': course_data['name'],
            'section': 'with {}'.format(course_data['instructor']),
            'description': ta_string,
            'ownerId': 'oimr@irishtradmusic.org',
            'courseState': 'ACTIVE',
        }

        request = api.cls_svc.courses().create(body=body)
        batch.add(request)

    logging.debug(batch)

    batch.execute()
    

def teacher_callback(request_id, response, exception):
    if exception is not None:
        logging.error('Unable to add teacher {} to course - {}'.format(request_id, exception))
    else:
        logging.info('Added teacher {} to course {}'.format(
            response.get('profile').get('emailAddress'),
            response.get('courseId')
            ))

def add_teachers(api, teachers, courses):
    for course in courses:
        batch = api.cls_svc.new_batch_http_request(callback=teacher_callback)

        for teacher in teachers:
            body = {'userId': teacher}
            request = api.cls_svc.courses().teachers().create(courseId=course, body=body)
            batch.add(request)
        
        batch.execute()

def main():
    logging.debug('main() started')
    
    gapi = enrollment.GoogleAPI(client_config)
    
    create_courses(gapi, courses.COURSES)
    logging.debug('Courses created: {}'.format(courses_created))
    add_teachers(gapi, teacher_list, clist)


if __name__ == '__main__':
    logging.info('Classroom create script started')
    main()
    logging.info('Script completed')