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


from utils.job import JobSolver

from utils.repo import dir_path, \
        repo_repomd, \
        load_stub

from utils.problem import interactive, \
        rule_solver

from utils.format import data_json 

#import gc
#gc.set_debug(gc.DEBUG_LEAK)

import logging

logger = logging.getLogger(__name__)


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
    parser.add_argument('packages', type=str, nargs='+',
                         help='list of packages or solvable glob expression.\n' \
                              'It accepts `repo:` and `selection:` prexif.')
    parser.add_argument('--weak', action='store_true', default=False,
                         help="The solver tries to fulfill weak jobs, " \
                             "but does not report a problem " \
                             "if it is not possible to do so.")

    root = logging.getLogger()
    root.setLevel(logging.WARNING) 
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    args = parser.parse_args()
    
    # problems_callback = interactive
    problems_callback = rule_solver
    data_writer = data_json

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
    
    # FIXME: workaroud to have less 
    # confict to solve 
    # this helps to keep as much packages
    # as possible in the data.json
    for s in pool.solvables:
        s.unset(solv.SOLVABLE_CONFLICTS)
        s.unset(solv.SOLVABLE_OBSOLETES)

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
    
    action_solver |= solv.Job.SOLVER_CLEANDEPS
    if args.weak:
        action_solver |= solv.Job.SOLVER_WEAK

    # convert arguments into jobs
    js = JobSolver(pool, repos, action_solver)
    jobs = js.get_jobs_from_packages(packages) 
    
    if not jobs:
        print("no package matched.")
        sys.exit(1)

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
        
        dw = data_writer(pool)
        data = dw.format(cl.solvables())
        print("install size change: %d K" % trans.calc_installsizechange())

    for key, val in {}.items():
        s = val.pop('solvable', None)
        s = val.pop('job', None)

    with open('{}/data.json'.format(args.exportdir), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if __name__== "__main__":
    main()
