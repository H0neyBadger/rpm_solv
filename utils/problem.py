import sys
import solv

import logging

logger = logging.getLogger(__name__)

def interactive(jobs, problems):
    """
    Solve problems manually from console interactive prompt
    """
    for problem in problems:
        print("Problem %d/%d:" % (problem.id, len(problems)))
        print(problem)
        solutions = problem.solutions()
        for solution in solutions:
            print("  Solution %d:" % solution.id)
            elements = solution.elements(True)
            for element in elements:
                print("  - %s" % element.str())
            print('')
        sol = ''
        while not (sol == 's' or sol == 'q' or (sol.isdigit() and int(sol) >= 1 and int(sol) <= len(solutions))):
            sys.stdout.write("Please choose a solution: ")
            sys.stdout.flush()
            sol = sys.stdin.readline().strip()
        if sol == 's':
            continue        # skip problem
        if sol == 'q':
            sys.exit(1)
        solution = solutions[int(sol) - 1]
        for element in solution.elements():
            newjob = element.Job()
            if element.type == solv.Solver.SOLVER_SOLUTION_JOB:
                jobs[element.jobidx] = newjob
            else:
                if newjob and newjob not in jobs:
                    jobs.append(newjob)

def exec_solution(solution, jobs):

    for element in solution.elements():
        print(element.str())
        newjob = element.Job()
        if element.type == solv.Solver.SOLVER_SOLUTION_JOB:
            jobs[element.jobidx] = newjob
        else:
            if newjob and newjob not in jobs:
                jobs.append(newjob)

def get_solvables_from_jobs(jobs):
    for idx, job in enumerate(jobs):
        how = job.how & solv.Job.SOLVER_JOBMASK
        if how != solv.Job.SOLVER_MULTIVERSION and how != solv.Job.SOLVER_NOOP:
            for s in job.solvables():
                yield idx, s

def search_solvables_from_jobs(jobs, **kwargs):
    for idx, s in get_solvables_from_jobs(jobs):
        for key, arg in kwargs.items():
            v = getattr(s, key)
            if str(v) != arg:
                break
        else: 
            # the key/arg loop did not break
            # solver match found
            yield idx, s
        # the key/arg loop did break
        # go to next solvable
        
 
def remove_job(jobs, idx):
     # do not realy remove the job 
     # to keep valid element.jobidx 
     # for solutions
     job = jobs[idx]
     job.how &= ~solv.Job.SOLVER_JOBMASK
     return job
       
def remove_solvable_from_jobs(jobs, solvable, preserve=0):
    print('Searching solvable: {} in jobs'.format(solvable))
    found = False
    for idx, s in search_solvables_from_jobs(jobs, name=solvable.name, evr=solvable.evr, arch=solvable.arch):
        # solvable found !!
        if preserve > 0:
            # keep job active 
            # goto next 
            print('Preserve {} from job {}'.format(solvable, job))
            # used to remove duplicated solvables only
            preserve -= 1
            found = True
            break 
        job = remove_job(jobs, idx)
        print('Remove {} from job {}'.format(solvable, job))
        #print('{:02x}'.format(job.how))
        #jobs.remove(job)
        found = True
        #break
    return found

def remove_requied_solvables(jobs, solvable):
    print("Remove solvable `{}` requirements".format(solvable))
    for dep in solvable.lookup_idarray(solv.SOLVABLE_REQUIRES):
        sel = solvable.pool.matchdepid(dep, solv.Selection.SELECTION_REQUIRES, solv.SOLVABLE_REQUIRES)
        for s in sel.solvables():
            found = remove_solvable_from_jobs(jobs, s)

def remove_dep_from_solvable(dep, solvable):
    print("Remove dep `{}` form solvable `{}`".format(dep.str(), solvable))
    requires = solvable.lookup_idarray(solv.SOLVABLE_REQUIRES)
    solvable.unset(solv.SOLVABLE_REQUIRES)
    if dep.id in requires: 
        requires.remove(dep.id)
    for d in requires:
        solvable.add_deparray(solv.SOLVABLE_REQUIRES, d)

