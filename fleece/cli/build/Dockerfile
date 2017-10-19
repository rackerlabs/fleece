FROM amazonlinux

ARG python_version=python27
ARG deps

RUN yum -y update && yum install -y ${python_version}-pip zip ${deps}

ENV python_version $python_version

COPY docker_build_lambda.sh /
CMD /docker_build_lambda.sh
