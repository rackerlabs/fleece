FROM amazonlinux:2

ARG python_version=python36
ARG deps

RUN echo 'exclude=filesystem' >> /etc/yum.conf
RUN if [ "${python_version}" == "python310" ]; then \
     yum groupinstall "Development Tools" -y; \
     yum erase openssl-devel -y; \
     yum install openssl11 openssl11-devel bzip2-devel wget zip ${deps} -y; \
     wget https://www.python.org/ftp/python/3.10.14/Python-3.10.14.tgz; \
     tar -xf Python-3.10.14.tgz; \
     cd Python-3.10.14/; \
     ./configure --enable-optimizations; \
     make altinstall; \
     python3.10 --version; \
     ln -s /usr/local/bin/python3.10 /usr/local/bin/python3; \
    else yum -y update && yum install -y ${python_version} zip ${deps}; \
    fi

RUN if [[ "${python_version}" == "python36" ]]; then \
     curl -sOL https://bootstrap.pypa.io/pip/3.6/get-pip.py; \
    else curl -sOL https://bootstrap.pypa.io/get-pip.py -o get-pip.py; \
    fi
RUN python3 get-pip.py --prefix=/usr/local/

ENV python_version $python_version

COPY docker_build_lambda.sh /
CMD /docker_build_lambda.sh
