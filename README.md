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
./rpm_solv.py \ 
    'repo:updates:patch:*' \
    '*' \
    --weak

# exclude fedora repo from selection
./rpm_solv.py \
    "repo:fedora:selection:subtract:*" \
    "bash" --weak 

# exclude all .x86_64 package from BaseOS repo
# "repo:BaseOS:selection:subtract:*.x86_64"
# then exclude bash>4.4.19-7.el8
# finally, request bash package resolution
./rpm_solv.py --repodir ./repos/  \
    "repo:BaseOS:selection:subtract:*.x86_64" \
    "selection:subtract:bash>4.4.19-7.el8" \
    "repo:BaseOS:bash" --weak

# the selection filter only affect the pakages query
# it does not change the packages solver set 
# in other words 
# even if you manually exculde a package 
# from the selection. the excluded package
# might be present in the final resutl 
# because of dependecies

# To modify the job solving process 
# you may change jobs flags 
# by using action delimited 
# by a comma character
# "job:essential,forcebest:bash"
# https://github.com/openSUSE/libsolv/blob/master/doc/libsolv-bindings.txt#the-job-class
./rpm_solv.py --repodir ./repos/  \
    "job:essential,forcebest:bash" 

```

