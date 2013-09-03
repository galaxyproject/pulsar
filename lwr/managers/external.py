from re import search

EXTERNAL_ID_TYPE_ANY = None

EXTERNAL_ID_PATTERNS = [
    ('condor', r'submitted to cluster (\d+).'),
    ('slurm', r'Submitted batch job (\w+)'),
    ('pbs', r'(.+)'),  # Default 'pattern' assumed by Galaxy code circa August 2013.
]


def parse_external_id(output, type=EXTERNAL_ID_TYPE_ANY):
    external_id = None
    for pattern_type, pattern in EXTERNAL_ID_PATTERNS:
        if type != EXTERNAL_ID_TYPE_ANY and type != pattern_type:
            continue

        match = search(pattern, output)
        if match:
            external_id = match.group(1)
            break

    return external_id
