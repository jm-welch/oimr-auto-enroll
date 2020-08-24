import requests
import re
import json
import datetime
from collections import UserList, Counter

DATE_FMT = "%Y-%m-%dT%H:%M:%SZ"

def makeRegistrationList(secretFile):
    api = RegFoxAPI(secretFile)
    registrants = RegistrantList(api.get_registrants())
    return api, registrants

class RegistrantList(UserList):
    def __init__(self, data=[]):
        # Store as raw input
        self._data = data
        # Remove invalid entries
        self.data = [Registrant(d) for d in self.validate(data)]

    @property
    def _raw(self):
        return [Registrant(d) for d in self._data]

    def validate(self, data):
        return [d for d in data if d.get('status')=='completed']

    def core_course_count(self):
        course_count = Counter({c: 0 for c in COURSES})
        for r in self.data:
            if r.core_courses:
                course_count.update(r.core_courses)
        return course_count

    def live_qa_count(self):
        qa_count = Counter()
        for code, data in COURSES.items():
            qa_count.update({qa: 0 for qa in data['liveQA']})
        for r in self.data:
            if r.qa_forums:
                qa_count.update(r.qa_forums)

        return qa_count

    def regs_by_course(self, course):
        return [r.emailAddr for r in self.data if course in r.core_courses]

    def date_list(self):
        result = [r.dateCreated.replace(minute=0, second=0) for r in self.data]
        return result

    def print_report(self):
        fmt = '{:^8} | {}'
        line_fmt = '{0:-^8} | {0:-^68}'

        report = []
        report.append('Report time: {}'.format(datetime.datetime.now().isoformat()))
        report.append('\nTotal registrants: {}'.format(len(self.data)))
        report.append('Age range: {}-{}'.format(min(r.age for r in self.data), max(r.age for r in self.data)))
        report.append('Total Donations: {}\n'.format(sum(r.donation for r in self.data)))

        # Core Courses
        report.append('Core Course Registration\n{}\n'.format('='*24))
        report.append('Count: {}\n'.format(sum(self.core_course_count().values())))

        report.append(fmt.format('Students', 'Course'))
        report.append(line_fmt.format('-'))
        for course, count in self.core_course_count().items():
            report.append(fmt.format(count, '({}) '.format(course) + course_title(course)))

        report.append('\n\n')

        # QA Forums
        report.append("QA Forum Signups\n{}\n".format('='*15))
        report.append('Count: {}\n'.format(sum(self.live_qa_count().values())))

        report.append(fmt.format('Students', 'Course'))
        report.append(line_fmt.format('-'))
        for course, count in self.live_qa_count().items():
            report.append(fmt.format(count, '({}) '.format(course) + course_title(course[:3])))

        for line in report:
            print(line)


class Registrant():
    course_regex = re.compile('(?:\[)(\w{3})(?:\])')
    qa_regex = re.compile('(?:\[)(\w{3}(?:L|R)\d?)(?:\])')
    #qarec_regex = re.compile('(?:\[)(\w{3}R)(?:\])')

    def __init__(self, raw_data):
        self._raw = raw_data
        self.customer_id = self._raw.get('orderCustomerId', '')
        self.registrationId = self._raw.get('orderId', '')
        self.orderNumber = self._raw.get('orderNumber', '')
        self.dateCreated = datetime.datetime.strptime(self._raw.get('dateCreated'), DATE_FMT)

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
    def age(self):
      dob = self.get_path('dateOfBirth').get('value')
      dob_fields = [int(x) for x in dob.split('-')]
      dob = datetime.date(*dob_fields)
      age = datetime.date.today() - dob
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
        return bool(get_path('extras.session1'))

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
        return json.dumps(self._raw, indent=2, force_ascii=False)

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
                #print(apiInfo)
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
            #print('getting more...{} of {}'.format(len(r.json()['data']), r.json()['totalResults']))
            registrants.extend(r.json()['data'])
            lastObj = r.json()['startingAfter']
            params.update({'startingAfter': lastObj})
            r = requests.get(uri, headers=self.header, params=params)
            if r.status_code != requests.codes.ok:
                r.raise_for_status()

        registrants.extend(r.json()['data'])

        return registrants


def course_title(code):
    return '{name} with {instructor}'.format(**COURSES[code])

