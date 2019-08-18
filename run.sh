
# sudo chcon -Rv -t container_file_t './solv'
# podman build -t libsolv:git -f ./Dockerfile
podman run --rm \
    -v "$(pwd)/rpm_solv.py:/usr/sbin/rpm_solv.py" \
    -v "$(pwd)/solv/:/var/cache/solv/" \
    libsolv:git rpm_solv.py "$@"
