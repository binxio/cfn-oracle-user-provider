# cfn-oracle-user-provider

Although CloudFormation is very good in creating Oracle database servers with Amazon RDS,
the mundane task of creating Oracle users is not supported. 

This custom Oracle user provider automates the provisioning of Oracle users.


## How does it work?
It is quite easy: you specify a CloudFormation resource of the [Custom::OracleUser](docs/OracleUser.md), as follows:

```yaml
  OracleUser:
    Type: Custom::OracleUser
    DependsOn: UserPassword
    Properties:
      Name: scott
      Adopt: false
      PasswordParameterName: /oracle/scott/password
      DeletionPolicy: Retain 
      Database:                   # the server to create the new user or database in
        Host: oracle
        Port: 1521
        Database: XE
        User: oracle
        PasswordParameterName: /oracle/oracle/password                # put your root password is in the parameter store
      ServiceToken: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:binxio-cfn-oracle-user-provider-vpc-${AppVPC}'

   UserPassword:
    Type: Custom::Secret
    Properties:
      Name: /oracle/scott/password
      KeyAlias: alias/aws/ssm
      Alphabet: _&`'~-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789
      Length: 30
      ServiceToken: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:binxio-cfn-secret-provider'
```

After the deployment, the Oracle user 'scott' has been created and granted the CONNECT role. The password for the root database user has been obtained by querying the Parameter `/oracle/oracle/password`.  

The RetainPolicy by default is `Retain`. This means that the account is locked. If you specify drop, the user will be dropped.
If you specify `Adopt` as True, a create user will not fail if the user already exists. Instead, the password is changed for that user and the account is unlocked. 
This is to allow to deploy to databases with pre-populated users.


## Installation

The installation of the Oracle User provider is not as straight forward as the other ones, due to licensing restrictions.
To install this Custom Resource, you need to build and deploy it yourself.

`
### Create a private ECR repository

To store your lambda container image, create an ECR repository with the name `xebia/cfn-oracle-user-provider`


### Build and deploy the lambda docker image:
To build the lambda, type:

```
make snapshot

PROVIDER_IMAGE_URI=$(make snowimage)
```


### deploy the customer provider
```sh
export VPC_ID=$(aws ec2  --output text --query 'Vpcs[?IsDefault].VpcId' describe-vpcs)
export SUBNET_ID=$(aws ec2 --output text --query Subnets[0].SubnetId \
			describe-subnets --filters Name=vpc-id,Values=$VPC_ID)
export SG_ID=$(aws ec2 --output text --query "SecurityGroups[*].GroupId" \
			describe-security-groups --group-names default  --filters Name=vpc-id,Values=$VPC_ID)

aws cloudformation create-stack \
	--capabilities CAPABILITY_IAM \
	--stack-name cfn-oracle-user-provider \
	--template-body file://cloudformation/cfn-custom-resource-provider.yaml  \
	--parameters \
	    ParameterKey=VPC,ParameterValue=$VPC_ID \
	    ParameterKey=Subnet,ParameterValue=$SUBNET_ID \
	    ParameterKey=SecurityGroup,ParameterValue=$SG_ID \
	    ParameterKey=ProviderImageUri,ParameterValue=$PROVIDER_IMAGE_URI

aws cloudformation wait stack-create-complete  --stack-name cfn-oracle-user-provider 
```
Note that this uses the default VPC, subnet and security group. As the Lambda functions needs to connect to the database. You will need to 
install this custom resource provider for each vpc that you want to be able to create database users.


If you have not done so, please install the secret provider too.

```
cd ..
git clone https https://github.com/binxio/cfn-secret-provider.git 
cd cfn-secret-provider
aws cloudformation create-stack \
	--capabilities CAPABILITY_IAM \
	--stack-name cfn-secret-provider \
	--template-body file://cloudformation/cfn-custom-resource-provider.json 
aws cloudformation wait stack-create-complete  --stack-name cfn-secret-provider 

```


## Demo
To install the simple sample of the Custom Resource, type:

```sh
aws cloudformation create-stack --stack-name cfn-database-user-provider-demo \
	--template-body file://cloudformation/demo-stack.json
aws cloudformation wait stack-create-complete  --stack-name cfn-database-user-provider-demo
```
It will create an Oracle database too, so it is quite time consuming...

## Conclusion
With this solution Oracle users can be provisioned just like a database, while keeping the
passwords safely stored in the AWS Parameter Store.
