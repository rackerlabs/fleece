FROM amazonlinux:1

ARG python_version=python36
ARG deps

RUN echo 'exclude=filesystem' >> /etc/yum.conf
RUN yum -y update && yum install -y ${python_version} zip ${deps}
RUN if [[ "${python_version}" == "python36" ]]; then curl -sOL https://bootstrap.pypa.io/pip/3.6/get-pip.py; else curl -sOL https://bootstrap.pypa.io/get-pip.py; fi
RUN python3 get-pip.py --prefix=/usr/local/

ENV python_version $python_version

COPY docker_build_lambda.sh /
CMD /docker_build_lambda.sh
