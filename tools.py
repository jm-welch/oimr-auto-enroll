import oimrtools as tools
from importlib import reload

fn = 'full_name'
ea = 'email_addr'

tc = 'commons1'
th = 'tradhall1'

def search_student(search_term):

    result = []

    result.extend([r for r in tools.registrants if search_term.lower() in r.full_name.lower()])
    result.extend([r for r in tools.registrants if search_term.lower() in r.email_addr.lower()])

    result = list(set(result))
    
    if len(result) == 1:
        result = result[0]
    elif len(result) > 1:
        result = result
    else:
        result = False

    return result