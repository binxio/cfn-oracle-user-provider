# Custom::OracleUser
The `Custom::OracleUser` resource creates an oracle database user without any permissions


## Syntax
To declare this entity in your AWS CloudFormation template, use the following syntax:

```yaml
Type: Custom::OracleUser
Properties:
  Name: String
  Adopt: Boolean
  Password: String
  PasswordParameterName: String
  DeletionPolicy: Retain/Drop
  Database:
    Host: STRING
    Port: INTEGER
    User: STRING
    DBName: STRING
    Password: STRING
    PasswordParameterName: STRING
  ServiceToken: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:binxio-cfn-oracle-user-provider-vpc-${AppVPC}'
```

## Properties
You can specify the following properties:

- `Name` - of the user to create
- `Adopt` - an existing user, default False.
- `Password` - of the user 
- `PasswordParameterName` - name of the parameter in the store containing the password of the user.
- `DeletionPolicy` - when the resource is deleted, default is `Retain`.
- `Database` - connection information of the database owner
-- `Host` - the database server is listening on.
-- `Port` - port the database server is listening on.
-- `DBName` - name to connect to.
-- `User` - name of the database owner.
-- `Password` - to identify the user with. 
-- `PasswordParameterName` - name of the parameter in the store containing the password of the user

Either `Password` or `PasswordParameterName` is required.

## Return values
There are no return values from this resources.

