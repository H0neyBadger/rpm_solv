
# sudo chcon -Rv -t container_file_t './solv'
# podman build -t libsolv:git -f ./Dockerfile
podman run --rm -it \
    -v "$(pwd)/rpm_solv.py:/usr/sbin/rpm_solv.py" \
    -v "$(pwd)/utils/:/usr/sbin/utils/" \
    -v "$(pwd)/solv/:/var/cache/solv/" \
    -v "$(pwd)/repos:/var/cache/repos/" \
    libsolv:git python3 -m cProfile \
    -o /var/cache/solv/cProfile \
    -s 'cumulative' \
    /usr/sbin/rpm_solv.py "$@" \
    --repodir=/var/cache/repos/ \
    --output=/var/cache/solv/

