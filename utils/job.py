
import solv
import logging

logger = logging.getLogger(__name__)

class JobSolver(object):
    # job default action flag 
    default_action = None

    def __init__(self, pool, repos, default_action=solv.Job.SOLVER_INSTALL):
        self.default_action = default_action
        self.pool = pool
        self.repos = repos
        self.patch_stack = {}
        self.sel_filter = pool.Selection_all()

    def __add_update_to_stack(self, jobs):
        """
        Compare the input jobs to the update stack 
        to keep the latest updates (of each package)
        active in our jobs
        """
        for job in jobs:
            for solvable in job.solvables():
                str_name = solvable.lookup_str(solv.SOLVABLE_NAME)
                str_arch = solvable.lookup_str(solv.SOLVABLE_ARCH)
                na = "{}.{}".format(str_name, str_arch)
                d = self.patch_stack.get(na, {})
                self.patch_stack[na] = d
                other = d.get('solvable', None)
                if not other:
                    d['job'] = job
                    d['solvable'] = solvable
                    continue

                logger.info("Compare update's evr solvable: `{}` other: `{}`".format(solvable, other))
                c = solvable.evrcmp(other)
                if c == 0:
                    logger.info("Equal evr solvable: `{}` other: `{}`".format(solvable, other))
                    continue
                elif c == 1:
                    logger.info("Keep solvable `{}`".format(solvable))
                    other_job = d['job']
                    # nullify other job
                    other_job.how = solv.Job.SOLVER_NOOP
                    d['job'] = job
                    d['solvable'] = solvable
                elif c == -1:
                    logger.info("Keep solvable `{}`".format(other))
                    # a better version already exists
                    # in our stack
                    job.how = solv.Job.SOLVER_NOOP

    def get_update_collection_selection(self, patch, action):
        """
        Return a list of selection issued 
        by and update patch: objects
        """
        ret = []
        for solvable in patch.solvables():
            # read UPDATE_COLLECTION to add advisories packages
            # to the solver process 
            pack = solvable.Dataiterator(solv.UPDATE_COLLECTION_NAME, '*', solv.Dataiterator.SEARCH_GLOB)
            pack.prepend_keyname(solv.UPDATE_COLLECTION)
            for p in pack:
                pos = p.parentpos()
                str_col_evr = pos.lookup_str(solv.UPDATE_COLLECTION_EVR)
                str_col_name = pos.lookup_str(solv.UPDATE_COLLECTION_NAME)
                str_col_arch = pos.lookup_str(solv.UPDATE_COLLECTION_ARCH)
                #str_col_filename = pos.lookup_str(solv.UPDATE_COLLECTION_FILENAME)
                #col_flags = pos.lookup_str(solv.UPDATE_COLLECTION_FLAGS)
                #str_sev = pos.lookup_str(solv.UPDATE_SEVERITY)
                nevra = "{}-{}.{}".format(str_col_name, str_col_evr, str_col_arch)
                sel = solvable.pool.select(nevra, solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_CANON)
                sel.filter(self.sel_filter)
                if not sel.isempty():
                    jobs = sel.jobs(action)
                    self.__add_update_to_stack(jobs)
                    ret += jobs
        return ret

    def get_jobs_from_packages(self, packages, action=None):
        """
        Convert a list of packages or glob expression string 
        into a list of job
        """
        # convert arguments into jobs
        if not action:
            action=self.default_action
        jobs = []

        for arg in packages:
            repofilter, arg = self.__get_repofilter(arg) 
            is_selection_filter = self.__parse_filter(arg, repofilter=repofilter)
            if is_selection_filter: 
                # update current object's filter 
                # selection:add ... 
                # is not considered as job
                # goto the next cmd args
                continue
            job_action, arg = self.__parse_job(arg, flags=action)
            if repofilter:
                repofilter.filter(self.sel_filter)
                sel = self.__build_selection(arg, sel_filter=repofilter)
            else: 
                sel = self.__build_selection(arg, sel_filter=self.sel_filter)
            
            if not sel.isempty():
                # read solvables affected by an update/patch 
                jobs += self.get_update_collection_selection(sel, job_action) 
                jobs += sel.jobs(job_action)

        return jobs

    
    def __build_selection(self, arg, sel_filter=None, flags=None, emptyfail=True):
        logger.debug('Solve selection query `{}`'.format(arg))
        if flags == None:
            flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_PROVIDES|solv.Selection.SELECTION_GLOB
            flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_REL
            if len(arg) and arg[0] == '/':
                flags |= solv.Selection.SELECTION_FILELIST
        
        sel = self.pool.select(arg, flags)
        if sel_filter:
            sel.filter(sel_filter)
        
        if emptyfail and sel.isempty():
            logger.error("nothing matches '%s'" % arg)
            exit(1)

        return sel
   
    def __parse_job(self, pkg, flags=0):
        """
        retrieve custom repo keyword
        job:weak:package.x86_64 >= 1.0.0
        
        it retruns a string libsolv fags
        return flags, 'package.x86_64 >= 1.0.0'
        """
        old_flags = flags
        if pkg.startswith("job:"):
            # retrieve custom filter
            # job:essential,weak:*
            keyword, action, pkg = pkg.split(':', 2)
            flag_names = action.split(',')
            for flag_name in flag_names:
                flag = getattr(solv.Job, 'SOLVER_'+ flag_name.upper(), None)
                if flag == None:
                    logger.error("Invalid job flag `{}`. ' \
                        'please use a valid keywords".format(flag_name))
                    exit(1)
                flags |= flag

            logger.debug('Set Job action as `{}` flags `{:02X}` -> `{:02X}`'.format(action,old_flags, flags)) 
        return flags, pkg


    def __parse_filter(self, pkg, repofilter=None):
        """
        retrieve custom repo keyword
        selection:add:package.x86_64 >= 1.0.0
        
        it retruns a libsolv selection 
        and package string query (without filter expression) 

        return filter, 'package.x86_64 >= 1.0.0'
        """
        flags = solv.Selection.SELECTION_NAME \
            | solv.Selection.SELECTION_CANON \
            | solv.Selection.SELECTION_DOTARCH \
            | solv.Selection.SELECTION_REL

        is_selection_filter = False
        if pkg.startswith("selection:"):
            # retrieve custom filter
            # selection:add:*
            keyword, action, pkg = pkg.split(':', 2)
            
            sel = self.__build_selection(pkg, sel_filter=repofilter, flags=flags, emptyfail=False)
            if action in ['add']:
                # A + B
                self.sel_filter.add(sel)
            elif action in ['subtract']:
                # A - B
                self.sel_filter.subtract(sel)
            elif action in ['filter']: 
                # A ∩ B
                self.sel_filter.filter(sel)
            elif action in ['symmetric_difference']:
                # A xor B
                # reverse filter
                other = self.sel_filter.clone()
                self.sel_filter.add(sel)
                other.filter(sel)
                self.sel_filter.subtract(other)
            else:
                logger.error("Invalid selection filter `{}`. ' \
                        'please use `add`, `subtract` `filter` ' \
                        'or `symmetric_difference` keywords".format(action))
                exit(1)
            is_selection_filter = True
        return is_selection_filter

    def __get_repofilter(self, pkg):
        """
        retrieve custom repo keyword
        repo:foo:packages-foo.x86_64
        
        it retruns a libsolv selection 
        and package string query (without filter expression) 

        return repofilter, 'packages-foo.x86_64'
        """
        repofilter = None
        if pkg.startswith("repo:"):
            # retrieve custom repo keyword
            # repo:foo:*
            keyword, repo_search, pkg = pkg.split(':', 2)
            repo_names = []
            for repo in self.repos: 
                repo_name = repo.name
                repo_names.append(repo_name)
                if repo_name == repo_search and hasattr(repo, 'handle'):
                    if not repofilter:
                        repofilter = self.pool.Selection()
                    repofilter.add(repo.handle.Selection(solv.Job.SOLVER_SETVENDOR))
                    break
            else:
                logger.error("No repository matches {}".format(repo_search))
                logger.error("Possible repo: name values {}".format(','.join(repo_names)))
                exit(1)
        # return the pkg expression 
        # without the repo:foo: prefix
        return repofilter, pkg

