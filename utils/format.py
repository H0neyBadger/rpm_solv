
import solv

import re
from collections import OrderedDict

import logging

logger = logging.getLogger(__name__)

class data_json(object):

    def __init__(self, pool):
        self.pool = pool
    
    def get_array(self, solvable, keyname):
        """
        Retrun a list of string based on solvable's keyname 
        """
        ret = []
        ids = solvable.lookup_idarray(keyname)
        for i in ids:
            ret.append(self.pool.id2str(i))
        # sort all array to keep consistent
        # list in data reports
        return sorted(ret)

    def get_references(self, solvable, references):
        """
        Read references
        i.e: bugzilla links ..
        """
        pack = solvable.Dataiterator(solv.UPDATE_REFERENCE_ID, '*', solv.Dataiterator.SEARCH_GLOB)
        pack.prepend_keyname(solv.UPDATE_REFERENCE)
        for p in pack: 
            pos = p.parentpos()
            str_reference_id = pos.lookup_str(solv.UPDATE_REFERENCE_ID)
            str_reference_title = pos.lookup_str(solv.UPDATE_REFERENCE_TITLE)
            str_reference_href = pos.lookup_str(solv.UPDATE_REFERENCE_HREF)
            str_reference_type = pos.lookup_str(solv.UPDATE_REFERENCE_TYPE)
            references.append(
                OrderedDict((
                    ("reference_id", str_reference_id),
                    ("reference_title", str_reference_title),
                    ("reference_href", str_reference_href),
                    ("reference_type", str_reference_type),
                ))
            )

    def get_updateinfo(self, solvable, str_col_filename):
        """
        Read errata/advisory info
        i.e: severity, name ...
        """

        str_name = solvable.lookup_str(solv.SOLVABLE_NAME)
        str_patchcategory = solvable.lookup_str(solv.SOLVABLE_PATCHCATEGORY)
        str_severity = solvable.lookup_str(solv.UPDATE_SEVERITY)
        num_buildtime = solvable.lookup_num(solv.SOLVABLE_BUILDTIME)
        # the reboot field is no filled by vendors 
        # keep it for info
        str_reboot = solvable.lookup_str(solv.UPDATE_REBOOT)
        references = []
        self.get_references(solvable, references)
        return OrderedDict((
            ("name", str_name),
            ("patchcategory", str_patchcategory),
            ("severity", str_severity),
            ("buildtime", num_buildtime),
            ("reboot", str_reboot),
            ("collection_filename", str_col_filename),
            ("references", sorted(references, key=lambda k: k['reference_id'], reverse=True)), 
        ))
    
    def build_updateinfo_stack(self, data, sel):
        """
        Parse UPDATE_COLLECTION_FILENAME 
        and compare it to available selection
        to retrieve packages' update infos
        """
        logger.info("Retrieve updateinfo for packages")
        split_filname_re = re.compile( \
                '(?P<name>.*)-(?P<version>[^-]+)-(?P<release>[^-]+)\.(?P<arch>\w+).rpm$' \
        )
        flags = solv.Selection.SELECTION_NAME | solv.Selection.SELECTION_DOTARCH | solv.Selection.SELECTION_REL
        # iterate over all advisory is faster than
        # searching for each errata's solv.UPDATE_COLLECTION_FILENAME
        # one by one
        uc_pack = self.pool.Dataiterator(solv.UPDATE_COLLECTION_FILENAME, '*', solv.Dataiterator.SEARCH_GLOB)
        uc_pack.prepend_keyname(solv.UPDATE_COLLECTION)
        for p in uc_pack:
            pos = p.parentpos()
            #str_col_evr = pos.lookup_str(solv.UPDATE_COLLECTION_EVR)
            str_col_name = pos.lookup_str(solv.UPDATE_COLLECTION_NAME)
            str_col_arch = pos.lookup_str(solv.UPDATE_COLLECTION_ARCH)
            str_col_filename = pos.lookup_str(solv.UPDATE_COLLECTION_FILENAME)
            
            nevra_m = split_filname_re.match(str_col_filename)
            if nevra_m is not None:
                nevra_d = nevra_m.groupdict()
                query = '{name}.{arch} >= {version}-{release}'.format(**nevra_d) 
                new_sel = self.pool.select(query, flags)
                new_sel.filter(sel)
                info = self.get_updateinfo(p.solvable, str_col_filename)
                for s in new_sel.solvables():
                    str_name = s.lookup_str(solv.SOLVABLE_NAME)
                    str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
                    str_evr = s.lookup_str(solv.SOLVABLE_EVR)
                    nevra = "{}-{}.{}".format(str_name, str_evr, str_arch)
                    d = data.get(nevra, None)
                    if d:
                        # update or insert errata in packages list
                        updateinfos = d.get('updateinfos', [])
                        if info not in updateinfos:
                            updateinfos.append(info)
                        d["updateinfos"] = sorted(updateinfos, key=lambda k: k['buildtime'], reverse=True)
                    else:
                        continue
            else:
                logger.warning('Failed to match UPDATE_COLLECTION_FILENAME: `{}`'.format(str_col_filename))
                continue

    def format(self, solvables, updateinfo=True):
        evr_re = re.compile('^(?:(?P<epoch>\d+):)?(?P<version>.*?)(?:\.(?P<release>\w+))?$')
        # create an empty selection to read 
        # update information from repo
        updateinfo_sel = self.pool.Selection()
        data = {}
        for s in solvables:
            str_name = s.lookup_str(solv.SOLVABLE_NAME)
            str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
            str_evr = s.lookup_str(solv.SOLVABLE_EVR)
            num_buildtime = s.lookup_num(solv.SOLVABLE_BUILDTIME)
            str_vendor = s.lookup_str(solv.SOLVABLE_VENDOR)
            str_summary = s.lookup_str(solv.SOLVABLE_SUMMARY)
            str_description = s.lookup_str(solv.SOLVABLE_DESCRIPTION)
            provides = self.get_array(s, solv.SOLVABLE_PROVIDES)
            requires = self.get_array(s, solv.SOLVABLE_REQUIRES)
            # do not display filelist, obsolete & conflict
            # since those attributes are removed from pool 
            # to avoid problem solving
            #filelist = self.get_array(s, solv.SOLVABLE_FILELIST)
            #import pdb; pdb.set_trace()

            nevra = "{}-{}.{}".format(str_name, str_evr, str_arch)
            # update or insert errata in packages list
            na = "{}.{}".format(str_name, str_arch)
            # 1:3.0.12-17.el7
            ma = evr_re.match(str_evr)
            if ma is not None:
                md = ma.groupdict()
                e = md['epoch']
                if not e:
                    epoch = '0'
                else :
                    epoch = e
                version = ma['version']
                release = ma['release']
            if release:
                frmt_str = '{epoch}:{name}-{version}.{release}.{arch}'
            else:
                frmt_str = '{epoch}:{name}-{version}.{arch}'
            df = {
                'name': str_name,
                'epoch': epoch,
                'release': release,
                'version': version,
                'arch': str_arch,
            }
            envra = frmt_str.format(**df)

            d = OrderedDict((
                ('nevra', nevra),
                ('summary', str_summary),
                ('description', str_description),
                ('sourcepkg', s.lookup_sourcepkg()),
                ('buildtime', num_buildtime),
                ('vendor', str_vendor),
                ('name', str_name),
                ('epoch', epoch),
                ('release', release),
                ('version', version),
                ('arch', str_arch),
                ('evr', str_evr),
                ('envra', envra),
                ('repo', str(s.repo)),
                ('provides', provides),
                ('requires', requires),
            ))
            data[nevra] = d
            updateinfos = [] 
            # read all <= related packages
            updateinfo_sel.add(s.Selection())
            print("  - %s" % s)
        
        if updateinfo and updateinfo_sel:
            self.build_updateinfo_stack(data, updateinfo_sel)

        # sort data's packages name
        # sorting is just to ease human reading
        # and/or diff comparison
        logger.info('Reoder data report')
        ret = list(OrderedDict(sorted(data.items())).values())
        return ret



