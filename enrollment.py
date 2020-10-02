#!/usr/bin/python3.7
from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json
import logging

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user',
    'https://www.googleapis.com/auth/admin.directory.group',
    'https://www.googleapis.com/auth/classroom.rosters',
    'https://www.googleapis.com/auth/classroom.courses',
    'https://www.googleapis.com/auth/classroom.profile.emails',
    'https://www.googleapis.com/auth/classroom.profile.photos'
]

def course_alias(courseId):
    """ Take a courseId and return the domain alias. Ex: 'BZK' -> 'd:BZK' """
    return 'd:' + courseId

class GoogleAPI():
    def __init__(self, client_config=None):
        self.auth(client_config)

    def auth(self, client_config=None, scopes=SCOPES):
        # Perform auth and return service
        
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    client_config, scopes)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.dir_svc = build('admin', 'directory_v1', credentials=creds)
        self.cls_svc = build('classroom', 'v1', credentials=creds)

    def add_group_member(self, group_id, email):
        # Add a member to a group in the domain
        args = {
            'groupKey': group_id,
            'body': {
                'email': email
            }
        }

        result = self.dir_svc.members().insert(**args)

    def list_courses(self):
        # List all Classrooms in the domain

        courses = self.cls_svc.courses().list().execute()
        return courses['courses']

    def get_user_from_id(self, u_id):
        # Fetch a user's data using their ID
        user = self.cls_svc.userProfiles().get(userId=u_id).execute()
        return user

    def create_course(self, body):
        """ Create course with body """
        # API Ref: http://googleapis.github.io/google-api-python-client/docs/dyn/classroom_v1.courses.html#create

        try:
            course = self.cls_svc.courses().create(body=body).execute()
        except HttpError as e:
            headers, details = e.args
            details = json.loads(details.decode())
            logging.exception('Error creating course {} - {}'.format(body.get('id', body), details['error'].get('status')))
            course = None
        finally:
            return course

    def remove_course(self, courseAlias):
        try:
            self.cls_svc.courses().delete(id=courseAlias).execute()
        except:
            pass

    def add_student(self, courseId, studentEmail, role='STUDENT'):
        # Invite a student to join a Classroom
        body = {
            'courseId': courseId,
            'userId': studentEmail,
            'role': role
        }
        enrollment = self.cls_svc.invitations().create(body=body).execute()
        return enrollment

    def add_teacher(self, courseId, teacherEmail):
        # Add a teacher
        
        courseAlias = 'd:'+courseId

        body = {
            'userId': teacherEmail
        }

        try:
            result = self.cls_svc.courses().teachers().create(courseId=courseAlias, body=body).execute()
        except HttpError as e:
            headers, details = e.args
            details = json.loads(details.decode())
            logging.exception('Error adding teacher {} to course {} - {}'.format(teacherEmail, courseId, details['error'].get('status')))
            result = None
        finally:
            return result
        
        



def get_GoogleApi():
    api = GoogleAPI()
    return api


if __name__ == '__main__':
    api = get_GoogleApi()

    oimrGoogleCourses = api.list_courses()
    print('done')

