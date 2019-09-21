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
import tempfile
import time
import re

from urllib import request
#import gc
#gc.set_debug(gc.DEBUG_LEAK)

class repo_generic(dict):
    def __init__(self, name, type, attribs = {}, **kwargs):
        for k in attribs:
            self[k] = attribs[k]
        self.extra_vars = kwargs
        self.name = name
        self.type = type

    def calc_cookie_file(self, filename):
        chksum = solv.Chksum(solv.REPOKEY_TYPE_SHA256)
        chksum.add("1.1")
        chksum.add_stat(filename)
        return chksum.raw()

    def calc_cookie_fp(self, fp):
        chksum = solv.Chksum(solv.REPOKEY_TYPE_SHA256)
        chksum.add("1.1");
        chksum.add_fp(fp)
        return chksum.raw()

    def calc_cookie_ext(self, f, cookie):
        chksum = solv.Chksum(solv.REPOKEY_TYPE_SHA256)
        chksum.add("1.1");
        chksum.add(cookie)
        chksum.add_fstat(f.fileno())
        return chksum.raw()
    
    def format_expire_time(self, expire="6h"):
        """
        Convert yum expire format into time in sec

        Time (in seconds) after which the metadata will expire. So that if the 
        current metadata downloaded is less than this many seconds old then 
        yum will not update the metadata against the repository. If you find 
        that yum is not downloading information on updates as often as you 
        would like lower the value of this option. You can also change from the
        default of using seconds to using days, hours or minutes by appending 
        a d, h or m respectively. The default is 6 hours, to compliment 
        yum-updatesd running once an hour. It's also possible to use the word 
        "never", meaning that the metadata will never expire. Note that when 
        using a metalink file the metalink must always be newer than the 
        metadata for the repository, due to the validation, so this timeout 
        also applies to the metalink file.
        """
        # The default is 6 hours
        if expire == "never": 
            return -1
        elif expire.endswith('d'):
            val = expire.split('d')[0]
            return int(val)*60*60*24
        elif expire.endswith('h'):
            val = expire.split('h')[0]
            return int(val)*60*60
        elif expire.endswith('m'):
            val = expire.split('')[0]
            return int(val)*60
        else:
            return int(expire)

    def cachepath(self, ext = None):
        path = re.sub(r'^\.', '_', self.name)
        if ext:
            path += "_" + ext + ".solvx"
        else:
            path += ".solv"
        return "/var/cache/solv/" + re.sub(r'[/]', '_', path)
        
    def load(self, pool):
        self.handle = pool.add_repo(self.name)
        self.handle.appdata = self
        self.handle.priority = 99 - self['priority']
        dorefresh = bool(int(self['autorefresh']))
        if dorefresh:
            try:
                st = os.stat(self.cachepath())
                metadata_expire = self.get('metadata_expire',"1h")
                expire = self.format_expire_time(metadata_expire)
                if expire == -1 or time.time() - st.st_mtime < expire:
                    dorefresh = False
            except OSError:
                pass
        self['cookie'] = ''
        self['extcookie'] = ''
        if not dorefresh and self.usecachedrepo(None):
            print("repo: '%s': cached" % self.name)
            return True
        return False

    def load_ext(self, repodata):
        return False

    def setfromurls(self, urls):
        if not urls:
            return
        url = urls[0]
        print("[using mirror %s]" % re.sub(r'^(.*?/...*?)/.*$', r'\1', url))
        self['baseurl'] = url

    def setfrommetalink(self, metalink):
        # FIXME
        # use xml module instead
        f = self.download(metalink, False, None)
        if not f:
            return None
        f = os.fdopen(f.dup(), 'r')
        urls = []
        chksum = None
        for l in f.readlines():
            l = l.strip()
            m = re.match(r'^<hash type="sha256">([0-9a-fA-F]{64})</hash>', l)
            # FIXME
            # ignore chksum 
            # the regex in xml file is pretty broken
            # the metalink file may contains many differents versions and checksums 
            # it ultimately result in missmatch checksum 
            #
            # if m:
            #    chksum = solv.Chksum(solv.REPOKEY_TYPE_SHA256, m.group(1))
            m = re.match(r'^<url.*>(https?://.+)repodata/repomd.xml</url>', l)
            if m:
                urls.append(m.group(1))
        if not urls:
            chksum = None       # in case the metalink is about a different file
        f.close()
        self.setfromurls(urls)
        return chksum
        
    def setfrommirrorlist(self, mirrorlist):
        f = self.download(mirrorlist, False, None)
        if not f:
            return
        f = os.fdopen(f.dup(), 'r')
        urls = []
        for l in f.readline():
            l = l.strip()
            if l[0:6] == 'http://' or l[0:7] == 'https://':
                urls.append(l)
        self.setfromurls(urls)
        f.close()

    def sub_url(self, url):
        """
        replace/substitute repo vars from url
        example: 
          releasever
          basearch 
          ...
        """
        extra_vars = self.extra_vars
        for key, val in self.extra_vars.items():
            url = re.sub(r"\${}".format(key), val, url)
        return url

    def download(self, file, uncompress, chksum, markincomplete=False):
        url = None
        if 'baseurl' not in self:
            if 'metalink' in self:
                if file != self['metalink']:
                    metalinkchksum = self.setfrommetalink(self['metalink'])
                    if file == 'repodata/repomd.xml' and metalinkchksum and not chksum:
                        chksum = metalinkchksum
                else:
                    url = file
            elif 'mirrorlist' in self:
                if file != self['mirrorlist']:
                    self.setfrommirrorlist(self['mirrorlist'])
                else:
                    url = file
        if not url:
            if 'baseurl' not in self:
                print("%s: no baseurl" % self.name)
                return None
            url = re.sub(r'/$', '', self['baseurl']) + '/' + file
        f = tempfile.TemporaryFile(mode='wb')
        real_url = self.sub_url(url)
        mem_f = request.urlopen(real_url).read()
        f.write(mem_f)
        f.seek(0)
        if chksum:
            fchksum = solv.Chksum(chksum.type)
            if not fchksum:
                print("%s: unknown checksum type" % file)
                if markincomplete:
                    self['incomplete'] = True
                return None
            fchksum.add_fd(f.fileno())
            # force .hex() methode to avoid "<type>:unfinished" hash
            fchksum.hex()

            if fchksum != chksum:
                print(file, url, chksum, fchksum)
                print("%s: checksum mismatch" % file)
                if markincomplete:
                    self['incomplete'] = True
                return None
        if uncompress:
            return solv.xfopen_fd(file, f.fileno())
        return solv.xfopen_fd(None, f.fileno())

    def usecachedrepo(self, ext, mark=False):
        try: 
            repopath = self.cachepath(ext)
            f = open(repopath, 'rb')
            f.seek(-32, os.SEEK_END)
            fcookie = f.read(32)
            if len(fcookie) != 32:
                return False
            if not ext:
                cookie = self['cookie']
            else:
                cookie = self['extcookie']
            if cookie and fcookie != cookie:
                return False
            if self.type != 'system' and not ext:
                f.seek(-32 * 2, os.SEEK_END)
                fextcookie = f.read(32)
                if len(fextcookie) != 32:
                    return False
            f.seek(0)
            f = solv.xfopen_fd('', f.fileno())
            flags = 0
            if ext:
                flags = solv.Repo.REPO_USE_LOADING|solv.Repo.REPO_EXTEND_SOLVABLES
                if ext != 'DL':
                    flags |= solv.Repo.REPO_LOCALPOOL
            if not self.handle.add_solv(f, flags):
                return False
            if self.type != 'system' and not ext:
                self['cookie'] = fcookie
                self['extcookie'] = fextcookie
            if mark:
                # no futimes in python?
                try:
                    os.utime(repopath, None)
                except Exception:
                    pass
        except IOError:
            return False
        return True

    def writecachedrepo(self, ext, repodata=None):
        if 'incomplete' in self:
            return
        tmpname = None
        try:
            if not os.path.isdir("/var/cache/solv"):
                os.mkdir("/var/cache/solv", 0o755)
            (fd, tmpname) = tempfile.mkstemp(prefix='.newsolv-', dir='/var/cache/solv')
            os.fchmod(fd, 0o444)
            f = os.fdopen(fd, 'wb+')
            f = solv.xfopen_fd(None, f.fileno())
            if not repodata:
                self.handle.write(f)
            elif ext:
                repodata.write(f)
            else:       # rewrite_repos case, do not write stubs
                self.handle.write_first_repodata(f)
            f.flush()
            if self.type != 'system' and not ext:
                if not self['extcookie']:
                    self['extcookie'] = self.calc_cookie_ext(f, self['cookie'])
                f.write(self['extcookie'])
            if not ext:
                f.write(self['cookie'])
            else:
                f.write(self['extcookie'])
            f.close
            if self.handle.iscontiguous():
                # switch to saved repo to activate paging and save memory
                nf = solv.xfopen(tmpname)
                if not ext:
                    # main repo
                    self.handle.empty()
                    flags = solv.Repo.SOLV_ADD_NO_STUBS
                    if repodata:
                        flags = 0       # rewrite repos case, recreate stubs
                    if not self.handle.add_solv(nf, flags):
                        sys.exit("internal error, cannot reload solv file")
                else:
                    # extension repodata
                    # need to extend to repo boundaries, as this is how
                    # repodata.write() has written the data
                    repodata.extend_to_repo()
                    flags = solv.Repo.REPO_EXTEND_SOLVABLES
                    if ext != 'DL':
                        flags |= solv.Repo.REPO_LOCALPOOL
                    repodata.add_solv(nf, flags)
            os.rename(tmpname, self.cachepath(ext))
        except (OSError, IOError):
            if tmpname:
                os.unlink(tmpname)

    def updateaddedprovides(self, addedprovides):
        if 'incomplete' in self:
            return 
        if not hasattr(self, 'handle'):
            return 
        if self.handle.isempty():
            return
        # make sure there's just one real repodata with extensions
        repodata = self.handle.first_repodata()
        if not repodata:
            return
        oldaddedprovides = repodata.lookup_idarray(solv.SOLVID_META, solv.REPOSITORY_ADDEDFILEPROVIDES)
        if not set(addedprovides) <= set(oldaddedprovides):
            for id in addedprovides:
                repodata.add_idarray(solv.SOLVID_META, solv.REPOSITORY_ADDEDFILEPROVIDES, id)
            repodata.internalize()
            self.writecachedrepo(None, repodata)

    def packagespath(self):
        return ''

    def add_ext_keys(self, ext, repodata, handle):
        if ext == 'DL':
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.REPOSITORY_DELTAINFO)
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.REPOKEY_TYPE_FLEXARRAY)
        elif ext == 'DU':
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.SOLVABLE_DISKUSAGE)
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.REPOKEY_TYPE_DIRNUMNUMARRAY)
        elif ext == 'FL':
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.SOLVABLE_FILELIST)
            repodata.add_idarray(handle, solv.REPOSITORY_KEYS, solv.REPOKEY_TYPE_DIRSTRARRAY)
        else:
            for langtag, langtagtype in [
                (solv.SOLVABLE_SUMMARY, solv.REPOKEY_TYPE_STR),
                (solv.SOLVABLE_DESCRIPTION, solv.REPOKEY_TYPE_STR),
                (solv.SOLVABLE_EULA, solv.REPOKEY_TYPE_STR),
                (solv.SOLVABLE_MESSAGEINS, solv.REPOKEY_TYPE_STR),
                (solv.SOLVABLE_MESSAGEDEL, solv.REPOKEY_TYPE_STR),
                (solv.SOLVABLE_CATEGORY, solv.REPOKEY_TYPE_ID)
            ]:
                repodata.add_idarray(handle, solv.REPOSITORY_KEYS, self.handle.pool.id2langid(langtag, ext, 1))
                repodata.add_idarray(handle, solv.REPOSITORY_KEYS, langtagtype)
        

