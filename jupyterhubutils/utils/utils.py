'''
Shared utility functions.
'''

import logging
import os

from collections import defaultdict


def rreplace(s, old, new, occurrence):
    '''Convenience function from:
    https://stackoverflow.com/questions/2556108/\
    rreplace-how-to-replace-the-last-occurrence-of-an-expression-in-a-string
    '''
    li = s.rsplit(old, occurrence)
    return new.join(li)


def sanitize_dict(input_dict, sensitive_fields):
    retval = {}
    if not input_dict:
        return retval
    retval.update(input_dict)
    for field in sensitive_fields:
        if retval.get(field):
            retval[field] = "[redacted]"
    return retval


def get_execution_namespace():
    '''Return Kubernetes namespace of this container.
    '''
    ns_path = '/var/run/secrets/kubernetes.io/serviceaccount/namespace'
    if os.path.exists(ns_path):
        with open(ns_path) as f:
            return f.read().strip()
    return None


def make_logger(name=__name__):
    '''Create a logger with a specific output format.
    '''
    logger = logging.getLogger(name)
    fstr = '%(levelname)s | %(asctime)s | %(module)s:%(funcName)s:%(lineno)d'
    fstr += ' | %(message)s'
    ch = logging.StreamHandler()
    fmt = logging.Formatter(fstr)
    ch.setFormatter(fmt)
    # Remove default handlers, if any
    logger.handlers = []
    logger.addHandler(ch)
    return logger


def str_bool(s):
    '''Make a sane guess for whether a value represents true or false.
    '''
    if not s:
        return False
    if type(s) != str:
        # It's not a string and it's not falsy, soooo....
        return True
    s = s.lower()
    if s in ['false', '0', 'no', 'n']:
        return False
    return True


def str_true(v):
    '''The string representation of a true value will be 'TRUE'.  False will
    be the empty string.
    '''
    if v:
        return 'TRUE'
    else:
        return ''


def list_duplicates(seq):
    '''List duplicate items from a sequence.
    '''
    # https://stackoverflow.com/questions/5419204
    tally = defaultdict(list)
    for i, item in enumerate(seq):
        tally[item].append(i)
    return ((key, locs) for key, locs in tally.items()
            if len(locs) > 1)
