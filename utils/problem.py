import sys
import solv

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



def remove_solvable_from_jobs(solvable, jobs):
    found = False
    print('Searching solvable: {} in jobs'.format(solvable))
    for job in jobs:
        if solvable in job.solvables():
            print('Remove {} from job {}'.format(solvable, job))
            # do not realy remove the job 
            # to keep valid element.jobidx 
            # for solutions
            job.how = solv.Job.SOLVER_NOOP
            #jobs.remove(job)
            found = True
            break
    return found

def rule_solver(jobs, pool, installed_repo, problems):
    """
    Solve problems manually from console interactive prompt
    """
    import time
    for problem in problems:
        print("Problem %d/%d:" % (problem.id, len(problems)))
        print(problem)
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
                        if s.evrcmp(other) == 1:
                            td = other
                        else:
                            td = s
                        remove_solvable_from_jobs(td, jobs)
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP:
                        print("SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP")
                        # example:
                        # nothing provides python3.7dist(xmltodict) = 0.11.0 
                        # needed by python3-pyvirtualize-0.9-6.20181003git57d2307.fc30.noarch
                        
                        fake = installed_repo.handle.add_solvable()
                        fake.name = 'fake:{}'.format(ri.dep.str())
                        fake.arch = 'noarch'
                        fake.evr =  ''
                        fake.add_deparray(solv.SOLVABLE_PROVIDES, ri.dep)
                        #addedprovides = pool.addfileprovides_queue()
                        #installed_repo.handle.internalize()
                        #installed_repo.updateaddedprovides(addedprovides)
                        #pool.createwhatprovides()
                        
                        #requires = s.lookup_idarray(solv.SOLVABLE_REQUIRES)
                        #s.unset(solv.SOLVABLE_REQUIRES)
                        #requires.remove(dep_id)
                        #for d in requires:
                        #    s.add_deparray(solv.SOLVABLE_REQUIRES, d)
                        #    exec_solution(problem.solutions()[0], jobs)
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_REQUIRES:
                        print('SOLVER_RULE_PKG_REQUIRES') 
                        # example:
                        # package prelude-correlator-5.0.1-1.fc30.x86_64 
                        # requires python3-prelude-correlator >= 5.0.0, 
                        # but none of the providers can be installed
                        interactive(jobs, [problem,])
                        break
                        s = ri.solvable
                        req = ri.solvable.pool.whatprovides(ri.dep)
                        if req:
                            for j in jobs:
                                # avoid solvable / job duplication
                                if req[0] in j.solvables():
                                    break
                            else: 
                                # to test with 'php-common-7.3.4-1.fc30.x86_64' 'php-7.3.9-1.fc30.x86_64' 
                                #sel = s.pool.matchdepid(ri.dep, flags, keyname)
                                sel = s.pool.matchdepid(ri.dep, solv.Selection.SELECTION_PROVIDES, solv.SOLVABLE_PROVIDES)
                                # duplicated package, 
                                # the SOLVER_RULE_PKG_SAME_NAME will handle
                                # the issue later
                                print('Add selection {} to current jobs list'.format(sel))
                                jobs += sel.jobs(solv.Job.SOLVER_INSTALL | solv.Job.SOLVER_TARGETED)
                        else:
                            # remove solvable from the stack
                            #import pdb; pdb.set_trace()
                            remove_solvable_from_jobs(s, jobs)
                        break
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
                        remove_solvable_from_jobs(other, jobs)
                        break
                    else:
                        print('uknown rule info {}'.format(ri.type))
                        #import pdb; pdb.set_trace()
                        exit(1)
                else:
                    # for allinfos loop
                    print('Problem allinfos not found')
                    import pdb; pdb.set_trace()
                    exit(1)
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
                remove_solvable_from_jobs(s, jobs)
            else: 
                print('uknown rule {}'.format(rule.type))
                #import pdb; pdb.set_trace()
                exit(1)

