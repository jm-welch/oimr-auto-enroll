import json

# Build course title from course data
def course_title(code):
    course = COURSES[code]
    return f"""{course.get('name')}{f" with {course.get('instructor')}" if course.get('instructor') else ''}""".format(**COURSES[code])

def course_title_with_code(code):
    return '({}) '.format(code) + course_title(code)

def list_all_courses():
    return list(COURSES.keys())

def list_all_liveQA():
    return ['{}L1'.format(c) for c in COURSES.keys()]

def pprint():
    print(json.dumps(COURSES, indent=2, ensure_ascii=False))

def ta_course_list(ta):
    return [k for k, v in COURSES.items() if v.get('ta') == ta]

def ta_for_course(course):
    return COURSES.get(course, {}).get('ta')

# Import courses from json
with open('courses.json', 'r') as infile:
    COURSES = json.load(infile)