# List of all courses
COURSES = {
  "BOF": {
    "instructor": "Cara Wildman",
    "name": "Bodhrán (Fundamentals)",
    "liveQA": {
      "BOFL1": None
    }
  },
  "BOI": {
    "instructor": "Paddy League",
    "name": "Bodhrán (Intermediate & Advanced)",
    "liveQA": {
      "BOIL1": None
    }
  },
  "BZK": {
    "instructor": "Eoin O’Neill",
    "name": "Bouzouki (All Levels)",
    "liveQA": {
      "BZKL1": None
    }
  },
  "BOX": {
    "instructor": "Colm Gannon",
    "name": "Button Accordion (All Levels)",
    "liveQA": {
      "BOXL1": None
    }
  },
  "COF": {
    "instructor": "Kelly Gannon",
    "name": "Concertina (Fundamentals)",
    "liveQA": {
      "COFL1": None
    }
  },
  "COI": {
    "instructor": "Cormac Begley",
    "name": "Concertina (Intermediate & Advanced)",
    "liveQA": {
      "COIL1": None
    }
  },
  "DAN": {
    "instructor": "Jaclyn O'Riley",
    "name": "Dancing (Sean-nós)",
    "liveQA": {
      "DANL1": None
    }
  },
  "FIF": {
    "instructor": "Chris Buckley",
    "name": "Fiddle (Fundamentals)",
    "liveQA": {
      "FIFL1": None
    }
  },
  "FIL": {
    "instructor": "Liz Doherty",
    "name": "Fiddle (Intermediate)",
    "liveQA": {
      "FILL1": None
    }
  },
  "FIE": {
    "instructor": "Eimear Arkins",
    "name": "Fiddle (Intermediate)",
    "liveQA": {
      "FIEL1": None
    }
  },
  "FIM": {
    "instructor": "Manus McGuire",
    "name": "Fiddle (Intermediate)",
    "liveQA": {
      "FIML1": None
    }
  },
  "FIA": {
    "instructor": "Zoë Connway",
    "name": "Fiddle (Advanced)",
    "liveQA": {
      "FIAL1": None
    }
  },
  "FLI": {
    "instructor": "Harry Bradley",
    "name": "Flute (Intermediate & Advanced)",
    "liveQA": {
      "FLIL1": None
    }
  },
  "GUF": {
    "instructor": "Jeff Moore",
    "name": "Guitar (Fundamentals)",
    "liveQA": {
      "GUFL1": None
    }
  },
  "GUI": {
    "instructor": "Jim Murray",
    "name": "Guitar (Intermediate & Advanced)",
    "liveQA": {
      "GUIL1": None
    }
  },
  "HRP": {
    "instructor": "Eileen Gannon",
    "name": "Harp (All Levels)",
    "liveQA": {
      "HRPL1": None
    }
  },
  "MBF": {
    "instructor": "John Morrow",
    "name": "Mandolin/Banjo (Fundamentals)",
    "liveQA": {
      "MBFL1": None
    }
  },
  "MAI": {
    "instructor": "Brian McGillicuddy",
    "name": "Mandolin (Intermediate & Advanced)",
    "liveQA": {
      "MAIL1": None
    }
  },
  "PIA": {
    "instructor": "Mirella Murray",
    "name": "Piano Accordion (All Levels)",
    "liveQA": {
      "PIAL1": None
    }
  },
  "SNG": {
    "instructor": "Liz Hanley",
    "name": "Singing (All Levels)",
    "liveQA": {
      "SNGL1": None
    }
  },
  "TBI": {
    "instructor": "Gerry O’Connor",
    "name": "Tenor Banjo (Intermediate & Advanced)",
    "liveQA": {
      "TBIL1": None
    }
  },
  "UIL": {
    "instructor": "Joey Abarta",
    "name": "Uilleann Pipes",
    "liveQA": {
      "UILL1": None
    }
  },
  "WHI": {
    "instructor": "Joanie Madden",
    "name": "Whistle (Intermediate & Advanced)",
    "liveQA": {
      "WHIL1": None
    }
  },
  "WFF": {
    "instructor": "L.E. McCullough",
    "name": "Whistle/Flute (Fundamentals)",
    "liveQA": {
      "WFFL1": None
    }
  }
}