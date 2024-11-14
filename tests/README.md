# test
Before you can test this code install the [Oracle instant client libraries](http://www.oracle.com/technetwork/database/database-technologies/instant-client/overview/index.html) and
 start a local Oracle docker container.


```
docker run -d \
      -p 1521:1521 \
      --name oracle-se2 \
      -e ORACLE_PWD=p@ssw0rd \
      container-registry.oracle.com/database/free:latest-lite
```
