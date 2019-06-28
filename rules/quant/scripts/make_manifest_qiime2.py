#! /usr/bin/env python


import sys
import yaml
import os
import argparse
import re
import warnings


parser = argparse.ArgumentParser(description='create a valid qiime2 manifest file', formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('input', help='fastq files formatted as Sample_ID_R1[2].fastq[.gz]', nargs='+')

if __name__ == '__main__':
    args = parser.parse_args()
    
    SAMPLES = set()
    patt = re.compile('(.*)_R[1-2].fastq')
    for fn in args.input:
        m = patt.match(os.path.basename(fn))
        if m:
            SAMPLES.add(m.groups()[0])
        else:
            raise ValueError('failed to identify Sample_ID from file: {}'.format(fn))

    n_fastq, n_samples = len(args.input), len(SAMPLES)
    if 2 * n_samples == n_fastq: #paired end
        header = ['sample-id', 'forward-absolute-filepath', 'reverse-absolute-filepath']
    elif n_samples == n_fastq: # single end
        header = ['sample-id', 'forward-absolute-filepath']
    else:
        raise ValueError('fastq files contains non-unique sample-ids or is a mix of paired and single end reads!')

    sys.stdout.write('\t'.join(header) + '\n')

    for sample_id in SAMPLES:
        els = [sample_id]
        for fn in args.input:
            if os.path.basename(fn).startswith(sample_id):
                els.append(os.path.abspath(fn))
        sys.stdout.write('\t'.join(els) + '\n')
        
