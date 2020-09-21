#!/usr/bin/python3.7
import pythonAnywhereConnect as pa
from pythonAnywhereConnect import PyAnywhereAPI as db
import courses
import requests
import re
import json
import datetime
from collections import UserList, Counter
import hashlib

oimrDb = pa.get_pyAnywhereAPI()

DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"


class RegistrantList(UserList):
    def __init__(self, data=[]):
        # Store as raw input
        self._data = data
        # Remove invalid entries
        self.data = [Registrant(d) for d in self.validate(data)]

    @property
    def _raw(self):
        return [Registrant(d) for d in self._data]

    @property
    def registrant_count(self):
        """ Count unique registrants, using Registrant.oimr_id as a key """
        return len(set(r.oimr_id for r in self.data))

    def validate(self, data):
        return [d for d in data if d.get('status') == 'completed']

    def core_course_count(self):
        course_count = Counter({c: 0 for c in courses.COURSES})
        for r in self.data:
            if r.core_courses:
                course_count.update(r.core_courses)
        return course_count

    def live_qa_count(self):
        qa_count = Counter({qa: 0 for qa in courses.list_all_liveQA()})
        for r in self.data:
            if r.qa_forums:
                qa_count.update(r.qa_forums)

        return qa_count

    def regs_by_course(self, course):
        return [r.emailAddr for r in self.data if course in r.core_courses]

    def date_list(self):
        result = [r.dateCreated.replace(minute=0, second=0) for r in self.data]
        return result

    def hourly_count(self, start='2020-08-22 13:00'):
        result = {}
        timestamp = datetime.datetime.strptime(start, '%Y-%m-%d %H:%M')
        while timestamp < datetime.datetime.utcnow():
            c = len([r for r in self.data if r.dateCreated.replace(minute=0, second=0) == timestamp])
            result[timestamp] = c
            timestamp += datetime.timedelta(hours=1)

        return result

    def duplicate_registrations(self):
        dupe_ids = Counter(r.oimr_id for r in self.data)
        dupe_ids = [x for x in dupe_ids if dupe_ids[x] > 1]
        dupe_items = [r for r in self.data if r.oimr_id in dupe_ids]
        for d in dupe_items:
            print('\n'.join([
                d.full_name,
                d.email_addr,
                d.get_path('dateOfBirth').get('value'),
                'Core Courses: {}'.format(d.core_courses),
                'QA Forums   : {}'.format(d.qa_forums),
                'Extras      : {}'.format(d.extras)
            ]) + '\n')

    @property
    def country_count(self):
        return Counter([r.get_path('address.country').get('value') for r in self.data])

    @property
    def income(self):
        total = sum([r.total for r in self.data])
        donations = sum([r.donation for r in self.data])
        registrations = total - donations

        result = {
            'registrations': registrations,
            'donations': donations,
            'total': total
        }

        return result

    @property
    def age_breakdown(self):
        age_ranges = (
            (12, 17),
            (18, 29),
            (30, 39),
            (40, 49),
            (50, 59),
            (60, 69),
            (70, 79),
            (80, 89)
        )

        def age_to_range(age):
            if age > 89:
                return '90+'

            for b, t in age_ranges:
                if b <= age <= t:
                    return '{}-{}'.format(b, t)

        result = Counter({'{}-{}'.format(*x): 0 for x in age_ranges})
        result.update({'80+': 0})

        for r in self.data:
            result.update([age_to_range(r.age)])

        return result

    def print_report(self, include_age=False, include_courses=False, include_qa=False):
        fmt = '{:^8} | {}'
        line_fmt = '{0:-^8} | {0:-^68}'

        counts = (
            len(self.data),
            self.registrant_count,
            len(self.data) - self.registrant_count
        )

        report = []
        report.append('Report time: {}'.format(datetime.datetime.now().isoformat()))
        report.append('\nTotal registrants: {} ({} unique, {} duplicates)'.format(*counts))

        # Finance
        report.append('\nFinances\n========')
        report.append(
            'Total from registrations : ${registrations:.02f}\nTotal from donations     : ${donations:.02f}\nTotal income before fees : ${total:.02f}\n'.format(
                **self.income))

        if include_age:
            # Age
            report.append('\nAge Breakdown\n=============')
            report.append('Age range: {}-{}\n'.format(min(r.age for r in self.data), max(r.age for r in self.data)))
            for data in self.age_breakdown.items():
                report.append('{:6}: {}'.format(*data))
            report.append('\n\n')

        if include_courses:
            # Core Courses
            report.append('Core Course Registration\n{}\n'.format('=' * 24))
            report.append('Count: {}\n'.format(sum(self.core_course_count().values())))

            report.append(fmt.format('Students', 'Course'))
            report.append(line_fmt.format('-'))
            for course, count in self.core_course_count().items():
                report.append(fmt.format(count, '({}) '.format(course) + courses.course_title(course)))

            report.append('\n\n')

        if include_qa:
            # QA Forums
            report.append("QA Forum Signups\n{}\n".format('=' * 15))
            report.append('Count: {}\n'.format(sum(self.live_qa_count().values())))

            report.append(fmt.format('Students', 'Course'))
            report.append(line_fmt.format('-'))
            for course, count in self.live_qa_count().items():
                report.append(fmt.format(count, '({}) '.format(course) + courses.course_title(course[:3])))

        for line in report:
            print(line)


