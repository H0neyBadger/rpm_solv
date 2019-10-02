
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
                other = d.get('solvable', None)
                logger.info("Conpare update's evr solvable: `{}` other: `{}`".format(solvable, other))
                if not other:
                    d['jobs'] = jobs
                    d['solvable'] = solvable
                elif other == solvable:
                    continue
                elif solvable.evrcmp(other) == 1:
                    logger.info("Keep `{}`".format(solvable))
                    other_job = d['jobs']
                    for job in other_job:
                        # nullify other job
                        job.how = solv.Job.SOLVER_NOOP
                    d['jobs'] = jobs
                    d['solvable'] = solvable
                else:
                    for job in jobs:
                        # a better version already exists 
                        # in our stack
                        job.how = solv.Job.SOLVER_NOOP
                self.patch_stack[na] = d


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
            flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_PROVIDES|solv.Selection.SELECTION_GLOB
            flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_REL
            if len(arg) and arg[0] == '/':
                flags |= solv.Selection.SELECTION_FILELIST
            sel = self.pool.select(arg, flags)
            if repofilter:
               sel.filter(repofilter)
            if sel.isempty():
                sel = self.pool.select(arg, flags | solv.Selection.SELECTION_NOCASE)
                if repofilter:
                   sel.filter(repofilter)
                if not sel.isempty():
                    print("[ignoring case for '%s']" % arg)
            if sel.isempty():
                print("nothing matches '%s'" % arg)
                exit(1)
            if sel.flags & solv.Selection.SELECTION_FILELIST:
                print("[using file list match for '%s']" % arg)
            if sel.flags & solv.Selection.SELECTION_PROVIDES:
                print("[using capability match for '%s']" % arg)
            
            # read solvables affected by an update/patch 
            jobs += self.get_update_collection_selection(sel, action) 
            jobs += sel.jobs(action)

        return jobs

    def __get_repofilter(self, pkg):
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
        # withour the repo:foo: prefix
        return repofilter, pkg

