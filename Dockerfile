FROM docker.io/library/fedora 

RUN dnf install python3-solv libsolv-tools -y && dnf clean all
