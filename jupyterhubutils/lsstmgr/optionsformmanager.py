'''Class to manage an LSST-specific options form.
'''
import datetime
import jinja2
import json
from collections import OrderedDict
from time import sleep
from .. import SingletonScanner
from ..utils import make_logger


class LSSTOptionsFormManager(object):
    '''Class to create and read a spawner form.
    '''

    sizemap = {}
    _scanner = None
    options_form_data = None

    def __init__(self, *args, **kwargs):
        self.log = make_logger()
        self.log.debug("Creating LSSTOptionsFormManager")
        self.parent = kwargs.pop('parent')

    def get_options_form(self):
        '''Create an LSST Options Form from parent's config object.
        '''
        # Make options form by scanning container repository, then cache it.
        # For a single spawning session, you always get the same form.
        #
        # If that's not OK (long-lived tokens, for example) then in
        #  your authenticator's refresh_user(), clear options_form_data.
        self.log.debug("Creating options form.")
        if self.options_form_data:
            self.log.debug("Returning cached options form.")
            return self.options_form_data
        cfg = self.parent.config
        scanner = SingletonScanner(host=cfg.lab_repo_host,
                                   owner=cfg.lab_repo_owner,
                                   name=cfg.lab_repo_name,
                                   experimentals=cfg.prepuller_experimentals,
                                   dailies=cfg.prepuller_dailies,
                                   weeklies=cfg.prepuller_weeklies,
                                   releases=cfg.prepuller_releases,
                                   cachefile=cfg.prepuller_cachefile,
                                   debug=cfg.debug)
        self._scanner = scanner
        self._sync_scan()
        lnames, ldescs = scanner.extract_image_info()
        desclist = []
        # Setting this up to pass into the Jinja template more easily
        for idx, img in enumerate(lnames):
            desclist.append({"name": img,
                             "desc": ldescs[idx]})
        colon = lnames[0].find(':')
        custtag = lnames[0][:colon] + ":__custom"
        all_tags = scanner.get_all_tags()
        now = datetime.datetime.now()
        nowstr = now.ctime()
        if not now.tzinfo:
            # If we don't have tzinfo, assume it's in UTC
            nowstr += " UTC"
        self._make_sizemap()
        # in order to get the right default size index, we need to poke the
        #  quota manager, because different users may get different sizes
        #  by default
        cfg = self.parent.config
        qm = self.parent.quota_mgr
        qm.define_resource_quota_spec()
        defaultsize = qm.custom_resources.get('size_index') or cfg.size_index
        template_file = self.parent.config.form_template
        template_loader = jinja2.FileSystemLoader(searchpath='/')
        template_environment = jinja2.Environment(loader=template_loader)
        template = template_environment.get_template(template_file)
        optform = template.render(
            defaultsize=defaultsize,
            desclist=desclist,
            all_tags=all_tags,
            custtag=custtag,
            sizelist=list(self.sizemap.values()),
            nowstr=nowstr)
        self.options_form_data = optform
        return optform

    def resolve_tag(self, tag):
        '''Delegate to scanner to resolve convenience tags.
        '''
        return self._scanner.resolve_tag(tag)

    def _sync_scan(self):
        scanner = self._scanner
        cfg = self.parent.config
        delay_interval = cfg.initial_scan_interval
        max_delay_interval = cfg.max_scan_interval
        max_delay = cfg.max_scan_delay
        delay = 0
        epoch = datetime.datetime(1970, 1, 1)
        while scanner.last_updated == epoch:
            self.log.info(("Scan results not available yet; sleeping " +
                           "{:02.1f}s ({:02.1f}s " +
                           "so far).").format(delay_interval, delay))
            sleep(delay_interval)
            delay = delay + delay_interval
            delay_interval *= 2
            if delay_interval > max_delay_interval:
                delay_interval = max_delay_interval
            if delay >= max_delay:
                errstr = ("Scan results did not become available in " +
                          "{}s.".format(max_delay))
                raise RuntimeError(errstr)

    def _make_sizemap(self):
        sizemap = OrderedDict()
        # For supported Python versions, dict is ordered anyway...
        sizes = self.parent.config.form_sizelist
        tiny_cpu = self.parent.config.tiny_cpu
        mem_per_cpu = self.parent.config.mb_per_cpu
        # Each size doubles the previous one.
        cpu = tiny_cpu
        idx = 0
        for sz in sizes:
            mem = mem_per_cpu * cpu
            sizemap[sz] = {"cpu": cpu,
                           "mem": mem,
                           "name": sz,
                           "index": idx}
            desc = sz.title() + " (%.2f CPU, %dM RAM)" % (cpu, mem)
            sizemap[sz]["desc"] = desc
            cpu = cpu * 2
            idx = idx + 1
        # Clean up if list of sizes changed.
        self.sizemap = sizemap

    def options_from_form(self, formdata=None):
        '''Get user selections.
        '''
        options = None
        if formdata:
            self.log.debug("Form data: %s", json.dumps(formdata,
                                                       sort_keys=True,
                                                       indent=4))
            options = {}
            if ('kernel_image' in formdata and formdata['kernel_image']):
                options['kernel_image'] = formdata['kernel_image'][0]
            if ('size' in formdata and formdata['size']):
                options['size'] = formdata['size'][0]
            if ('image_tag' in formdata and formdata['image_tag']):
                options['image_tag'] = formdata['image_tag'][0]
            if ('clear_dotlocal' in formdata and formdata['clear_dotlocal']):
                options['clear_dotlocal'] = True
        return options

    def dump(self):
        '''Return contents dict for pretty-printing.
        '''
        sd = {"parent": str(self.parent),
              "sizemap": self.sizemap,
              "scanner": str(self._scanner)}
        return sd