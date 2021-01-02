import logging
import re


def get_included_headers_from_source_code(source):
    res = []
    lines = source.splitlines()
    for line in lines:
        line = line.strip()
        m = re.fullmatch(r'^#include ("|<)(.+[.](h|hpp))("|>)$', line)
        if m is not None:
            header = m.group(2)
            logging.debug('Include found: {}'.format(header))
            res.append(header)
    return res