class Registrant():
    course_regex = re.compile('(?:\[)(\w{3})(?:\])')
    qa_regex = re.compile('(?:\[)(\w{3}(?:L|R)\d?)(?:\])')

    # qarec_regex = re.compile('(?:\[)(\w{3}R)(?:\])')

    def __init__(self, raw_data):
        self._raw = raw_data
        self.customer_id = self._raw.get('orderCustomerId', '')
        self.registrationId = self._raw.get('orderId', '')
        self.orderNumber = self._raw.get('orderNumber', '')
        self.dateCreated = datetime.datetime.strptime(self._raw.get('dateCreated'), DATE_FMT)
        self.total = float(self._raw.get('total', 0))

    @property
    def oimr_id(self):
        """
        Create a hash of the registrant's full name,
        date of birth, and email to serve as a unique ID
        """
        string_to_hash = self.full_name.lower()
        string_to_hash += self.get_path('dateOfBirth').get('value')
        string_to_hash += self.email_addr.lower()

        hashed_string = hashlib.md5(string_to_hash.encode()).hexdigest()
        return hashed_string

    @property
    def full_name(self):
        fname = self.get_path('name.first').get('value')
        lname = self.get_path('name.last').get('value')
        return ' '.join((fname, lname))

    @property
    def email_addr(self):
        email = self.get_path('email').get('value')
        return email

    @property
    def dob(self):
        dob = self.get_path('dateOfBirth').get('value')
        dob_fields = [int(x) for x in dob.split('-')]
        dob = datetime.date(*dob_fields)
        return dob

    @property
    def age(self):
        age = datetime.date.today() - self.dob
        return age.days // 365

    @property
    def true_fields(self):
        return [f for f in self._raw['fieldData'] if f.get('value', '').lower() == 'true']

    @property
    def fields(self):
        # Convert fields to dict for easier use
        result = {}
        for f in self._raw['fieldData']:
            result[f.get('path', f.get('label'))] = f

        return result

    def get_path(self, path):
        # Search for path
        found = [f for f in self._raw['fieldData'] if f.get('path') == path]
        if not len(found):
            return None
        elif len(found) == 1:
            return found[0]
        else:
            return found

    @property
    def core_courses(self):
        courses = [self.course_regex.search(f.get('label', '')) for f in self.true_fields]
        courses = [m.group(1) for m in courses if m] or None
        return courses

    @property
    def extras(self):
        return bool(self.get_path('extras.session1'))

    @property
    def qa_forums(self):
        return self._qa_forums()

    @property
    def donation(self):
        donation = self.get_path('considerGivingDonationThanks.amount')
        if donation:
            return float(donation['value'])
        else:
            return False

    @property
    def status(self):
        return self._raw.get('status', '')

    @property
    def pretty(self):
        return json.dumps(self._raw, indent=2, ensure_ascii=False)

    def pprint(self):
        print(self.pretty)

    def _qa_forums(self, type_filter=False):
        fora = [self.qa_regex.search(f.get('label', '')) for f in self.true_fields]
        fora = [m.group(1) for m in fora if m] or None
        if type_filter and fora:
            fora = [x for x in fora if x[3].lower() == type_filter.lower()]
        return fora

    def __repr__(self):
        return '<Registrant {0} ({1})>'.format(self.registrationId, self.full_name)

    def __str__(self):
        return 'Registrant: {0}'.format(self.full_name)


class RegFoxAPI():
    def __init__(self, inputFile=None, apiKey=None, formId=None):
        """ If an inputFile is passed, use that,
            otherwise, look for explicit values """
        if inputFile:
            with open(inputFile, 'r') as infile:
                apiInfo = json.load(infile)
                # print(apiInfo)
                self.apiKey = apiInfo['apiKey']
                self.formId = apiInfo['formId']
        else:
            self.apiKey, self.formId = apiKey, formId

        self.product = 'regfox.com'
        self.base_url = 'https://api.webconnex.com/v2/public'

    @property
    def params(self):
        # Make the params for our web calls
        # This is a property so that it's re-initialized each use
        params = {
            'product': self.product,
            'formId': self.formId
        }

        return params

    @property
    def header(self):
        # Make the header for our web calls
        headers = {
            'apiKey': self.apiKey
        }

        return headers

    def test_connection(self):
        # Just do a fast connection check
        uri = self.base_url + '/ping'
        r = requests.get(uri, headers=self.header)
        return r.status_code == requests.codes.ok

    def get_registrants(self, **kwargs):
        """ Fetch a list of all registrants """

        uri = self.base_url + '/search/registrants'

        params = self.params.copy()
        if kwargs:
            params.update(kwargs)

        registrants = []

        r = requests.get(uri, headers=self.header, params=params)
        if r.status_code != requests.codes.ok:
            r.raise_for_status()

        # Check to see if we have more to get
        while r.json().get('hasMore'):
            # print('getting more...{} of {}'.format(len(r.json()['data']), r.json()['totalResults']))
            registrants.extend(r.json()['data'])
            lastObj = r.json()['startingAfter']
            params.update({'startingAfter': lastObj})
            r = requests.get(uri, headers=self.header, params=params)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()

        registrants.extend(r.json()['data'])

        return registrants


def makeRegistrationList(secretFile, **kwargs):
    try:
        oimrDb.make_log_info_entry('INFO', 'registration-mysql', 'makeRegistration', 'Starting RegfoxApi', 377)
    except Exception:
        # make log exception calls sys.exc_info() so all the error capture is done in pythonAnywhereConnect
        oimrDb.make_log_exception_entry()

    api = RegFoxAPI(secretFile)
    registrants = RegistrantList(api.get_registrants(**kwargs))
    return api, registrants


if __name__ == '__main__':
    api, registrants = makeRegistrationList('regfox_secret.json')
    print('done')
    # registrants.print_report()
