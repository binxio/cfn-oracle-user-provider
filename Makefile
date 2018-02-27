include Makefile.mk

NAME=cfn-oracle-user-provider

ORACLE_INSTANT_CLIENT_HOME=/usr/local/lib/instantclient_12_2/

AWS_REGION=eu-central-1
ALL_REGIONS=$(shell printf "import boto3\nprint '\\\n'.join(map(lambda r: r['RegionName'], boto3.client('ec2').describe_regions()['Regions']))\n" | python | grep -v '^$(AWS_REGION)$$')
S3_BUCKET=binxio-public-$(AWS_REGION)

help:
	@echo 'make                 - builds a zip file to target/.'
	@echo 'make release         - builds a zip file and deploys it to s3.'
	@echo 'make clean           - the workspace.'
	@echo 'make test            - execute the tests, requires a working AWS connection.'
	@echo 'make deploy-provider - deploys the provider.'
	@echo 'make delete-provider - deletes the provider.'
	@echo 'make demo            - deploys the provider and the demo cloudformation stack.'
	@echo 'make delete-demo     - deletes the demo cloudformation stack.'

deploy:
	aws s3 --region $(AWS_REGION) \
		cp target/$(NAME)-$(VERSION).zip \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-$(VERSION).zip 
	aws s3 --region $(AWS_REGION) \
		cp \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-$(VERSION).zip \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-latest.zip 

deploy-all-regions:
	@for REGION in $(ALL_REGIONS); do \
		echo "copying to region $$REGION.." ; \
		aws s3 --region $(AWS_REGION) \
			cp  \
			s3://binxio-public-$(AWS_REGION)/lambdas/$(NAME)-$(VERSION).zip \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-$(VERSION).zip; \
		aws s3 --region $$REGION \
			cp  \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-$(VERSION).zip \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-latest.zip; \
		aws s3api --region $$REGION \
			put-object-acl --bucket binxio-public-$$REGION \
			--acl public-read --key lambdas/$(NAME)-$(VERSION).zip; \
		aws s3api --region $$REGION \
			put-object-acl --bucket binxio-public-$$REGION \
			--acl public-read --key lambdas/$(NAME)-latest.zip; \
	done

do-push: deploy

do-build: local-build