def rule_solver(count, jobs, pool, problems, loop_control):
    """
    Solve problems manually from console interactive prompt
    """
    import time
    njobs = []
    for problem in problems:
        print("Problem loop: {}, {}/{}: `{}`".format(count, problem.id, len(problems), problem))
        #rules = problem.findallproblemrules()
        # read the first problem rule
        rules = (problem.findproblemrule(),)
        for rule in rules: 
            #print(rule.type)
            rule_all_infos = rule.allinfos()
            if rule.type == solv.Solver.SOLVER_RULE_PKG:
                # A package dependency rule.
                #print('SOLVER_RULE_PKG package dependency rule.')
                for ri in rule_all_infos:
                    #print(ri.problemstr())
                    if ri.type == solv.Solver.SOLVER_RULE_PKG_SAME_NAME:
                        print("SOLVER_RULE_PKG_SAME_NAME")
                        other = ri.othersolvable
                        s = ri.solvable
                        print("compare {} to {}".format(s, other))
                        # preserve : number of copies to keep in job
                        preserve = 0
                        if s.evrcmp(other) == 1:
                            td = other
                        elif str(s) == str(other):
                            preserve = 1
                            td = s
                        else:
                            td = s
                        found = remove_solvable_from_jobs(jobs, td, preserve)
                        if not found:
                            solution = problem.solutions()
                            if len(solution) > 0:
                                exec_solution(solution[0], jobs)
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP:
                        print("SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP")
                        # example:
                        # nothing provides python3.7dist(xmltodict) = 0.11.0 
                        # needed by python3-pyvirtualize-0.9-6.20181003git57d2307.fc30.noarch
                        remove_dep_from_solvable(ri.dep, ri.solvable)
                        continue
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_REQUIRES:
                        print('SOLVER_RULE_PKG_REQUIRES') 
                        # example:
                        # package prelude-correlator-5.0.1-1.fc30.x86_64 
                        # requires python3-prelude-correlator >= 5.0.0, 
                        # but none of the providers can be installed
                        
                        s = ri.solvable
                        d = ri.dep
                        # do not try to solve the same deps twice
                        req = ri.solvable.pool.whatprovides(d)
                        
                        if len(req):
                            # the rep exists ( add new job to selection )
                            # add duplicated package, 
                            # the SOLVER_RULE_PKG_SAME_NAME will handle
                            # the issue later
                            for r in req:
                                # to test this issue
                                # 'hwloc-libs-2.0.4-1.fc31.i686' 'legion-openmpi-19.09.1-1.fc31.i686'
                                job = r.pool.Job( solv.Job.SOLVER_INSTALL | solv.Job.SOLVER_TARGETED | solv.Job.SOLVER_SOLVABLE, r.id)
                                # search if a beter version exists in our jobs
                                for idx, other in search_solvables_from_jobs(jobs, name=r.name, arch=r.arch):
                                    if r.evrcmp(other) != 1:
                                        print('Solvable is superseded dep: `{}`->`{}` by: `{}`'.format(s, r, other, d))
                                        remove_dep_from_solvable(d, s)
                                        #found = remove_solvable_from_jobs(jobs, s)
                                        #found = remove_solvable_from_jobs(jobs, r)
                                        break
                                    else: 
                                        # remove other old pkg
                                        remove_job(jobs, idx)
                                else:
                                   # keep r in the stack
                                   print('Add job `{}` to current jobs list'.format(job))
                                   njobs.append(job)
                        else: 
                            print('dep not found for solvable: `{}` dep: `{}`'.format(s, d))
                            remove_dep_from_solvable(ri.dep, ri.solvable)
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_CONFLICTS:
                        print('SOLVER_RULE_PKG_CONFLICTS') 
                        # example
                        # package compat-openssl10-devel-1:1.0.2o-5.fc30.i686 
                        # conflicts with openssl-devel provided 
                        # by openssl-devel-1:1.1.1c-6.fc30.x86_64
                        s = ri.solvable
                        other = ri.othersolvable
                        # remove conflicts to avoid problems resolution
                        s.unset(solv.SOLVABLE_CONFLICTS)
                        other.unset(solv.SOLVABLE_CONFLICTS)
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_OBSOLETES:
                        print('SOLVER_RULE_PKG_OBSOLETES')
                        # example
                        # package infiniband-diags-2.0.0-2.el7.x86_64
                        # obsoletes libibmad < 2.0.0-2.el7
                        # provided by libibmad-1.3.13-1.el7.x86_64
                        other = ri.othersolvable
                        #s.unset(solv.SOLVABLE_OBSOLETES)
                        remove_solvable_from_jobs(jobs, other)
                        break
                    else:
                        print('uknown rule info {}'.format(ri.type))
                        #import pdb; pdb.set_trace()
                        exit(1)
                else:
                    # for allinfos loop
                    if not rule_all_infos:
                        i = rule.info()
                        if i: 
                            print('Problem allinfos not found: `{}` ' \
                                    'with solvable: `{}` and other :`{}`'.format(
                                    i.problemstr(), i.solvable, i.othersolvable))
                            #import pdb; pdb.set_trace()
                        else: 
                            print('Problem allinfos not found `{}`'.format(i))
                        break
            elif rule.type == solv.Solver.SOLVER_RULE_INFARCH:
                print('SOLVER_RULE_INFARCH')
                # from libsolv-bindings.txt
                # Infarch rules are also negative assertions, 
                # they disallow the installation of packages when 
                # there are packages of the same name 
                # but with a better architecture.
                # example: 
                # gcc-gfortran-9.0.1-0.10.fc30.i686 has inferior architecture
                print(rule.info().problemstr())
                s = rule.info().solvable
                remove_solvable_from_jobs(jobs, s)
            elif rule.type == solv.Solver.SOLVER_RULE_JOB:
                print('SOLVER_RULE_JOB')
                # ??? conflicting requests
                print(rule.info().problemstr())
                s = rule.info().solvable
                remove_solvable_from_jobs(jobs, s)
            else: 
                print('uknown rule {}'.format(rule.type))
                #import pdb; pdb.set_trace()
                exit(1)
    # playing with the jobs durring problem resolution
    # may raises seg fault from libsolv
    jobs += njobs
    ids = {}
    # clear job stack of duplicated rpm name
    for idx, s in search_solvables_from_jobs(jobs):
        # keep the latest package of each
        # available solvale
        # the aim is to limit the number of
        # problem to solv by pruning 
        # duplicated package first
        str_name = s.lookup_str(solv.SOLVABLE_NAME)
        str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
        na = "{}.{}".format(str_name, str_arch)
        other, oidx = ids.get(na, (None, None))
        job = None
        if other is not None:
            if s.evrcmp(other) == 1:
                keep = s
                kidx = idx
                job = remove_job(jobs, oidx)
            else:
                keep = other
                kidx = oidx
                job = remove_job(jobs, idx)
            ids[na] = (keep, kidx)
            logger.debug("compare `{}` to `{}`. keep: `{}`. clear job: `{}`->`{}`".format(s, other, keep, kidx, job))
        else: 
            ids[na] = (s, idx)

    # clear 'do nothing' job from list
    # the same jobs array is reused for the next round
    for job in jobs: 
        how = job.how & solv.Job.SOLVER_JOBMASK
        logger.debug('End of loop job cleanup how: {:02x} jobmask: {:02x} job: {}'.format(job.how, how, job))
        if how == solv.Job.SOLVER_NOOP :
            logger.info('Remove job {} from jobs stack'.format(job))
            # 
            jobs.remove(job)
     