class repo_repomd(repo_generic):
    def load(self, pool):
        if super(repo_repomd, self).load(pool):
            return True
        sys.stdout.write("rpmmd repo '%s': " % self.name)
        sys.stdout.flush()
        f = self.download("repodata/repomd.xml", False, None, None)
        if not f:
            print("no repomd.xml file, skipped")
            self.handle.free(True)
            del self.handle
            return False
        self['cookie'] = self.calc_cookie_fp(f)
        if self.usecachedrepo(None, True):
            print("cached")
            return True
        self.handle.add_repomdxml(f, 0)
        print("fetching")
        (filename, filechksum) = self.find('primary')
        if filename:
            f = self.download(filename, True, filechksum, True)
            if f:
                self.handle.add_rpmmd(f, None, 0)
            if 'incomplete' in self:
                return False # hopeless, need good primary
        (filename, filechksum) = self.find('updateinfo')
        if filename:
            f = self.download(filename, True, filechksum, True)
            if f:
                self.handle.add_updateinfoxml(f, 0)
        self.add_exts()
        self.writecachedrepo(None)
        # must be called after writing the repo
        self.handle.create_stubs()
        return True

    def find(self, what):
        di = self.handle.Dataiterator_meta(solv.REPOSITORY_REPOMD_TYPE, what, solv.Dataiterator.SEARCH_STRING)
        di.prepend_keyname(solv.REPOSITORY_REPOMD)
        for d in di:
            dp = d.parentpos()
            filename = dp.lookup_str(solv.REPOSITORY_REPOMD_LOCATION)
            chksum = dp.lookup_checksum(solv.REPOSITORY_REPOMD_CHECKSUM)
            if filename and not chksum:
                print("no %s file checksum!" % filename)
                filename = None
                chksum = None
            if filename:
                return (filename, chksum)
        return (None, None)
        
    def add_ext(self, repodata, what, ext):
        filename, chksum = self.find(what)
        if not filename and what == 'deltainfo':
            filename, chksum = self.find('prestodelta')
        if not filename:
            return
        handle = repodata.new_handle()
        repodata.set_poolstr(handle, solv.REPOSITORY_REPOMD_TYPE, what)
        repodata.set_str(handle, solv.REPOSITORY_REPOMD_LOCATION, filename)
        repodata.set_checksum(handle, solv.REPOSITORY_REPOMD_CHECKSUM, chksum)
        self.add_ext_keys(ext, repodata, handle)
        repodata.add_flexarray(solv.SOLVID_META, solv.REPOSITORY_EXTERNAL, handle)

    def add_exts(self):
        repodata = self.handle.add_repodata(0)
        repodata.extend_to_repo()
        self.add_ext(repodata, 'deltainfo', 'DL')
        self.add_ext(repodata, 'filelists', 'FL')
        repodata.internalize()
    
    def load_ext(self, repodata):
        repomdtype = repodata.lookup_str(solv.SOLVID_META, solv.REPOSITORY_REPOMD_TYPE)
        if repomdtype == 'filelists':
            ext = 'FL'
        elif repomdtype == 'deltainfo':
            ext = 'DL'
        else:
            return False
        sys.stdout.write("[%s:%s: " % (self.name, ext))
        if self.usecachedrepo(ext):
            sys.stdout.write("cached]\n")
            sys.stdout.flush()
            return True
        sys.stdout.write("fetching]\n")
        sys.stdout.flush()
        filename = repodata.lookup_str(solv.SOLVID_META, solv.REPOSITORY_REPOMD_LOCATION)
        filechksum = repodata.lookup_checksum(solv.SOLVID_META, solv.REPOSITORY_REPOMD_CHECKSUM)
        f = self.download(filename, True, filechksum)
        if not f:
            return False
        if ext == 'FL':
            self.handle.add_rpmmd(f, 'FL', solv.Repo.REPO_USE_LOADING|solv.Repo.REPO_EXTEND_SOLVABLES|solv.Repo.REPO_LOCALPOOL)
        elif ext == 'DL':
            self.handle.add_deltainfoxml(f, solv.Repo.REPO_USE_LOADING)
        self.writecachedrepo(ext, repodata)
        return True

