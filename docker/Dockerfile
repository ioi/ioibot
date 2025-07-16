ARG PYTHON_VERSION=3.12

ARG LIBOLM_VERSION=3.2.16

FROM python:${PYTHON_VERSION}-alpine

ARG LIBOLM_VERSION

COPY . /data

WORKDIR /data/

RUN apk add --no-cache \
    build-base \
    cmake \
    git \
    libffi-dev \
    libpq \
    postgresql-dev \
    yaml-dev \
    py3-setuptools \
    python3-dev \
    curl \
    bash \
    libstdc++ \
    openssl-dev

RUN pip install --no-warn-script-location "matrix-nio[e2e]" pandas

RUN pip install --no-warn-script-location ".[postgres]"

RUN mkdir /scripts

COPY docker/build_and_install_libolm.sh /scripts/

RUN chmod +x /scripts/build_and_install_libolm.sh

RUN /scripts/build_and_install_libolm.sh ${LIBOLM_VERSION}


VOLUME ["/data"]

ENTRYPOINT ["ioi-bot"]
