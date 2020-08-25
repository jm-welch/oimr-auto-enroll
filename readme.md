# O'Flaherty Retreat 2020 Registration/Enrollment Bridge

## Purpose
The intent of these scripts is to obtain registration data from RegFox, and allow automated enrollment into Google Classrooms in the G Suite domain.

## API References
* [WebConnex (RegFox) Registrants API](https://docs.webconnex.io/api/v2/#registrants)
* Google APIs:
    * [G Suite - Python QuickStart](https://developers.google.com/admin-sdk/directory/v1/quickstart/python)
    * [G Suite - Groups API](https://developers.google.com/admin-sdk/directory/v1/reference/groups)
    * [Classroom - Python QuickStart](https://developers.google.com/classroom/quickstart/python)
    * [Classroom - Teachers and Students](https://developers.google.com/classroom/guides/manage-users)
    * [Classroom - invitations.create](https://developers.google.com/classroom/reference/rest/v1/invitations/create)

## Getting Started
WIP - Section coming soon

* PythonAnywhere
* Local Setup
* pipenv
* Python versions

## Structure

### registration.py
This module contains the following classes, all pertaining to RegFox or registrant data

#### RegFoxAPI()
This is a wrapper for the RegFox API, as described in the links above. An `apiKey` is required to connect, and a `formId` is used to filter results based on the specific registration page for the retreat. It can be invoked in one of two ways:

``` python
# Secrets file
api = RegFoxAPI(inputFile='regfox_secret.json')

# Explicit values
api = RegFoxAPI(formId=12345, apiKey='nunya')
```

If using a secrets file, it should be JSON structured, like so:

``` json
{
    "apiKey": "nunya",
    "formId": 12345
}
```

The `RegFoxAPI()` object has a `get_registrants()` method, which will obtain a list of all registrants matching the `formId` used during initialization (multiple pages, if present). API parameters can be passed as arguments to the method. For example, this would return all registrants whose records were updated after the 4th of July 2020:

``` python
api = RegFoxAPI('regfox_secrets.json')
registrants = api.get_registrants(dateUpdatedAfter="2020-07-04")
```

#### Registrant()
The `Registrant()` class is used to serialize a single registrant's data as returned from the `RegFoxAPI.get_registrants()` call. Data within these objects should only pertain to a single registrant object returned by RegFox, and no manual merging should occur.

The raw JSON is stored as `Registrant._raw`, in case it's needed. A pretty output of registrant data can be obtained via the `pprint()` method

Many attributes are generated using the `@property` decorator, both to prevent accidental modification, and to allow us to handle RegFox's specific JSON schema, which requires iteration over a list of objects to obtain field values.

While some registrant metadata is stored at the top level of this schema, much of it is stored within the `fieldData` tree, which is a list of objects with varying structure. These fields can be accessed from `Registrant.fields`, a dict created by iterating over the `fieldData` tree and using the `path` value as the key. The `Registrant.get_path(path)` method can be used to fetch the object for a specific path (a string) from the `Registrant.fields` property.

#### RegistrantList()
This is an extension of a Python list to allow for batch processing on lists of `Registrant()` objects.

Of note, this contains a `print_report()` method, which will print out an overall summary of registration to-date, including counts for each core course and QA forum.