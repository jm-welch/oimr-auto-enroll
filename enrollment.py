#!/usr/bin/python3.7
from __future__ import print_function
import pickle
import os.path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pythonAnywhereConnect as pa

oimrDb = pa.get_pyAnywhereAPI()

# If modifying these scopes, delete the file token.pickle.
SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user',
    'https://www.googleapis.com/auth/admin.directory.group',
    'https://www.googleapis.com/auth/classroom.rosters',
    'https://www.googleapis.com/auth/classroom.courses',
    'https://www.googleapis.com/auth/classroom.profile.emails',
    'https://www.googleapis.com/auth/classroom.profile.photos'
]

cred_file = 'google_secret.json'

class API():
    def __init__(self):
        self.auth()

    def auth(self, scopes=SCOPES):
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
                flow = InstalledAppFlow.from_client_secrets_file(
                    cred_file, scopes)
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

    def add_student(self, courseId, studentEmail, role='STUDENT'):
        # Invite a student to join a Classroom
        body = {
            'courseId': courseId,
            'userId': studentEmail,
            'role': role
        }
        enrollment = self.cls_svc.invitations().create(body=body).execute()
        return enrollment


def get_GoogleApi():
    api = API()
    return api


if __name__ == '__main__':
    api = get_GoogleApi()

    oimrGoogleCourses = api.list_courses()
    print('done')