local-build: src/*.py venv requirements.txt $(ORACLE_INSTANCE_CLIENT_ZIP)
	mkdir -p target/content 
	cp requirements.txt target/content
	docker run -v $(PWD)/target/content:/venv --workdir /venv python:2.7 pip install --quiet -t . -r requirements.txt
	docker run -v $(PWD)/target/content:/venv --workdir /venv python:2.7 python -m compileall -q -f .
	for zip in zips/*.zip ; do bsdtar --strip-components=1 -C target/content -xvf $$zip; done ; rm target/content/ojdbc8.jar target/content/xstreams.jar
	docker run -v $(PWD)/target/content:/venv python:2.7 /bin/bash -c 'apt-get update; apt-get install -y libaio-dev ; cp /lib/x86_64-linux-gnu/libaio.so.1.0.1 /venv'
	(cd target/content ; ln -sf libaio.so.1.0.1 libaio.so.1)
	cp -r src/* target/content
	find target/content -type d | xargs  chmod ugo+rx
	find target/content -type f | xargs  chmod ugo+r 
	cd target/content && zip --quiet -9r ../../target/$(NAME)-$(VERSION).zip  *
	chmod ugo+r target/$(NAME)-$(VERSION).zip

venv: requirements.txt
	virtualenv -p python2 venv  && \
	. ./venv/bin/activate && \
	pip install --quiet --upgrade pip && \
	pip install --quiet -r requirements.txt 
	
clean:
	rm -rf venv target
	rm -rf src/*.pyc tests/*.pyc

test: venv
	for i in $$PWD/cloudformation/*; do \
		aws cloudformation validate-template --template-body file://$$i > /dev/null || exit 1; \
	done
	. ./venv/bin/activate && \
	pip install --quiet -r requirements.txt -r test-requirements.txt && \
	cd src && \
        LD_LIBRARY_PATH=$(ORACLE_INSTANT_CLIENT_HOME) PYTHONPATH=$(PWD)/src pytest ../tests/test*.py

autopep:
	autopep8 --experimental --in-place --max-line-length 132 src/*.py tests/*.py

deploy-provider:
	@set -x ;if aws cloudformation get-template-summary --stack-name $(NAME) >/dev/null 2>&1 ; then \
		export CFN_COMMAND=update; \
	else \
		export CFN_COMMAND=create; \
	fi ;\
	export VPC_ID=$$(aws ec2  --output text --query 'Vpcs[?IsDefault].VpcId' describe-vpcs) ; \
        export SUBNET_IDS=$$(aws ec2 --output text --query 'RouteTables[?Routes[?GatewayId == null]].Associations[].SubnetId' \
                                describe-route-tables --filters Name=vpc-id,Values=$$VPC_ID | tr '\t' ','); \
	export SG_ID=$$(aws ec2 --output text --query "SecurityGroups[*].GroupId" \
				describe-security-groups --group-names default  --filters Name=vpc-id,Values=$$VPC_ID); \
	([[ -z $$VPC_ID ]] || [[ -z $$SUBNET_IDS ]] || [[ -z $$SG_ID ]]) && \
		echo "Either there is no default VPC in your account, less then two subnets or no default security group available in the default VPC" && exit 1 ; \
	echo "$$CFN_COMMAND provider in default VPC $$VPC_ID, subnets $$SUBNET_IDS using security group $$SG_ID." ; \
	aws cloudformation $$CFN_COMMAND-stack \
		--capabilities CAPABILITY_IAM \
		--stack-name $(NAME) \
		--template-body file://cloudformation/cfn-resource-provider.yaml  \
		--parameters ParameterKey=VPC,ParameterValue=$$VPC_ID \
			     ParameterKey=Subnets,ParameterValue=\"$$SUBNET_IDS\" \
			     ParameterKey=SecurityGroup,ParameterValue=$$SG_ID ;\
	aws cloudformation wait stack-$$CFN_COMMAND-complete --stack-name $(NAME) ;

delete-provider:
	aws cloudformation delete-stack --stack-name $(NAME)
	aws cloudformation wait stack-delete-complete  --stack-name $(NAME)

demo: 
	@if aws cloudformation get-template-summary --stack-name $(NAME)-demo >/dev/null 2>&1 ; then \
		export CFN_COMMAND=update; export CFN_TIMEOUT="" ;\
	else \
		export CFN_COMMAND=create; export CFN_TIMEOUT="--timeout-in-minutes 20"  ;\
	fi ;\
	export VPC_ID=$$(aws ec2  --output text --query 'Vpcs[?IsDefault].VpcId' describe-vpcs) ; \
        export SUBNET_IDS=$$(aws ec2 --output text --query 'RouteTables[?Routes[?GatewayId == null]].Associations[].SubnetId' \
                                describe-route-tables --filters Name=vpc-id,Values=$$VPC_ID | tr '\t' ','); \
        export SG_ID=$$(aws ec2 --output text --query "SecurityGroups[*].GroupId" \
                                describe-security-groups --group-names default  --filters Name=vpc-id,Values=$$VPC_ID); \
	echo "$$CFN_COMMAND demo in default VPC $$VPC_ID, subnets $$SUBNET_IDS using security group $$SG_ID." ; \
        ([[ -z $$VPC_ID ]] || [[ -z $$SUBNET_IDS ]] || [[ -z $$SG_ID ]]) && \
                echo "Either there is no default VPC in your account, no two subnets or no default security group available in the default VPC" && exit 1 ; \
	aws cloudformation $$CFN_COMMAND-stack --stack-name $(NAME)-demo \
		--template-body file://cloudformation/demo-stack.yaml  \
		$$CFN_TIMEOUT \
		--parameters 	ParameterKey=VPC,ParameterValue=$$VPC_ID \
				ParameterKey=Subnets,ParameterValue=\"$$SUBNET_IDS\" \
				ParameterKey=SecurityGroup,ParameterValue=$$SG_ID ;\
	aws cloudformation wait stack-$$CFN_COMMAND-complete --stack-name $(NAME)-demo ;

delete-demo:
	aws cloudformation delete-stack --stack-name $(NAME)-demo
	aws cloudformation wait stack-delete-complete  --stack-name $(NAME)-demo

