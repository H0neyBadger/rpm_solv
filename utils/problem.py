import sys
import solv

import logging

logger = logging.getLogger(__name__)

from abc import abstractmethod
import time

class AbstractProblemSolver:

    def __init__(self, pool):
        self.pool = pool
        self.loop_control = []
        self.jobs = []
        self.new_jobs = []
        self.loop_limit = 3000
        self.cache = {}

    @abstractmethod
    def solv_problems(self, problems):
        assert False

    def __build_job_cache(self):
        """
        Build solvalbe name hashtable
        for fast job idx retrival
        """
        # flush cache
        self.cache = {}
        logger.debug("Build job cache for jobs: `{}`".format(len(self.jobs)))
        for idx, job in enumerate(self.jobs):
            for s in job.solvables():
                data = self.cache.get(s.name, [])
                d = (idx, job, s)
                data.append(d) 
                self.cache[s.name] = data

    def run_problem_loop(self, jobs):
        self.loop_count = 0
        self.jobs = jobs
        flags = solv.Solver.SOLVER_FLAG_SPLITPROVIDES \
            | solv.Solver.SOLVER_FLAG_NO_INFARCHCHECK \
            #| solv.Solver.SOLVER_FLAG_BEST_OBEY_POLICY \
        
        while True:
            self.loop_count += 1
            # do not allow the script to run more than 3000 loop
            assert (self.loop_count <= self.loop_limit),"Loop count limit reached"
            # use a new solver to 
            # avoid error SOLVER_RULE_PKG
            # "some dependency problem"
            # and crash
            solver = self.pool.Solver()
            solver.set_flag(flags, 1)
            problems = solver.solve(self.jobs)
            if not problems:
                break
            self.__build_job_cache()
            self.solv_problems(problems)
            
            #self.remove_duplicated_names()
            self.clear_noop_jobs()
            if len(self.new_jobs):
                self.jobs = self.new_jobs + self.jobs
                self.new_jobs = []

            # reload modified deps
            self.pool.createwhatprovides()
        return solver

    def exec_solution(self, solution):
        """
        exec element job based on libsolv solution object
        """
        for element in solution.elements():
            logger.info("run element solution: `{}`".format(element.str()))
            newjob = element.Job()
            if element.type == solv.Solver.SOLVER_SOLUTION_JOB:
                self.jobs[element.jobidx] = newjob
            else:
                if newjob and newjob not in jobs:
                    self.jobs.append(newjob)

    def __get_solvables_from_cache(self, cache):
        """
        yield only valid jobs 
        SOLVER_MULTIVERSION and SOLVER_NOOP are ignored
        """
        for idx, job, s in cache:
            how = job.how & solv.Job.SOLVER_JOBMASK
            if how != solv.Job.SOLVER_MULTIVERSION and how != solv.Job.SOLVER_NOOP:
                #logger.debug("how {:02x} {} {} {}".format(how, idx, job, s))
                yield idx, job, s

    def search_solvables_from_cache(self, name=None, **kwargs):
        """
        use Cache hashtable to retrieve idx, job and solvable
        associated to a solvable name 
        """
        if name is not None: 
            c_jobs = self.cache.get(name, [])
        else: 
            # no name provided 
            # search in all jobs array
            # worst case 
            # flaten list of list
            c_jobs = [ i for sub in self.cache.values() for i in sub ]
        for idx, job, s in self.__get_solvables_from_cache(c_jobs):
            for key, arg in kwargs.items():
                v = getattr(s, key)
                if not isinstance(v, str):
                    v = v()
                if str(v) != arg:
                    break
            else: 
                # the key/arg loop did not break
                # solver match found
                yield idx, job, s
            # the key/arg loop did break
            # go to next solvable
            
    def remove_job(self, idx):
        """
        Set jobs[idx] as SOLVER_NOOP
        """
        # do not realy remove the job 
        # to keep valid element.jobidx 
        # for solutions
        job = self.jobs[idx]
        #logger.debug("how: {:02x} {}".format(job.how, job.solvables()))
        #how = job.how & solv.Job.SOLVER_JOBMASK
        #if how == solv.Job.SOLVER_MULTIVERSION:
        #    import pdb; pdb.set_trace()
        job.how &= ~solv.Job.SOLVER_JOBMASK
        # deleting job element from the array
        # may raise libsolv error 
        # so we use SOLVER_NOOP instead
        return job
           
    def remove_solvable_from_jobs(self, solvable, preserve=0):
        """
        search solvable and remove job from stack
        use preserve = 1 to keep the first job instance
        """

        logger.info('Searching solvable: `{}` in jobs'.format(solvable))
        found = False
        for idx, job, s in self.search_solvables_from_cache(name=solvable.name, 
                                                       evr=solvable.evr, 
                                                       arch=solvable.arch):
            # solvable found !!
            if preserve > 0:
                # keep job active 
                # goto next 
                logger.debug('Preserve `{}` from job `{}` count:`{}`'.format(solvable, job, preserve))
                # used to remove duplicated solvables only
                preserve -= 1
                found = True
                continue
            logger.info('Remove `{}` from job `{}`'.format(solvable, job))
            job = self.remove_job(idx)
            found = True
        return found

    def remove_dep_from_solvable(self, dep, solvable):
        """
        Remove specific deb from solvable
        WARNING: it may break the solvability of problems
        since the original solvable object is modified
        """
        logger.info("Remove dep `{}` form solvable `{}`".format(dep.str(), solvable))
        requires = solvable.lookup_idarray(solv.SOLVABLE_REQUIRES)
        solvable.unset(solv.SOLVABLE_REQUIRES)
        if dep.id in requires: 
            requires.remove(dep.id)
        for d in requires:
            solvable.add_deparray(solv.SOLVABLE_REQUIRES, d)

    def remove_duplicated_names(self):
        """
        Remove duplicated solvable from job stack
        """
        ids = {}
        # clear job stack of duplicated rpm name
        for idx, job, s in self.search_solvables_from_cache():
            # keep the latest package of each
            # available solvale
            # the aim is to limit the number of
            # problem to solv by pruning 
            # duplicated package first
            str_name = s.lookup_str(solv.SOLVABLE_NAME)
            str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
            na = "{}.{}".format(str_name, str_arch)
            other, oidx = ids.get(na, (None, None))
            #print("how: {:02x} {}".format(job.how, job.solvables()))

            job = None
            if other is not None:
                if s.evrcmp(other) == 1:
                    keep = s
                    kidx = idx
                    job = self.remove_job(oidx)
                else:
                    keep = other
                    kidx = oidx
                    job = self.remove_job(idx)
                ids[na] = (keep, kidx)
                logger.debug("Compare `{}` to `{}`. " \
                        "keep: `{}`. " \
                        "clear job: `{}`->`{}`".format(s, other, keep, kidx, job))
            else: 
                ids[na] = (s, idx)

    def clear_noop_jobs(self):
        """
        Remove NOOP 'do nothing' jobs form job stack
        clear 'do nothing' job from list
        """
        # the same jobs array is reused for the next round
        for job in self.jobs: 
            how = job.how & solv.Job.SOLVER_JOBMASK
            if how == solv.Job.SOLVER_NOOP :
                logger.info("End of loop job cleanup how: {:02x} " \
                        "jobmask: {:02x} job: {} " \
                        "sovlables: `{}`".format(job.how, how, job, job.solvables()))
                #logger.info('Remove job {} from jobs stack'.format(job))
                self.jobs.remove(job)

