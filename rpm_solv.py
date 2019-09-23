#!/usr/bin/python3

#
# Copyright (c) 2011, Novell Inc.
#
# This program is licensed under the BSD license, read LICENSE.BSD
# for further information
#

import solv
import sys
import os
import glob
import argparse
import configparser
import re
import json

from utils.repo import dir_path, \
        repo_repomd, \
        load_stub, \
        get_repofilter

from utils.problem import interactive, \
        rule_solver

#import gc
#gc.set_debug(gc.DEBUG_LEAK)

def main():
    parser = argparse.ArgumentParser(description="RPM cli dependency solver") 
    parser.add_argument('--repodir', 
                        default='/etc/yum.repos.d/', 
                        type=dir_path, dest='repodir',
                        help='repository directory')
    parser.add_argument('--basearch', default="x86_64", 
                        type=str, help="Base architecture")
    parser.add_argument('--releasever', default="30", 
                        type=str, help="Release version")
    parser.add_argument('--exportdir', default="./", 
                        type=dir_path, help="Directory to use for data.json export")
    parser.add_argument('--repofilter', action="append",
                         type=str, help="limit to specified repositories")
    parser.add_argument('packages', type=str, nargs='+',
                         help='list of packages or solvable glob expression')
    parser.add_argument('--weak', action='store_true', default=False,
                         help="The solver tries to fulfill weak jobs, " \
                             "but does not report a problem " \
                             "if it is not possible to do so.")

    args = parser.parse_args()
    
    # problems_callback = interactive
    problems_callback = rule_solver

    # action_solver = solv.Job.SOLVER_DISTUPGRADE
    # action_solver = solv.Job.SOLVER_UPDATE
    # use a fake install to force full rpm depedencies 
    action_solver = solv.Job.SOLVER_INSTALL

    # read all repo configs
    repos = []
    reposdir = args.repodir

    basearch = args.basearch
    releasever = args.releasever

    for repo_file in sorted(glob.glob('%s/*.repo' % reposdir)):
        config = configparser.ConfigParser()
        config.read(repo_file)
        for section in config.sections():
            repoattr = {'enabled': 0, 'priority': 99, 'autorefresh': 1, 'type': 'rpm', 'metadata_expire': "900"}
            repoattr.update(config[section])
            if repoattr['type'] == 'rpm':
                repo = repo_repomd(section, 'repomd', repoattr, 
                                   basearch = args.basearch,
                                   releasever = args.releasever)
                repos.append(repo)

    pool = solv.Pool()
    pool.setarch(args.basearch)
    pool.set_loadcallback(load_stub)

    # now load all enabled repos into the pool
    #sysrepo = repo_system('@System', 'system')
    #sysrepo.load(pool)
    for repo in repos:
        if int(repo['enabled']):
            repo.load(pool)

    cmdlinerepo = None
    packages = []
    for arg in args.packages:
        if arg.endswith(".rpm") and os.access(arg, os.R_OK):
            if not cmdlinerepo:
                cmdlinerepo = repo_cmdline('@commandline', 'cmdline')
                cmdlinerepo.load(pool)
                cmdlinerepo['packages'] = {}
            s = cmdlinerepo.handle.add_rpm(arg, solv.Repo.REPO_REUSE_REPODATA|solv.Repo.REPO_NO_INTERNALIZE)
            if not s:
                print(pool.errstr)
                sys.exit(1)
            cmdlinerepo['packages'][arg] = s
        elif os.access(arg, os.R_OK):
            # read a list of packages from file
            with open(arg, 'r') as f:
                for a in f.readlines():
                    # remove comment from line
                    p = a.strip().split('#')[0]
                    if p:
                        packages.append(p)
        else:
            packages.append(arg)

    if cmdlinerepo:
        cmdlinerepo.handle.internalize()

    addedprovides = pool.addfileprovides_queue()
    if addedprovides:
        #sysrepo.updateaddedprovides(addedprovides)
        for repo in repos:
            repo.updateaddedprovides(addedprovides)

    pool.createwhatprovides()

    # convert arguments into jobs
    jobs = []
    for arg in packages:
        repofilter = None
        repofilter, arg = get_repofilter(pool, repos, arg, args.repofilter)
        flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_PROVIDES|solv.Selection.SELECTION_GLOB
        flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_REL
        if len(arg) and arg[0] == '/':
            flags |= solv.Selection.SELECTION_FILELIST
        sel = pool.select(arg, flags)
        if repofilter:
           sel.filter(repofilter)
        if sel.isempty():
            sel = pool.select(arg, flags | solv.Selection.SELECTION_NOCASE)
            if repofilter:
               sel.filter(repofilter)
            if not sel.isempty():
                print("[ignoring case for '%s']" % arg)
        if sel.isempty():
            print("nothing matches '%s'" % arg)
            sys.exit(1)
        if sel.flags & solv.Selection.SELECTION_FILELIST:
            print("[using file list match for '%s']" % arg)
        if sel.flags & solv.Selection.SELECTION_PROVIDES:
            print("[using capability match for '%s']" % arg)
        jobs += sel.jobs(action_solver)

    if not jobs:
        print("no package matched.")
        sys.exit(1)

    # returned data
    data={}

    for job in jobs:
        for s in job.solvables():
            print("Name:        %s" % s)
            print("Repo:        %s" % s.repo)
            print("Summary:     %s" % s.lookup_str(solv.SOLVABLE_SUMMARY))
            str_url = s.lookup_str(solv.SOLVABLE_URL)
            if str_url:
                print("Url:         %s" % str_url)
            str_license = s.lookup_str(solv.SOLVABLE_LICENSE)
            if str_license:
                print("License:     %s" % str_license)
            print("Description:\n%s" % s.lookup_str(solv.SOLVABLE_DESCRIPTION))
            
            str_name = s.lookup_str(solv.SOLVABLE_NAME)
            str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
            str_patchcategory = s.lookup_str(solv.SOLVABLE_PATCHCATEGORY)
            str_severity = s.lookup_str(solv.UPDATE_SEVERITY)
            str_reboot = s.lookup_str(solv.UPDATE_REBOOT)
            num_buildtime = s.lookup_num(solv.SOLVABLE_BUILDTIME)
            
            # keep the latest version of each 
            # duplicated packages in jobs
            na = "{}.{}".format(str_name, str_arch)
            d = data.get(na,{})
            data[na] = d
            other = d.get('solvable', None)
            # keep the latest solvable 
            if not other or s.evrcmp(other) == 1:
                d['solvable'] = s

            # read UPDATE_COLLECTION to add advisories packages
            # to the solver process 
            pack = s.Dataiterator(solv.UPDATE_COLLECTION_NAME, '*', solv.Dataiterator.SEARCH_GLOB)
            # remove conflicts to avoid problems resolution
            s.unset(solv.SOLVABLE_CONFLICTS)
            pack.prepend_keyname(solv.UPDATE_COLLECTION)
            for p in pack:
                pos = p.parentpos()
                str_col_evr = pos.lookup_str(solv.UPDATE_COLLECTION_EVR)
                str_col_name = pos.lookup_str(solv.UPDATE_COLLECTION_NAME)
                str_col_arch = pos.lookup_str(solv.UPDATE_COLLECTION_ARCH)
                #str_sev = pos.lookup_str(solv.UPDATE_SEVERITY)
                nevra = "{}-{}.{}".format(str_col_name, str_col_evr, str_col_arch)
                sel = pool.select(nevra, solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_CANON)
                for cs in sel.solvables():
                    #print("collection: {}".format(nevra))
                    # update or insert errata in packages list
                    str_col_name = cs.lookup_str(solv.SOLVABLE_NAME)
                    str_col_arch = cs.lookup_str(solv.SOLVABLE_ARCH) 
                    na = "{}.{}".format(str_col_name, str_col_arch)
                    d = data.get(na,{})
                    data[na] = d
                    advisories = d.get('advisories',[])
                    d['advisories'] = advisories
                    
                    adv = {
                        "name": str_name,
                        "severity": str_severity,
                        "patchcategory": str_patchcategory,
                        "buildtime": num_buildtime,
                    }
                    other = d.get('solvable', None)
                    # keep the latest solvable 
                    if not other or cs.evrcmp(other) == 1:
                        d['solvable'] = cs

                    advisories.append(adv)
                    jobs += sel.jobs(action_solver | solv.Job.SOLVER_TARGETED)
            
            print('')

    jobs = []
    # rebuild jobs from filtered unique data
    for key, val in data.items():
        s = val.get('solvable') 
        if s:
            str_evr = s.lookup_str(solv.SOLVABLE_EVR)
            str_name = s.lookup_str(solv.SOLVABLE_NAME)
            str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
            nevra = "{}-{}.{}".format(str_name, str_evr, str_arch)
            sel = pool.select(nevra, solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_CANON)
            jobs += sel.jobs(action_solver)

    for job in jobs:
        #job.how |= solv.Job.SOLVER_FORCEBEST
        job.how |= solv.Job.SOLVER_CLEANDEPS
        if args.weak:
            job.how |= solv.Job.SOLVER_WEAK

    #pool.set_debuglevel(2)
    solver = pool.Solver()
    flags = solv.Solver.SOLVER_FLAG_SPLITPROVIDES \
        | solv.Solver.SOLVER_FLAG_NO_INFARCHCHECK \
        #| solv.Solver.SOLVER_FLAG_BEST_OBEY_POLICY \

    solver.set_flag(flags, 1)

    while True:
        problems = solver.solve(jobs)
        if not problems:
            break
        problems_callback(jobs, problems)
                                    
    # no problems, show transaction
    trans = solver.transaction()
    del solver
    if trans.isempty():
        print("Nothing to do.")
        sys.exit(0)
    print('')
    print("Transaction summary:")
    print('')
    for cl in trans.classify(solv.Transaction.SOLVER_TRANSACTION_SHOW_OBSOLETES | solv.Transaction.SOLVER_TRANSACTION_OBSOLETE_IS_UPGRADE):
        if cl.type == solv.Transaction.SOLVER_TRANSACTION_ERASE:
            print("%d erased packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_INSTALL:
            print("%d installed packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_REINSTALLED:
            print("%d reinstalled packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_DOWNGRADED:
            print("%d downgraded packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_CHANGED:
            print("%d changed packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_UPGRADED:
            print("%d upgraded packages:" % cl.count)
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_VENDORCHANGE:
            print("%d vendor changes from '%s' to '%s':" % (cl.count, cl.fromstr, cl.tostr))
        elif cl.type == solv.Transaction.SOLVER_TRANSACTION_ARCHCHANGE:
            print("%d arch changes from '%s' to '%s':" % (cl.count, cl.fromstr, cl.tostr))
        else:
            continue
        evr_re = re.compile('^(?:(?P<epoch>\d+):)?(?P<version>.*?)(?:\.(?P<release>\w+))?$')
        for p in cl.solvables():
            str_name = p.lookup_str(solv.SOLVABLE_NAME)
            str_arch = p.lookup_str(solv.SOLVABLE_ARCH)
            str_evr = p.lookup_str(solv.SOLVABLE_EVR)
            num_buildtime = p.lookup_num(solv.SOLVABLE_BUILDTIME)

            nevra = "{}-{}.{}".format(str_name, str_evr, str_arch)
            # update or insert errata in packages list
            na = "{}.{}".format(str_name, str_arch)
            d = data.get(na,{})
            data[na] = d
            d['nevra'] = nevra
            d['name'] = str_name
            d['evr'] = str_evr
            d['arch'] = str_arch
            d['repo'] = str(p.repo) 
            d['buildtime'] = num_buildtime
            # 1:3.0.12-17.el7
            ma = evr_re.match(str_evr)
            if ma is not None: 
                md = ma.groupdict()
                e = md['epoch']
                if not e:
                    d['epoch'] = '0'
                else :
                    d['epoch'] = e
                d['version'] = ma['version']
                d['release'] = ma['release']
            if d['release']:
                frmt_str = '{epoch}:{name}-{version}.{release}.{arch}'
            else: 
                frmt_str = '{epoch}:{name}-{version}.{arch}'
            d['envra'] = frmt_str.format(**d)

            if cl.type == solv.Transaction.SOLVER_TRANSACTION_UPGRADED or cl.type == solv.Transaction.SOLVER_TRANSACTION_DOWNGRADED:
                op = trans.othersolvable(p)
                print("  - %s -> %s" % (p, op))
            else:
                print("  - %s" % p)
        print('')
    print("install size change: %d K" % trans.calc_installsizechange())

    # remove empty data
    for key in data.copy().keys():
        n = data[key].get('name', None)
        if not n:
            del data[key]

    # remove solvable data
    for key, val in data.items():
        s = val.pop('solvable', None)

    with open('{}/data.json'.format(args.exportdir), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__== "__main__":
    main()
