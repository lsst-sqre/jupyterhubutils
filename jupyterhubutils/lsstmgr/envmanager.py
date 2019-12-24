from ..utils import make_logger, str_true, sanitize_dict


class LSSTEnvironmentManager(object):
    '''Class to hold LSST-specific, but not user-specific, environment.
    The user- specific pieces (from the volume manager and the quota
    manager) will be injected at spawn time.

    The environment should be regarded as immutable after creation.
    '''
    pod_env = {}

    def __init__(self, *args, **kwargs):
        self.log = make_logger()
        self.log.debug("Creating LSSTEnvironmentManager")
        self.parent = kwargs.pop('parent')

    def create_pod_env(self):
        '''Return a dict mapping string to string for injection into the
        pod environment.
        '''
        cfg = self.parent.config
        env = {}
        env['DEBUG'] = str_true(cfg.debug)
        env['MEM_LIMIT'] = cfg.mem_limit
        env['CPU_LIMIT'] = cfg.cpu_limit
        # FIXME
        # Workaround for a bug in our dask templating.
        mem_g = cfg.mem_guarantee
        env['MEM_GUARANTEE'] = self._mem_workaround(mem_g)
        env['CPU_GUARANTEE'] = cfg.cpu_guarantee
        env['LAB_SIZE_RANGE'] = cfg.lab_size_range
        env['CULL_TIMEOUT'] = cfg.cull_timeout
        env['CULL_POLICY'] = cfg.cull_policy
        env['RESTRICT_DASK_NODES'] = str_true(cfg.restrict_dask_nodes)
        env['LAB_NODEJS_MAX_MEM'] = cfg.lab_nodejs_max_mem
        env['NODE_OPTIONS'] = cfg.lab_node_options
        env['EXTERNAL_HUB_URL'] = cfg.external_hub_url
        env['HUB_ROUTE'] = cfg.hub_route
        env['EXTERNAL_HUB_URL'] = cfg.external_hub_url
        env['EXTERNAL_URL'] = cfg.external_hub_url
        env['EXTERNAL_INSTANCE_URL'] = cfg.external_instance_url
        env['FIREFLY_ROUTE'] = cfg.firefly_route
        env['JS9_ROUTE'] = cfg.js9_route
        env['API_ROUTE'] = cfg.api_route
        env['TAP_ROUTE'] = cfg.tap_route
        env['SODA_ROUTE'] = cfg.soda_route
        env['WORKFLOW_ROUTE'] = cfg.workflow_route
        env['EXTERNAL_FIREFLY_ROUTE'] = cfg.external_firefly_route
        env['EXTERNAL_JS9_ROUTE'] = cfg.external_js9_route
        env['EXTERNAL_API_ROUTE'] = cfg.external_api_route
        env['EXTERNAL_TAP_ROUTE'] = cfg.external_tap_route
        env['EXTERNAL_SODA_ROUTE'] = cfg.external_soda_route
        env['EXTERNAL_WORKFLOW_ROUTE'] = cfg.external_workflow_route
        env['AUTO_REPO_URLS'] = cfg.auto_repo_urls
        # Now clean up the env hash by removing any keys with empty values
        cleaned = self._clean_env(env)
        sanitized = self._sanitize(cleaned)
        self.log.debug("create_env yielded:\n.{}".format(sanitized))
        self.pod_env = cleaned

    def _mem_workaround(self, mem):
        '''We need to stop appending "M" to the dask template.  For now
        we return size-in-megabytes-with-no-suffix.
        '''
        if not mem:
            return "1"
        mem_s = str(mem)
        last_c = mem_s[-1].upper()
        # If we get ever-so-precious "*i", deal with it.  "M" also means
        #  2^20 here, not 10^6.  Deal with it.
        if last_c.isdigit():
            return mem_s
        mem_s = mem_s[:-1]
        if last_c == "i":
            mem_s = mem_s[:-1]
            last_c = mem_s[-1]
        mem_i = None
        try:
            mem_i = int(mem_s)
        except ValueError:
            return "1"
        if mem_i < 1:
            mem_i = 1
        if last_c == "K":
            mem_i = int(mem_i / 1024)
            if mem_i < 1:
                mem_i = 1
        elif last_c == "G":
            mem_i = 1024 * mem_i
        elif last_c == "T":
            mem_i = 1024 * 1024 * mem_i
        else:
            # Assume M
            pass
        return str(mem_i)

    def _clean_env(self, env):
        return {str(k): str(v) for k, v in env.items() if (v is not None and
                                                           str(v) != '')}

    def get_env(self):
        '''Return the whole stored environment to caller as a dict.
        '''
        return self.pod_env

    def get_env_key(self, key):
        '''Return value of a specific key in the stored environment to caller.
        '''
        return self.pod_env.get(key)

    def _sanitize(self, incoming):
        sensitive = ['ACCESS_TOKEN', 'GITHUB_ACCESS_TOKEN',
                     'JUPYTERHUB_API_TOKEN', 'JPY_API_TOKEN']
        return sanitize_dict(incoming, sensitive)

    def dump(self):
        '''Return contents as a dict for pretty-printing.
        '''
        ed = {"parent": str(self.parent),
              "pod_env": self._sanitize(self.pod_env)
              }
        return ed