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

def remove_solvable_from_jobs(solvable, jobs):
    for job in jobs:
        if solvable in job.solvables(): 
            jobs.remove(job)

def rule_solver(jobs, problems):
    """
    Solve problems manually from console interactive prompt
    """
    for problem in problems:
        print("Problem %d/%d:" % (problem.id, len(problems)))
        print(problem)
        solutions = problem.solutions()
        rules = problem.findallproblemrules()
        sol = ''
        for rule in rules: 
            #print(rule.type)
            rule_all_infos = rule.allinfos()
            if rule.type == solv.Solver.SOLVER_RULE_PKG:
                # A package dependency rule.
                print('SOLVER_RULE_PKG package dependency rule.')
                for ri in rule_all_infos:
                    print(ri.problemstr())
                    if ri.type == solv.Solver.SOLVER_RULE_PKG_SAME_NAME:
                        print("SOLVER_RULE_PKG_SAME_NAME")
                        other = ri.othersolvable
                        s = ri.solvable
                        print("compare {} to {}".format(s, other))
                        if s.evrcmp(other) == 1:
                            td = other
                        else:
                            td = s
                        print("remove {}".format(td))
                        remove_solvable_from_jobs(td, jobs)
                        sol = "s"
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP:
                        print("SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP")
                        # example:
                        # nothing provides python3.7dist(xmltodict) = 0.11.0 
                        # needed by python3-pyvirtualize-0.9-6.20181003git57d2307.fc30.noarch
                        s = ri.solvable
                        #remove_solvable_from_jobs(s, jobs)
                        #FIXME: keep the solvable in the stack
                        # despite the missing required dependencies
                        s.unset(solv.SOLVABLE_REQUIRES)
                        sol = "s"
                        break
                    elif ri.type == solv.Solver.SOLVER_RULE_PKG_REQUIRES:
                        print('SOLVER_RULE_PKG_REQUIRES') 
                        # example:
                        # package prelude-correlator-5.0.1-1.fc30.x86_64 
                        # requires python3-prelude-correlator >= 5.0.0, 
                        # but none of the providers can be installed
                        s = ri.solvable
                        # remove solvable from the stack
                        remove_solvable_from_jobs(s, jobs)
                        sol = "s"
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
                        sol = "s"
                        break
                    else:
                        print('uknown rule info {}'.format(ri.type))
                        #import pdb; pdb.set_trace()
                        exit()
                else:
                    # for allinfos loop
                    print('Problem allinfos not found')
                    if rule.info().type == solv.Solver.SOLVER_RULE_PKG and len(problem.solutions()) == 1:
                        # example:
                        # package prelude-correlator-5.0.1-1.fc30.x86_64 
                        # requires python3-prelude-correlator >= 5.0.0, 
                        # but none of the providers can be installed
                        
                        # only one solution exists
                        sol = '1'
                    elif rule.info().type == solv.Solver.SOLVER_RULE_PKG:
                        # expample:
                        # package compat-openssl10-pkcs11-helper-devel-1.22-8.fc30.i686 
                        # conflicts with pkcs11-helper-devel 
                        # provided by pkcs11-helper-devel-1.22-7.fc30.i686
                        s = rule.info().solvable
                        other = rule.info().othersolvable
                        # remove conflicts to avoid problems resolution
                        s.unset(solv.SOLVABLE_CONFLICTS)
                        if other:
                            other.unset(solv.SOLVABLE_CONFLICTS)
                        sol = 's'
                    else: 
                        #import pdb; pdb.set_trace()
                        pass
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
                sol = "s"
            else: 
                print('uknown rule {}'.format(rule.type))
                sol = ''
                #import pdb; pdb.set_trace()
                #exit()

        for solution in solutions:
            print("  Solution %d:" % solution.id)
            elements = solution.elements(True)
            for element in elements:
                print("  - %s" % element.str())
            print('')
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