class repo_unknown(repo_generic):
    def load(self, pool):
        print("unsupported repo '%s': skipped" % self.name)
        return False

class repo_system(repo_generic):
    def load(self, pool):
        self.handle = pool.add_repo(self.name)
        self.handle.appdata = self
        pool.installed = self.handle
        sys.stdout.write("rpm database: ")
        self['cookie'] = self.calc_cookie_file("/var/lib/rpm/Packages")
        if self.usecachedrepo(None):
            print("cached")
            return True
        print("reading")
        if hasattr(self.handle.__class__, 'add_products'):
            self.handle.add_products("/etc/products.d", solv.Repo.REPO_NO_INTERNALIZE)
        f = solv.xfopen(self.cachepath())
        self.handle.add_rpmdb_reffp(f, solv.Repo.REPO_REUSE_REPODATA)
        self.writecachedrepo(None)
        return True

class repo_cmdline(repo_generic):
    def load(self, pool):
        self.handle = pool.add_repo(self.name)
        self.handle.appdata = self 
        return True

def get_repofilter(pool, repos, pkg='', repofilterlist=None):
    repofilter = None
    if pkg.startswith("repo:"):
        # retrieve custom repo keyword
        # repo:foo:*
        keyword, reponame, pkg = pkg.split(':', 2)
        repofilterlist=[reponame]
    
    if repofilterlist: 
        dbg_reponames = []
        for repo in repos:
            dbg_reponames.append(repo.name)
            if repo.name in repofilterlist and hasattr(repo, 'handle'):
                if not repofilter:
                    repofilter = pool.Selection()
                repofilter.add(repo.handle.Selection(solv.Job.SOLVER_SETVENDOR))
        
        if not repofilter: 
            print("no repository matches '%s'" % repofilterlist)
            print("Possible repo: name values {}".format(','.join(dbg_reponames)))
            sys.exit(1)
    return repofilter, pkg

def load_stub(repodata):
    repo = repodata.repo.appdata
    if repo:
        return repo.load_ext(repodata)
    return False

def dir_path(string):
    """
    Check args directory
    """
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)