class InteractiveSolver(AbstractProblemSolver):

    def solv_problems(self, problems):
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

class ProblemSolver(AbstractProblemSolver):

    def get_next_evr_from_solvable(self, solvable):
        """
        return the next version available for a specific solvable
        (solvable.evr + 1)

        return None if no better version exists for this solvable
        """
        # search all solvable greater than our origin
        nevra = "{}.{} > {}".format(solvable.name, solvable.arch, solvable.evr)
        pkg_sel = self.pool.select(nevra, 
            solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_REL)
        ret = None
        for other in pkg_sel.solvables():
            if not ret:
                ret = other
            else: 
                if ret.evrcmp(other) == 1:
                    # ret > other
                    # keep only the solvable next to 
                    # our origin 
                    logger.debug('Next solvable candidate found ' \
                            'origin: `{}` (`{}` < `{}`)'.format(solvable, other, ret))
                    ret = other
        return ret

    def fix_pkg_requires_problem(self, solvable, requires, rule_info, problem, force=False):
        #interactive(jobs, [problem])
        #import pdb; pdb.set_trace()
        dep = rule_info.dep
        flags = solv.Job.SOLVER_INSTALL | solv.Job.SOLVER_TARGETED | solv.Job.SOLVER_SOLVABLE
        found = False
        print("Solvable `{}` requires dep `{}`, " \
                "provided by one of: `{}` forced: `{}`".format(solvable, dep, requires, force))
        for s_dep_leaf in self.pool.whatmatchesdep(solv.SOLVABLE_REQUIRES, dep.id):
            for idx, job, s in self.search_solvables_from_cache(name=s_dep_leaf.name, evr=s_dep_leaf.evr, arch=s_dep_leaf.arch):
                next_solvable = self.get_next_evr_from_solvable(s_dep_leaf)
                if next_solvable is not None:
                    #job.how = flags | solv.Job.SOLVER_WEAK 
                    self.remove_job(idx)
                    #remove_solvable_from_jobs(jobs, s_dep_leaf)
                    self.new_jobs.append(solvable.pool.Job(flags, next_solvable.id)) 
                    print('Replace solvable: `{}` by `{}` from job `{}`'.format(s_dep_leaf, next_solvable, job))
                    found = True
                break
        
        if not found : 
            # allow multi install to avoid provide conflicts
            for req in requires + [solvable]:
                key = "`{}` SOLVER_MULTIVERSION".format(req.name)
                if key not in self.loop_control: 
                    self.loop_control.append(key)
                    print("Set solvable `{}` as SOLVER_MULTIVERSION " \
                            "to avoid provides conflicts".format(req))
                    sub_query = solvable.pool.select(req.name, solv.Selection.SELECTION_NAME)
                    install_job = self.pool.Job(flags, req.id)
                    self.new_jobs += sub_query.jobs( solv.Job.SOLVER_MULTIVERSION )
                    self.new_jobs.append(install_job) 
                    found = True
        if not found and force:
            return self.fix_pkg_requires_solutions(solvable, 
                    requires, rule_info, problem, force=force)

        return found

    def fix_pkg_requires_solutions(self, solvable, requires, rule_info, problem, force=False):
        # run solutions as last resort
        # solvable.pool.set_debuglevel(1)
        solutions = problem.solutions()
        # all solvable involved in the problem
        problem_solvable = requires[:] + [solvable] 
        # selected solution
        sol = None
        # blacklist of possible solutions
        sol_blacklist = []
        # list to calculate avg build time
        build_times = []
        solvables_list = []
        #print(problem)
        for idx, solution in enumerate(solutions):
            print("  Solution %d:" % solution.id)
            elements = solution.elements(True)
            for element in elements:
                print("  - %s" % element.str())

        for idx, solution in enumerate(solutions):
            build_times.append([])
            elements = solution.elements(True)
            for element in elements:
                if 'despite the inferior architecture' in element.str():
                    # try to solv the problem by adding i686 packages
                    if len(elements) == 1:
                        sol = idx 
                        logger.debug('Select solution #`{}` based on string match `despite the inferior architecture`'.format(sol+1))
                    # goto next element
                    break
                elif element.type == solv.Solver.SOLVER_SOLUTION_JOB:
                    job_element = self.jobs[element.jobidx]
                    for s in job_element.solvables():
                        s_time = s.lookup_num(solv.SOLVABLE_BUILDTIME)
                        build_times[idx].append(s_time)
                        for r in problem_solvable: 
                            if r.name == s.name:
                                logger.debug("compare {} to {}".format(s, r))
                                evr_cmp = r.evrcmp(s)
                                if evr_cmp > 0:
                                    # get rid of the current problem 
                                    # by removing the involved 
                                    # requirements/solvables
                                    
                                    # the required pkg is >= than the solution
                                    # remove the current solution from the job stack
                                    sol = idx
                                    logger.debug('Select solution #`{}` based on EVR solvable match'.format(sol+1))
                                    break
                                elif evr_cmp < 0:
                                    # the current solution is > requested packages
                                    # reset sol index
                                    sol_blacklist.append(idx)
                                    logger.debug('Reset solution #`{}` based on EVR compare'.format(idx+1))

                        else:
                            # the requirement loop 
                            # did not break goto next
                            continue
                        # the requiremnt loop 
                        # did break (leave to solvable loop)
                        break
        if sol is None: 
            # FIXME
            # avg buildtimes to define 
            # the oldest packages set.
            # and then make a decision 
            ref = None
            for idx, bts in enumerate(build_times):
                if len(bts):
                    avg = 0
                    for x in bts:
                        avg += x
                    avg /= len(bts)
                else:
                    avg = 0
                if idx not in sol_blacklist and (ref is None or avg < ref):
                    sol = idx
                    ref = avg
            logger.debug('Select solution #`{}` based on AVG rpm build time'.format(sol+1))
        
        # import pdb; pdb.set_trace()

        if sol is None and force is False:
            import pdb; pdb.set_trace()
        elif sol is None and force is True:
            #import pdb; pdb.set_trace()
            # FIXME use a default answer to get rid of this problem
            logger.error('Failed to find a valid solution ' \
                    ' for problem `{}` (infinit loop?) '.format(problem))
            sol = 0
        
        # fix problem
        for element in solutions[sol].elements(True):
            print('Run solution: #`{}` `{}`'.format(sol+1, element.str()))
            if 'do not ask to install' in element.str():
                self.jobs[element.jobidx].how |= solv.Job.SOLVER_WEAK 
                break
            # may raise seg fautl
            newjob = element.Job()
            if element.type == solv.Solver.SOLVER_SOLUTION_JOB:
                jobs[element.jobidx] = newjob
            else: 
                if newjob and newjob not in self.jobs:
                    self.new_jobs.append(newjob)

        return True

    def solv_problems(self, problems):
        """
        Solve problems manually from console interactive prompt
        """
        for problem in problems:
            print("Problem loop: {}, {}/{}: " \
                    "`{}`".format(self.loop_count, 
                        problem.id, len(problems), problem))
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
                            # preserve : number of copies to keep in job
                            preserve = 0
                            if s.evrcmp(other) == 1:
                                td = other
                            elif str(s) == str(other):
                                preserve = 1
                                td = s
                            else:
                                td = s
                            print("Compare solvables: `{}` to `{}`" \
                                    " remove: `{}`" \
                                    " and preserve: `{}`".format(s, other, td, preserve))
                            found = self.remove_solvable_from_jobs(td, preserve)
                            assert found
                            break
                        elif ri.type == solv.Solver.SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP:
                            print("SOLVER_RULE_PKG_NOTHING_PROVIDES_DEP")
                            # example:
                            # nothing provides python3.7dist(xmltodict) = 0.11.0 
                            # needed by python3-pyvirtualize-0.9-6.20181003git57d2307.fc30.noarch
                            self.remove_dep_from_solvable(ri.dep, ri.solvable)
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
                            req = self.pool.whatprovides(d)
                            key = '`{}` dep `{}`'.format(s, d)
                            force = False
                            if key in self.loop_control:
                                # force solver solution
                                # if we meet the same 
                                # problem twice
                                force = True
                                #interactive(jobs, [problem])
                                #import pdb; pdb.set_trace()
                            
                            self.loop_control.append(key)
                            
                            if len(req):
                                # the rep exists ( add new job to selection )
                                # add duplicated package, 
                                # the SOLVER_RULE_PKG_SAME_NAME will handle
                                # the issue later
                                # req may contains the same package 
                                # futher time
                                fixed = self.fix_pkg_requires_problem(s, req, ri, problem, force=force)
                                break
                            else: 
                                print('dep not found for solvable: `{}` dep: `{}`'.format(s, d))
                                self.remove_dep_from_solvable(ri.dep, ri.solvable)
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
                            self.remove_solvable_from_jobs(other)
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
                    self.remove_solvable_from_jobs(s)
                elif rule.type == solv.Solver.SOLVER_RULE_JOB:
                    print('SOLVER_RULE_JOB')
                    # ??? conflicting requests
                    print(rule.info().problemstr())
                    s = rule.info().solvable
                    self.remove_solvable_from_jobs(s)
                else: 
                    print('uknown rule {}'.format(rule.type))
                    #import pdb; pdb.set_trace()
                    exit(1)
            
