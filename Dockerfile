FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.10
WORKDIR ${LAMBDA_TASK_ROOT}

ENV ORACLE_HOME=/opt/oracle
ENV LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$ORACLE_HOME/lib

# install oracle client library dependencies
RUN yum update -y \
    && yum install -y libaio unzip \
    && yum clean all \
    && rm -rf /var/cache/yum

# install oracle client library
RUN curl -o instantclient.zip https://download.oracle.com/otn_software/linux/instantclient/213000/instantclient-basic-linux.x64-21.3.0.0.0.zip \
    && unzip instantclient.zip \
    && mkdir -p $ORACLE_HOME \
    && mv instantclient_21_3 $ORACLE_HOME/lib \
    && rm -f instantclient.zip

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./

RUN find . -type d -print0 | xargs -0 chmod ugo+rx && \
    find . -type f -print0 | xargs -0 chmod ugo+r

CMD ["oracle_user_provider.handler"]
