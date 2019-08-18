FROM docker.io/library/fedora 

RUN dnf install python3-solv.x86_64 -y && dnf clean all
