#!/bin/bash -e
readonly inject_build_info="${1}"

if [[ ! -f /build_cache/${DEPENDENCIES_SHA}.zip ]] || [[ "$REBUILD_DEPENDENCIES" == "1" ]]; then
    echo "rebuilding dependencies"
    rm -rf /build_cache/*
    mkdir /tmp/build
    /usr/bin/pip-${python_version:6:1}.${python_version:7:1} install -r /requirements/requirements.txt -t /tmp/build
    cd /tmp/build
    zip -X -r /build_cache/${DEPENDENCIES_SHA}.zip .
else
    echo "using cached dependencies; no rebuild"
fi
cd /src
rm -f /dist/lambda_function.zip
cp /build_cache/${DEPENDENCIES_SHA}.zip /dist/lambda_function.zip
if [[ "$EXCLUDE_PATTERNS" != "" ]]; then
    EXCLUDE="-x $EXCLUDE_PATTERNS"
fi
eval zip -X -r /dist/lambda_function.zip $EXCLUDE -- .

if [[ -n "${inject_build_info}" ]]; then
    cd /tmp
    echo "{\"VERSION_HASH\": \"${VERSION_HASH}\", \"BUILD_TIME\": \"${BUILD_TIME}\"}" > config.json
    zip -X -r /dist/lambda_function.zip config.json
fi
