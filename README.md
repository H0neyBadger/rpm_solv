# rpm_solv
The aim of this script is to pre-calculate rpms’ dependencies for a third party system.
It can be useful to : 
* create a versionlock that is actually aware of dependencies. 
* create/anlyse advisories’ dependencies 
* calculate the size for a specific update

This script is heavily based on libsolv’s pysolv.
Thus I kept the original BSD license.

https://github.com/openSUSE/libsolv/blob/master/examples/pysolv


Requirements:
* python3
* python3-solv (libsolv python binding)

usage
```bash
# list curl dependencies
./rpm_solv.py curl-7.65.3-2.fc30
cat ./data.json

# Solve all ppc64le’s patches for fedora 29
./rpm_solv.py \
    --repodir ./repos/ \
    --basearch ppc64le \
    --releasever 29 \
    --weak \
    'patch:*'

# Solve 'patch:*' from the 'updates' repository
# And solve '*' from the 'fedora' repo using the repofilter arg
./rpm_solv.py \ 
    'repo:updates:patch:*' \
    '*' \
    --repofilter=fedora \
    --weak

```

TODO:
* manage solutions’ elements correctly
* fix cache folder (for standard user)

