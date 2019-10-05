
import solv

import re
from collections import OrderedDict

import logging

logger = logging.getLogger(__name__)

class data_json(object):

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
                    ("references", str_reference_id),
                    ("reference_title", str_reference_title),
                    ("reference_href", str_reference_href),
                    ("reference_type", str_reference_type),
                ))
            )

    def get_updateinfo(self, solvable, updateinfos):
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
        updateinfos.append(
            OrderedDict((
                ("name", str_name),
                ("patchcategory", str_patchcategory),
                ("severity", str_severity),
                ("buildtime", num_buildtime),
                ("reboot", str_reboot),
                ("references", references), 
            ))
        )


    def format(self, solvables):
        evr_re = re.compile('^(?:(?P<epoch>\d+):)?(?P<version>.*?)(?:\.(?P<release>\w+))?$')
        data = {}
        for s in solvables:
            str_name = s.lookup_str(solv.SOLVABLE_NAME)
            str_arch = s.lookup_str(solv.SOLVABLE_ARCH)
            str_evr = s.lookup_str(solv.SOLVABLE_EVR)
            num_buildtime = s.lookup_num(solv.SOLVABLE_BUILDTIME)
           
            nevra = "{}-{}.{}".format(str_name, str_evr, str_arch)
            # update or insert errata in packages list
            na = "{}.{}".format(str_name, str_arch)
            d = OrderedDict((
                ('nevra', nevra),
                ('name', str_name),
                ('evr', str_evr),
                ('arch', str_arch),
                ('repo', str(s.repo)),
                ('buildtime', num_buildtime),
            ))
            data[na] = d
            # 1:3.0.12-17.el7
            ma = evr_re.match(str_evr)
            if ma is not None:
                md = ma.groupdict()
                e = md['epoch']
                if not e:
                    d['epoch'] = '0'
                else :
                    d['epoch'] = e
                d['version'] = ma['version']
                d['release'] = ma['release']
            if d['release']:
                frmt_str = '{epoch}:{name}-{version}.{release}.{arch}'
            else:
                frmt_str = '{epoch}:{name}-{version}.{arch}'
            d['envra'] = frmt_str.format(**d)
            updateinfos = [] 
            # read all related packages
            sel = s.pool.select(na, solv.Selection.SELECTION_DOTARCH|solv.Selection.SELECTION_NAME)
            for other in sel.solvables():
                if other.evrcmp(s) < 1:
                    logger.info("Retrieve update info for : {}".format(other))
                    # solvable is newer than other
                    o_str_name = other.lookup_str(solv.SOLVABLE_NAME)
                    o_str_arch = other.lookup_str(solv.SOLVABLE_ARCH)
                    o_str_evr = other.lookup_str(solv.SOLVABLE_EVR)
                    o_nevra = "{}-{}.{}".format(o_str_name, o_str_evr, o_str_arch)
                    uc_pack = s.pool.Dataiterator(solv.UPDATE_COLLECTION_FILENAME, o_nevra + '.rpm', solv.Dataiterator.SEARCH_GLOB)
                    uc_pack.prepend_keyname(solv.UPDATE_COLLECTION)
                    for uc_p in uc_pack:
                        advisory = uc_p.solvable
                        self.get_updateinfo(advisory, updateinfos)
            d["updateinfos"] = updateinfos
            print("  - %s" % s)
        # sort data's packages name
        # the sort is just to ease human reading
        # and/or diff comparison
        return OrderedDict(sorted(data.items()))


