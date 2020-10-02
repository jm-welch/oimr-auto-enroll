import json

# Build course title from course data
def course_title(code):
    return '{name} with {instructor}'.format(**COURSES[code])

def course_title_with_code(code):
    return '({}) '.format(code) + course_title(code)

def list_all_courses():
    return list(COURSES.keys())

# Import courses from json
with open('courses.json', 'r') as infile:
    COURSES = json.load(infile)