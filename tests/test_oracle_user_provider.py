import sys
import uuid
import cx_Oracle
import boto3
import logging
from oracle_user_provider import handler

logging.basicConfig(level=logging.INFO)


def escaped_string(str):
    return '"{}"'.format(str.replace('\\', '\\\\').replace('"', '\\"'))


class Request(dict):

    def __init__(self, request_type, user, physical_resource_id=None):
        self.update({
            'RequestType': request_type,
            'ResponseURL': 'https://httpbin.org/put',
            'StackId': 'arn:aws:cloudformation:us-west-2:EXAMPLE/stack-name/guid',
            'RequestId': 'request-%s' % str(uuid.uuid4()),
            'ResourceType': 'Custom::OracleUser',
            'LogicalResourceId': 'Whatever',
            'ResourceProperties': {
                'User': user, 'Password': 'password',
                'Database': {'User': 'system', 'Password': 'oracle', 'Host': 'localhost',
                              'Port': 1521, 'DBName': 'XE'}
            }})
        if physical_resource_id is not None:
            self['PhysicalResourceId'] = physical_resource_id

    def test_owner_connection(self, password=None):
        p = self['ResourceProperties']
        if password is None:
            password = p['Database']['Password']
        db = p['Database']
        return cx_Oracle.connect('{}/{}@{}:{}/{}'.format(
            escaped_string(db['User']), escaped_string(password), db['Host'], db['Port'], db['DBName']))

    def test_user_connection(self, password=None):
        p = self['ResourceProperties']
        db = p['Database']
        if password is None:
            password = p['Password']
        return cx_Oracle.connect('{}/{}@{}:{}/{}'.format(
            escaped_string(p['User']), escaped_string(password), db['Host'], db['Port'], db['DBName']))


def test_invalid_user_name():
    request = Request('Create', 'a-user')
    response = handler(request, {})
    assert response['Status'] == 'FAILED', response['Reason']


def expected_physical_id(request):
    p = request['ResourceProperties']
    db = p['Database']
    return 'oracle:{}@{}:{}/{}'.format(p['User'], db['Host'], db['Port'], db['DBName'])


def new_user_name():
    return 'u%s' % str(uuid.uuid4()).replace('-', '')[:29]


def test_create_user():
    # create a test user
    name = new_user_name()
    request = Request('Create', name)
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']
    assert 'PhysicalResourceId' in response
    physical_resource_id = response['PhysicalResourceId']
    assert physical_resource_id == expected_physical_id(request)

    c = request.test_user_connection()
    c.close()

    # duplicate user create fails
    request = Request('Create', name)
    response = handler(request, {})
    assert response['Status'] == 'FAILED', '%s' % response['Reason']
    assert response['Reason'] == 'user already exists and Adopt == False'

    # adopt user, change password
    request = Request('Create', name)
    request['ResourceProperties']['Adopt'] = True
    request['ResourceProperties']['Password'] = 'newpassword'
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', '%s' % response['Reason']
    c = request.test_user_connection()
    c.close()

    # revoke connect privileged the created user
    request = Request('Delete', name, physical_resource_id)
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']

    try:
        c = request.test_user_connection()
        c.close()
        assert False, 'succesfully logged in to delete user'
    except:
        pass

    # drop the user
    request = Request('Delete', name, physical_resource_id)
    request['ResourceProperties']['DeletionPolicy'] = 'Drop'
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']

    # delete non existing user
    request = Request('Delete', name + "-")
    request['PhysicalResourceId'] = expected_physical_id(request)
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']


def test_update_password():
    # create user
    name = new_user_name()
    request = Request('Create', name)
    request['DeletionPolicy'] = 'Drop'
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', '%s' % response['Reason']
    assert 'PhysicalResourceId' in response
    physical_resource_id = response['PhysicalResourceId']
    expect_id = 'postgresql:localhost:5432:postgres:%(name)s:%(name)s' % {'name': name}
    assert physical_resource_id == expected_physical_id(request)

    # update the password
    request = Request('Update', name, physical_resource_id)
    request['Password'] = 'geheim'
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']

    c = request.test_user_connection()
    c.close()

    # update the user is not possible
    request = Request('Update', name + '-', physical_resource_id)
    response = handler(request, {})
    assert response['Status'] == 'FAILED', response['Reason']

    # delete the created user
    request['User'] = name
    request['ResourceProperties']['DeletionPolicy'] = 'Drop'
    request['RequestType'] = 'Delete'
    request['PhysicalResourceId'] = physical_resource_id
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']


def test_create_user_resource_role():
    # create a test user
    name = new_user_name()
    request = Request('Create', name)
    request['ResourceProperties']['ResourceRole'] = True
    response = handler(request, {})
    assert response['Status'] == 'SUCCESS', response['Reason']
    assert 'PhysicalResourceId' in response
    physical_resource_id = response['PhysicalResourceId']
    assert physical_resource_id == expected_physical_id(request)

    c = request.test_user_connection()
    cursor = c.cursor()
    cursor.execute('CREATE TABLE X(X VARCHAR2(10))')
    cursor.execute('DROP TABLE X')
    cursor.close()
    c.close()

    # duplicate user create fails
def test_password_parameter_use():
    ssm = boto3.client('ssm')
    name = new_user_name()
    user_password_name = '/test-{}'.format(name)
    dbowner_password_name = '/test-owner-{}'.format(name)

    try:
        request = Request('Create', name)

        user_password = str(uuid.uuid4())[:30]
        del request['ResourceProperties']['Password']
        request['ResourceProperties']['PasswordParameterName'] = user_password_name
        dbowner_password = request['ResourceProperties']['Database']['Password']
        del request['ResourceProperties']['Database']['Password']
        request['ResourceProperties']['Database']['PasswordParameterName'] = dbowner_password_name

        ssm.put_parameter(Name=user_password_name, Value=user_password, Type='SecureString', Overwrite=True)
        ssm.put_parameter(Name=dbowner_password_name, Value=dbowner_password, Type='SecureString', Overwrite=True)
        response = handler(request, {})
        assert response['Status'] == 'SUCCESS', response['Reason']

        c = request.test_user_connection(user_password)
        c.close()

        request = Request('Delete', name, physical_resource_id=response['PhysicalResourceId'])
        request['ResourceProperties']['DeletionPolicy'] = 'Drop'
        response = handler(request, {})
        assert response['Status'] == 'SUCCESS', response['Reason']

    except Exception as e:
        sys.stderr.write('%s\n' % e)
        raise
    finally:
        try:
            ssm.delete_parameter(Name=user_password_name)
        except ssm.exceptions.ParameterNotFound as e:
            pass
        try:
            ssm.delete_parameter(Name=dbowner_password_name)
        except ssm.exceptions.ParameterNotFound as e:
            pass
