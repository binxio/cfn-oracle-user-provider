import boto3
import logging
import cx_Oracle
from botocore.exceptions import ClientError
from cfn_resource_provider import ResourceProvider

log = logging.getLogger()

request_schema = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "oneOf": [
        {"required": ["Database", "User", "Password"]},
        {"required": ["Database", "User", "PasswordParameterName"]}
    ],
    "properties": {
        "Database": {"$ref": "#/definitions/connection"},
        "User": {
            "type": "string",
            "pattern": "^[_A-Za-z][A-Za-z0-9_$]*$",
            "description": "the user to create"
        },
        "Password": {
            "type": "string",
            "description": "the password for the user"
        },
        "PasswordParameterName": {
            "type": "string",
            "minLength": 1,
            "description": "the name of the password in the Parameter Store."
        },
        "Adopt": {
            "type": "boolean",
            "default": False,
            "description": "if true, will adopt an existing user on create"
        },
        "DeletionPolicy": {
            "type": "string",
            "default": "Retain",
            "enum": ["Drop", "Retain"]
        }
    },
    "definitions": {
        "connection": {
            "type": "object",
            "oneOf": [
                {"required": ["DBName", "Host", "Port", "User", "Password"]},
                {"required": ["DBName", "Host", "Port", "User", "PasswordParameterName"]}
            ],
            "properties": {
                "DBName": {
                    "type": "string",
                    "description": "the name of the database"
                },
                "Host": {
                    "type": "string",
                    "description": "the host of the database"
                },
                "Port": {
                    "type": "integer",
                    "default": 5432,
                    "description": "the network port of the database"
                },
                "User": {
                    "type": "string",
                    "description": "the username of the database owner"
                },
                "Password": {
                    "type": "string",
                    "description": "the password of the database owner"
                },
                "PasswordParameterName": {
                    "type": "string",
                    "description": "the name of the database owner password in the Parameter Store."
                }
            }
        }
    }
}

def escaped_string(str):
    return '"{}"'.format(str.replace('\\', '\\\\').replace('"', '\\"'))


class OracleUser(ResourceProvider):

    def __init__(self):
        super(OracleUser, self).__init__()
        self.ssm = boto3.client('ssm')
        self.connection = None
        self.request_schema = request_schema

    def convert_property_types(self):
        self.heuristic_convert_property_types(self.properties)

    def get_password(self, name):
        try:
            response = self.ssm.get_parameter(Name=name, WithDecryption=True)
            return response['Parameter']['Value']
        except ClientError as e:
            raise ValueError('Could not obtain password using name {}, {}'.format(name, e.message))

    @property
    def user_password(self):
        if 'Password' in self.properties:
            return self.get('Password')
        else:
            return self.get_password(self.get('PasswordParameterName'))


    @property
    def dbowner_password(self):
        db = self.get('Database')
        if 'Password' in db:
            return db.get('Password')
        else:
            return self.get_password(db['PasswordParameterName'])

    @property
    def user(self):
        return self.get('User')

    @property
    def adopt_user(self):
        return self.get('Adopt')

    @property
    def host(self):
        return self.get('Database', {}).get('Host', None)

    @property
    def port(self):
        return self.get('Database', {}).get('Port', 5432)

    @property
    def dbname(self):
        return self.get('Database', {}).get('DBName', None)

    @property
    def dbowner(self):
        return self.get('Database', {}).get('User', None)

    @property
    def deletion_policy(self):
        return self.get('DeletionPolicy')


    def connect(self):
        self.connection = None
        log.info('connecting to database %s on port %d as user %s', self.host, self.port, self.dbowner)
        try:
            self.connection = cx_Oracle.connect(self.dbowner,
                                                self.dbowner_password, '{o.host}:{o.port}/{o.dbname}'.format(o=self))
        except Exception as e:
            raise ValueError('Failed to connect, {}'.format(e))

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.connection = None


    def user_exists(self):
        cursor = self.connection.cursor()
        try:
            cursor.execute('SELECT username FROM dba_users WHERE username = :username', username=self.user)
            rows = cursor.fetchall()
            return len(rows) > 0
        finally:
            cursor.close()

    def drop_user(self):
        cursor = self.connection.cursor()
        try:
            if self.deletion_policy == 'Drop':
                log.info('drop user %s', self.user)
                cursor.execute('DROP USER {}'.format(escaped_string(self.user)))
            else:
                log.info('lockout user %s', self.user)
                cursor.execute('ALTER USER {} ACCOUNT LOCK'.format(escaped_string(self.user)))
        finally:
            cursor.close()

    def update_password(self):
        log.info('update password of %s', self.user)
        cursor = self.connection.cursor()
        try:
            cursor.execute("ALTER USER {} IDENTIFIED BY {} ACCOUNT UNLOCK".format(escaped_string(self.user), escaped_string(self.user_password)))
        finally:
            cursor.close()

    def create_user(self):
        log.info('create user %s ', self.user)
        cursor = self.connection.cursor()
        try:
            cursor.execute("CREATE USER {} IDENTIFIED BY {}".format(escaped_string(self.user), escaped_string(self.user_password)))
            cursor.execute("GRANT CONNECT TO {}".format(escaped_string(self.user)))
        finally:
            cursor.close()

    def create(self):
        try:
            self.connect()
            if not self.user_exists():
                self.create_user()
            else:
                if self.adopt_user:
                    self.update_password()
                else:
                    self.fail('user already exists and Adopt == False')
            self.physical_resource_id = self.url
        except Exception as e:
            self.physical_resource_id = 'could-not-create'
            self.fail('Failed to create user, %s' % e.message)
        finally:
            self.close()

    @property
    def url(self):
        return 'oracle:{o.user}@{o.host}:{o.port}/{o.dbname}'.format(o=self)

    @property
    def update_allowed(self):
        return self.url == self.physical_resource_id

    def update(self):
        try:
            self.connect()
            if self.update_allowed:
                self.update_password()
            else:
                self.fail('Only the password of %s can be updated' % self.user)
        except Exception as e:
            self.fail('Failed to update the user, {}'.format(e))
        finally:
            self.close()

    def delete(self):
        if self.physical_resource_id == 'could-not-create':
            self.success('user was never created')
            return

        try:
            self.connect()
            self.drop_user()
        except Exception as e:
            return self.fail('{}'.format(e))
        finally:
            self.close()


provider = OracleUser()


def handler(request, context):
    return provider.handle(request, context)
