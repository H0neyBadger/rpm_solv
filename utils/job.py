
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
        self.sel_filter = pool.Selection_all()

    def get_update_collection_selection(self, sel, sel_filter=None, operator='='):
        """
        Return a list of selection issued
        by and update patch: objects
        """
        ret = self.pool.Selection()
        for solvable in sel.solvables():
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
                # operators might be =, <, >, <=, >=,
                nevra = "{}.{} {} {}".format(str_col_name, str_col_arch, operator, str_col_evr)
                pkg_sel = solvable.pool.select(nevra, solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_REL)
                ret.add(pkg_sel)
                if sel_filter is not None:
                    ret.filter(sel_filter)
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
        ids = []
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
                f = repofilter.filter(self.sel_filter)
            else: 
                f = self.sel_filter

            sel = self.__build_selection(arg, sel_filter=f)

            if not sel.isempty():
                # read solvables affected by an update/patch
                for s in sel.solvables():
                    if str(s) not in ids:
                        ids.append(str(s))
                        jobs.append(self.pool.Job( job_action | solv.Job.SOLVER_SOLVABLE, s.id))
        return jobs


    def __build_selection(self, arg, sel_filter=None, flags=None, expand_update_collection=True, emptyfail=True):
        logger.debug('Solve selection query `{}`'.format(arg))
        if flags == None:
            flags = solv.Selection.SELECTION_NAME|solv.Selection.SELECTION_PROVIDES|solv.Selection.SELECTION_GLOB
            flags |= solv.Selection.SELECTION_CANON|solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_REL
            if len(arg) and arg[0] == '/':
                flags |= solv.Selection.SELECTION_FILELIST

        sel = self.pool.select(arg, flags)

        if expand_update_collection:
            updates_sel = self.get_update_collection_selection(sel, sel_filter=sel_filter)
            sel.add(updates_sel)

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
                    logger.error("Invalid job flag `{}`. " 
                        "please use a valid keywords".format(flag_name))
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

        is_selection_filter = False
        if pkg.startswith("selection:"):
            # retrieve custom filter
            # selection:add:*
            keyword, action, pkg = pkg.split(':', 2)

            sel = self.__build_selection(pkg, sel_filter=repofilter, flags=None, emptyfail=False)
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
                logger.error("Invalid selection filter `{}`. "
                        "please use `add`, `subtract` `filter` "
                        "or `symmetric_difference` keywords".format(action))
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

