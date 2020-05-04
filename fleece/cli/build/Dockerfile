FROM amazonlinux:1

ARG python_version=python36
ARG deps

RUN echo 'exclude=filesystem' >> /etc/yum.conf
RUN yum -y update && yum install -y ${python_version}-pip zip ${deps}

ENV python_version $python_version

COPY docker_build_lambda.sh /
CMD /docker_build_lambda.sh
